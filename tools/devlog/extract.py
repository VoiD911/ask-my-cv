"""Extraction et rattachement des sous-agents pour le journal public.

Ce module lit les journaux de sous-agents (`agent-<id>.jsonl` et
`agent-<id>.meta.json`) produits par l'outil de développement, en tire un
enregistrement par agent (`AgentRecord`), en déduit le rôle (implémentation,
revue, correction), le rattache à un plan (`assign_plan`) et traduit les SHA de
commit d'avant la réécriture d'historique vers les SHA publiés
(`translate_shas`).

Structure attendue d'un `agent-<id>.jsonl` (une entrée JSON par ligne) :

- chaque entrée a un `type` (`user`, `assistant` ou `attachment`) et un
  `timestamp` ISO 8601 (UTC, suffixe `Z`) ;
- la **consigne** est le premier message `user` non méta : `message.content`
  est une chaîne (ou, à défaut, une liste de blocs `text`) ;
- les messages `user` suivants portent des blocs `tool_result`, ou sont des
  messages méta (`isMeta`) — relances du contrôleur, notifications — ignorés
  pour la consigne ;
- les messages `assistant` portent des blocs `thinking`, `text` et
  `tool_use` ; le **rapport final** est le dernier bloc `text` ;
- les entrées `attachment` (crochets, rappels, contexte) ne comptent que pour
  les dates de début et de fin.

`agent-<id>.meta.json` fournit `agentType`, `description` et `model`.

Aucune donnée n'est masquée ici : le masquage (`redact.py`) est appliqué au
moment du rendu, avant toute écriture.
"""

from __future__ import annotations

import json
import re
import subprocess  # noqa: S404
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "UNKNOWN",
    "UNPUBLISHED_SUFFIX",
    "AgentRecord",
    "PlanWindow",
    "Role",
    "assign_plan",
    "load_agent",
    "load_agents",
    "load_commit_map",
    "load_published_shas",
    "role",
    "translate_shas",
]

UNKNOWN = "inconnu"
UNPUBLISHED_SUFFIX = " (hors historique publié)"

Role = Literal["implementation", "review", "fix", "other"]


@dataclass(frozen=True)
class AgentRecord:
    """Un sous-agent, réduit à ce que le journal public peut montrer."""

    id: str
    type: str
    model: str
    description: str
    started: datetime
    ended: datetime
    prompt: str
    report: str


@dataclass(frozen=True)
class PlanWindow:
    """Fenêtre d'activité d'un plan : `[start, end)` ; `end=None` = ouverte."""

    id: str
    start: datetime
    end: datetime | None
    keywords: tuple[str, ...] = ()


# --------------------------------------------------------------------------
# Lecture des sous-agents
# --------------------------------------------------------------------------


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _text_of(content: Any) -> str:
    """Texte d'un `message.content` : chaîne, ou concaténation des blocs `text`."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part)
    return ""


def _read_entries(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{lineno}: JSON invalide ({exc.msg})") from exc
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def _read_meta(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path.name}:{exc.lineno}: métadonnées JSON invalides ({exc.msg})"
        ) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"{path.name}: métadonnées illisibles ({exc})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: objet JSON attendu, {type(data).__name__} trouvé")
    return data


def _first_prompt(entries: Iterable[dict[str, Any]]) -> str:
    for entry in entries:
        if entry.get("type") != "user" or entry.get("isMeta"):
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        text = _text_of(message.get("content"))
        if text:
            return text
    return ""


def _last_report(entries: Sequence[dict[str, Any]]) -> str:
    for entry in reversed(entries):
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str) and content:
            return content
        if isinstance(content, list):
            for block in reversed(content):
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                    return str(block["text"])
    return ""


def _model_of(meta: Mapping[str, Any], entries: Iterable[dict[str, Any]]) -> str:
    model = meta.get("model")
    if isinstance(model, str) and model:
        return model
    for entry in entries:
        message = entry.get("message")
        if entry.get("type") == "assistant" and isinstance(message, dict):
            candidate = message.get("model")
            if isinstance(candidate, str) and candidate and not candidate.startswith("<"):
                return candidate
    return UNKNOWN


def load_agent(jsonl_path: Path) -> AgentRecord:
    """Lit un `agent-<id>.jsonl` et son `agent-<id>.meta.json` voisin."""
    entries = _read_entries(jsonl_path)
    stamps = [
        _parse_timestamp(e["timestamp"]) for e in entries if isinstance(e.get("timestamp"), str)
    ]
    if not stamps:
        raise ValueError(f"{jsonl_path.name}: aucune entrée horodatée")
    stem = jsonl_path.name.removesuffix(".jsonl")
    meta = _read_meta(jsonl_path.with_name(f"{stem}.meta.json"))
    return AgentRecord(
        id=stem.removeprefix("agent-"),
        type=str(meta.get("agentType") or UNKNOWN),
        model=_model_of(meta, entries),
        description=str(meta.get("description") or ""),
        started=min(stamps),
        ended=max(stamps),
        prompt=_first_prompt(entries),
        report=_last_report(entries),
    )


def load_agents(directory: Path) -> list[AgentRecord]:
    """Lit tous les `agent-*.jsonl` d'un dossier, triés par date de début."""
    records = [load_agent(path) for path in sorted(Path(directory).glob("agent-*.jsonl"))]
    return sorted(records, key=lambda r: (r.started, r.id))


# --------------------------------------------------------------------------
# Rôle
# --------------------------------------------------------------------------

# Le mot-clé qui apparaît le plus tôt l'emporte : « Address review findings »
# est une correction, « Review the fix » une revue, « You are an implementer
# … PR under review » une implémentation.
_ROLE_KEYWORDS: tuple[tuple[Role, re.Pattern[str]], ...] = (
    ("review", re.compile(r"\bre-?review", re.IGNORECASE)),
    (
        "fix",
        re.compile(
            r"\b(?:fix(?:e[ds]|ing|er)?|address(?:e[ds]|ing)?"
            r"|correct(?:if|ifs|ion|ions)?|corrig(?:e|é|ée|és|ées|er|ez|es))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "review",
        re.compile(
            r"\b(?:review(?:s|ing|er)?|revue|relecture|audit(?:e|er)?|spec compliance)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "implementation",
        re.compile(
            r"\b(?:implement(?:s|ing|er|ation)?|implémente[rz]?|implémentation|build|create)\b",
            re.IGNORECASE,
        ),
    ),
)

_PROMPT_HEAD = 400


def _earliest_role(text: str) -> Role | None:
    best: tuple[int, Role] | None = None
    for candidate, pattern in _ROLE_KEYWORDS:
        match = pattern.search(text)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), candidate)
    return best[1] if best else None


def role(record: AgentRecord) -> Role:
    """Déduit le rôle d'un agent : type d'agent, puis description, puis consigne.

    Les agents spécialisés en revue (`*reviewer*`) sont toujours des revues. Pour
    les autres, la description courte est consultée d'abord, puis le début de
    la consigne (les consignes citent souvent d'autres rôles plus loin).
    """
    if "reviewer" in record.type.lower():
        return "review"
    for text in (record.description, record.prompt[:_PROMPT_HEAD]):
        found = _earliest_role(text)
        if found is not None:
            return found
    return "other"


# --------------------------------------------------------------------------
# Rattachement à un plan
# --------------------------------------------------------------------------


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    # Bornes excluant aussi « - » : « 1e-2 » ne correspond pas à « 1e-2b ».
    return re.compile(rf"(?<![\w-]){re.escape(keyword)}(?![\w-])", re.IGNORECASE)


def _plans_mentioned(text: str, plans: Sequence[PlanWindow]) -> set[str]:
    return {
        plan.id
        for plan in plans
        if any(_keyword_pattern(k).search(text) for k in plan.keywords if k)
    }


def assign_plan(record: AgentRecord, plans: Sequence[PlanWindow]) -> str:
    """Rattache un agent à un plan, ou renvoie `"inconnu"` si c'est ambigu.

    - Candidats par date : les fenêtres qui contiennent `record.started`.
    - Candidats par mots-clés : les plans cités dans la description ou, à
      défaut, dans la consigne.
    - Un seul candidat commun (ou un seul candidat d'une source quand l'autre
      est muette) → ce plan. Conflit ou plusieurs candidats → `"inconnu"`,
      jamais un choix silencieux.
    """
    by_date = {
        plan.id
        for plan in plans
        if plan.start <= record.started and (plan.end is None or record.started < plan.end)
    }
    by_keyword = _plans_mentioned(record.description, plans) or _plans_mentioned(
        record.prompt, plans
    )
    if by_date and by_keyword:
        candidates = by_date & by_keyword
    else:
        candidates = by_date or by_keyword
    if len(candidates) == 1:
        return next(iter(candidates))
    return UNKNOWN


# --------------------------------------------------------------------------
# Traduction des SHA
# --------------------------------------------------------------------------

_NULL_SHA = "0" * 40
_HEX_TOKEN = re.compile(r"(?<![0-9A-Za-z_:@.\-])([0-9a-f]{7,40})(?![0-9A-Za-z_\-])")
_HAS_HEX_LETTER = re.compile(r"[a-f]")
# Contexte git explicite juste avant le jeton. « HEAD » n'est reconnu qu'en
# majuscules : « head » (tête de liste, de file…) est un mot anglais courant.
_COMMIT_CONTEXT = re.compile(
    r"(?:(?-i:\bHEAD)|\bcommits?|\bsha(?:-?1)?|\bmerge[sd]?|\bcherry-pick(?:ed)?"
    r"|\brevert(?:ed)?|\brebased?|\bgit\s+(?:show|log|diff|checkout|reset|revert|rebase))"
    r"\b(?:\s+(?:is\s+now\s+)?(?:onto|at|to|on|from|of|de|du))?\W{0,8}$",
    re.IGNORECASE,
)
# Ligne de `git log --oneline` : SHA court (avec au moins une lettre a-f),
# espace, puis du texte ; puce ou accent grave facultatifs.
_ONELINE = re.compile(
    r"^[ \t]*(?:[-*][ \t]+)?`?(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}`?[ \t]+\S", re.MULTILINE
)
_ONELINE_MIN_LINES = 2


def load_commit_map(path: Path) -> dict[str, str]:
    """Lit un `commit-map` de git-filter-repo : en-tête `old new`, puis paires.

    Les commits supprimés par la réécriture (nouveau SHA nul) sont omis : ils
    sont traités comme absents de l'historique publié.
    """
    mapping: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] == "old":
            continue
        old, new = (p.lower() for p in parts)
        if new != _NULL_SHA:
            mapping[old] = new
    return mapping


def _unique_prefix(token: str, shas: Iterable[str]) -> str | None:
    found = [sha for sha in shas if sha.startswith(token)]
    return found[0] if len(found) == 1 else None


def _paragraph_around(text: str, start: int) -> tuple[int, int]:
    """Bornes du paragraphe (bloc sans ligne vide) contenant `start`."""
    before = text.rfind("\n\n", 0, start)
    after = text.find("\n\n", start)
    return (0 if before < 0 else before + 2, len(text) if after < 0 else after)


def _in_oneline_log(text: str, start: int) -> bool:
    """Vrai si le jeton ouvre une ligne d'un bloc façon `git log --oneline`.

    La ligne doit avoir la forme `<sha> <texte>` et son paragraphe contenir au
    moins `_ONELINE_MIN_LINES` lignes de cette forme : un mot hexadécimal isolé
    en tête d'une ligne de prose n'est pas une référence de commit.
    """
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", start)
    line = text[line_start : len(text) if line_end < 0 else line_end]
    match = _ONELINE.match(line)
    if match is None or line_start + match.end() <= start:
        return False
    lo, hi = _paragraph_around(text, start)
    return len(_ONELINE.findall(text[lo:hi])) >= _ONELINE_MIN_LINES


def _in_commit_context(text: str, start: int) -> bool:
    return bool(_COMMIT_CONTEXT.search(text[max(0, start - 40) : start]))


def _looks_like_commit_ref(text: str, start: int, token: str) -> bool:
    if not _HAS_HEX_LETTER.search(token):
        return False  # purement numérique : horodatage, compteur, port…
    return len(token) == 40 or _in_oneline_log(text, start) or _in_commit_context(text, start)


def load_published_shas(repo: Path) -> set[str]:
    """SHA de tous les commits accessibles du dépôt publié (`git rev-list --all`).

    Sert à reconnaître les commits postérieurs à la réécriture, absents de la
    table de correspondance mais bien publiés.
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo), "rev-list", "--all"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("commande `git` introuvable") from exc
    except subprocess.CalledProcessError as exc:
        reason = (exc.stderr or "").strip() or f"code de sortie {exc.returncode}"
        raise RuntimeError(f"dépôt git illisible : {repo} ({reason})") from exc
    shas = {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}
    if not shas:
        raise RuntimeError(f"aucun commit dans le dépôt : {repo}")
    return shas


def translate_shas(text: str, commit_map: Mapping[str, str], published: Iterable[str] = ()) -> str:
    """Remplace les SHA anciens (7 à 40 caractères) par les SHA publiés.

    - Un préfixe qui correspond à **un seul** ancien SHA est remplacé par le
      nouveau SHA, tronqué à la même longueur.
    - Un préfixe d'un SHA déjà publié (nouveau SHA de la table, ou SHA de
      `published`, cf. `load_published_shas`) est laissé tel quel.
    - Un jeton qui ressemble à une référence de commit mais absent de la
      table est suivi de `UNPUBLISHED_SUFFIX`. « Ressemble » = au moins une
      lettre a-f **et** (40 caractères, ou précédé d'un contexte git —
      « commit », « SHA », « HEAD » en majuscules, « merge », « cherry-pick »,
      « rebase »… — ou ligne d'un bloc d'au moins deux lignes façon
      `git log --oneline`).
    - Un jeton purement numérique n'est traduit qu'après un contexte git, et
      n'est jamais marqué (horodatages, compteurs, ports).
    - Tout le reste (empreintes `sha256:…`, UUID, identifiants hexadécimaux
      quelconques, préfixes ambigus) est laissé intact.

    La fonction est idempotente.
    """
    old_shas = list(commit_map)
    new_shas = set(commit_map.values()) | {sha.lower() for sha in published}

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if text.startswith(UNPUBLISHED_SUFFIX, match.end()):
            return token
        numeric = not _HAS_HEX_LETTER.search(token)
        if numeric and not _in_commit_context(text, match.start()):
            return token
        old = _unique_prefix(token, old_shas)
        if old is not None:
            return commit_map[old][: len(token)]
        if any(sha.startswith(token) for sha in new_shas):
            return token
        if any(sha.startswith(token) for sha in old_shas):
            return token  # préfixe ambigu : on ne devine pas
        if _looks_like_commit_ref(text, match.start(), token):
            return token + UNPUBLISHED_SUFFIX
        return token

    return _HEX_TOKEN.sub(replace, text)
