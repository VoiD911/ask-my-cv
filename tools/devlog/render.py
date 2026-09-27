"""Rendu du journal de développement public : un Markdown par plan et `index.json`.

`render` est une fonction **pure** (aucune entrée/sortie) : elle reçoit les
agents (`extract.load_agents`), les plans (`load_plan_docs`), la table de
correspondance des SHA et la configuration de masquage, et renvoie en mémoire
le contenu de chaque fichier à écrire. L'écriture est faite ensuite, en une
fois, par la CLI (`python -m tools.devlog render`) : si un secret est détecté
dans n'importe quel texte, `SecretDetected` est levée avant toute écriture et
rien n'est produit, pas même partiellement.

Chaîne appliquée à **chaque** texte publié (rapport, description, titre,
objectif, type d'agent, modèle) :

1. `translate_shas` — SHA d'avant la réécriture d'historique → SHA publiés ;
2. `redact` — comptes AWS, chemins de poste, adresses ;
3. `assert_no_secret` — bloquant ;
4. `find_suspects` — non bloquant, consigné dans un rapport **local** (type,
   aperçu opaque, plan, tâche, agent) qui n'est jamais publié.

Le rapport local ne contient jamais la valeur d'un suspect : les descriptions
qui y figurent (contexte d'un suspect, agents non rattachés) passent par la
même chaîne (un secret interrompt aussi le rendu), puis chaque suspect y est
remplacé par son aperçu opaque.

Dans le Markdown publié, le HTML brut est neutralisé hors code (`<` → `&lt;`)
et les champs courts tiennent sur une ligne : un rapport ne peut ni refermer
le bloc `<details>` ni injecter de balise ou de titre. `index.json` garde le
texte brut (le site l'affiche comme texte, jamais comme HTML).

Les consignes des agents (`AgentRecord.prompt`) ne sont **jamais** publiées :
ce sont des instructions du contrôleur, utilisées uniquement pour classer
l'agent (rôle, plan, tâche). Les identifiants d'agent ne sont pas publiés non
plus (ils figurent seulement dans le rapport local, pour résoudre les agents
non rattachés via `assignments`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from tools.devlog.extract import (
    UNKNOWN,
    AgentRecord,
    PlanWindow,
    Role,
    assign_plan,
    published_commit_refs,
    role,
    translate_shas,
)
from tools.devlog.redact import (
    RedactConfig,
    SecretDetected,
    Suspect,
    assert_no_secret,
    find_suspects,
    redact,
)

__all__ = [
    "FINAL_REVIEW",
    "OFF_TASK",
    "REPOSITORY",
    "PlanDoc",
    "RenderResult",
    "SuspectEntry",
    "UnknownAgent",
    "Verdict",
    "load_plan_docs",
    "load_plan_windows",
    "render",
    "task_key",
    "verdict",
]

REPOSITORY = "VoiD911/ask-my-cv"
_REPO_URL = f"https://github.com/{REPOSITORY}"
FINAL_REVIEW = "Revue finale"
OFF_TASK = "Hors tâche"
_PROMPT_HEAD = 400
_INDEX_VERSION = 1

Verdict = Literal["approuvé", "corrections demandées", "non déterminé"]


# --------------------------------------------------------------------------
# Plans
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanDoc:
    """Un document de plan : sa fenêtre d'activité, son titre, son objectif."""

    window: PlanWindow
    title: str
    goal: str
    filename: str


# `YYYY-MM-DD-ask-my-cv-<id>[-<slug>].md` ; l'identifiant est `1b`, `1b-bis`,
# `1c-1a`, `1c-2`, `1d-3`, `1e-2b`… et doit être suivi d'un `-` ou de `.md`.
_PLAN_FILE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})-ask-my-cv-"
    r"(?P<id>\d[a-z](?:-bis|-\d[a-z]?)?)(?=-|\.md$)(?:-.+)?\.md$"
)
_GOAL_LINE = re.compile(r"^\*\*(?:Goal|Objectif)\s*:\*\*\s*(?P<goal>.*)$", re.IGNORECASE)


def _title_and_goal(text: str) -> tuple[str, str]:
    title = ""
    goal = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not title and stripped.startswith("# "):
            title = stripped[2:].strip()
        match = _GOAL_LINE.match(stripped)
        if not goal and match:
            goal = match.group("goal").strip()
        if title and goal:
            break
    return title, goal


def load_plan_docs(plans_dir: Path) -> list[PlanDoc]:
    """Lit les plans d'un dossier, triés par date puis par nom de fichier.

    Fenêtre d'un plan : du jour de son fichier (00:00 UTC) jusqu'à la date
    **distincte** suivante parmi les fichiers de plan (`None` pour la
    dernière). Des plans datés du même jour partagent donc la même fenêtre ;
    leurs mots-clés (`<id>`, `plan <id>`) les départagent (`assign_plan`).
    """
    found: list[tuple[datetime, str, str, str]] = []
    for path in sorted(Path(plans_dir).glob("*.md")):
        match = _PLAN_FILE.match(path.name)
        if match is None:
            continue
        start = datetime.fromisoformat(match.group("date")).replace(tzinfo=UTC)
        found.append((start, path.name, match.group("id"), path.read_text(encoding="utf-8")))
    found.sort(key=lambda item: (item[0], item[1]))
    dates = sorted({item[0] for item in found})
    docs: list[PlanDoc] = []
    for start, filename, plan_id, text in found:
        later = [d for d in dates if d > start]
        window = PlanWindow(
            id=plan_id,
            start=start,
            end=later[0] if later else None,
            keywords=(plan_id, f"plan {plan_id}"),
        )
        title, goal = _title_and_goal(text)
        docs.append(PlanDoc(window=window, title=title or plan_id, goal=goal, filename=filename))
    return docs


def load_plan_windows(plans_dir: Path) -> list[PlanWindow]:
    """Fenêtres des plans d'un dossier (cf. `load_plan_docs`)."""
    return [doc.window for doc in load_plan_docs(plans_dir)]


# --------------------------------------------------------------------------
# Tâche
# --------------------------------------------------------------------------

# « Task 4 », « Tasks 8-9 », « tâche 2 », « Tâches 3–4 ». Le mot « task/tâche »
# est obligatoire : « plan 1c-1b » n'est jamais lu comme un numéro de tâche.
_TASK_RE = re.compile(
    r"(?<!\w)(?:tasks?|t[âa]ches?)\s*#?\s*(?P<first>\d+)(?:\s*[-–]\s*(?P<last>\d+))?(?![\w-])",
    re.IGNORECASE,
)
_FINAL_REVIEW_RE = re.compile(r"\b(?:final\s+review|revue\s+finale)\b", re.IGNORECASE)


def _task_label(text: str) -> str | None:
    match = _TASK_RE.search(text)
    if match is not None:
        first, last = match.group("first"), match.group("last")
        if last is not None and int(last) != int(first):
            return f"Tâches {int(first)}-{int(last)}"
        return f"Tâche {int(first)}"
    if _FINAL_REVIEW_RE.search(text):
        return FINAL_REVIEW
    return None


def task_key(record: AgentRecord) -> str:
    """Tâche d'un agent : description, puis début de la consigne (400 car.).

    `Tâche N`, `Tâches N-M`, `Revue finale`, ou `Hors tâche` à défaut.
    """
    for text in (record.description, record.prompt[:_PROMPT_HEAD]):
        label = _task_label(text)
        if label is not None:
            return label
    return OFF_TASK


_TASK_LABEL_RE = re.compile(r"^Tâches? (?P<first>\d+)(?:-(?P<last>\d+))?$")


def _task_order(label: str) -> tuple[int, int, int]:
    match = _TASK_LABEL_RE.match(label)
    if match is not None:
        first = int(match.group("first"))
        last = int(match.group("last") or first)
        return (0, first, last)
    return (1, 0, 0) if label == FINAL_REVIEW else (2, 0, 0)


# --------------------------------------------------------------------------
# Verdict
# --------------------------------------------------------------------------

_NEGATIVE_RE = re.compile(
    r"\b(?:not\s+(?:yet\s+)?(?:ready|approved)|needs?\s+(?:\w+\s+)?(?:fix|fixes|changes|work)"
    r"|changes\s+requested|request(?:s|ed|ing)?\s+changes|changements\s+demandés"
    r"|corrections?\s+demandées?|non\s+approuvé|pas\s+(?:encore\s+)?prêt|rejected|refusé)",
    re.IGNORECASE,
)
_POSITIVE_RE = re.compile(
    r"\b(?:approved|approuvé|ready\s+to\s+(?:push|merge)|prêt\s+à\s+(?:pousser|fusionner)|lgtm)",
    re.IGNORECASE,
)
_VERDICT_WORD = re.compile(r"verdict", re.IGNORECASE)
_BARE_POSITIVE = re.compile(r"^[\s*_#>`-]*(?:approved|approuvé)[\s*_.!`]*$", re.IGNORECASE)
_BARE_NEGATIVE = re.compile(
    r"^[\s*_#>`-]*(?:needs\s+fixes|changes\s+requested|changements\s+demandés)[\s*_.!`]*$",
    re.IGNORECASE,
)


def _judge(text: str) -> Verdict | None:
    if _NEGATIVE_RE.search(text):
        return "corrections demandées"
    if _POSITIVE_RE.search(text):
        return "approuvé"
    return None


def _verdict_window(report: str, start: int) -> str:
    """Reste de la ligne après « verdict » ; si elle est muette, la ligne non
    vide suivante (« **Verdict** » seul sur sa ligne, conclusion dessous)."""
    line_end = report.find("\n", start)
    if line_end < 0:
        return report[start:]
    rest = report[start:line_end]
    if _judge(rest) is not None:
        return rest
    for line in report[line_end + 1 :].splitlines():
        if line.strip():
            return rest + "\n" + line
    return rest


def verdict(report: str) -> Verdict:
    """Verdict d'un rapport de revue.

    La phrase qui suit le dernier « verdict » est prioritaire ; une forme
    négative (not ready, needs fixes, changes requested, changements
    demandés…) l'emporte sur une forme positive dans cette même phrase. À
    défaut, une ligne réduite à « Approved » / « Needs fixes » compte.
    """
    for match in reversed(list(_VERDICT_WORD.finditer(report))):
        judged = _judge(_verdict_window(report, match.end()))
        if judged is not None:
            return judged
    for line in reversed(report.splitlines()):
        if _BARE_NEGATIVE.match(line):
            return "corrections demandées"
        if _BARE_POSITIVE.match(line):
            return "approuvé"
    return "non déterminé"


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UnknownAgent:
    """Agent non rattaché à un plan : absent du journal, listé dans le rapport local."""

    agent: str
    description: str
    date: str


@dataclass(frozen=True)
class SuspectEntry:
    """Signal heuristique de `find_suspects`, sans jamais la valeur en clair."""

    kind: str
    preview: str
    field: str
    plan: str
    task: str | None
    agent: str | None
    description: str | None


@dataclass(frozen=True)
class RenderResult:
    files: dict[str, str]
    unknown: list[UnknownAgent] = field(default_factory=list)
    suspects: list[SuspectEntry] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Event:
    record: AgentRecord
    role: Role
    task: str
    agent_type: str
    model: str
    description: str
    report: str
    verdict: Verdict | None
    commits: tuple[str, ...]
    links: tuple[str, ...]


_SECTIONS: tuple[tuple[Role, str], ...] = (
    ("implementation", "Implémentation"),
    ("review", "Revues"),
    ("fix", "Corrections"),
    ("other", "Autres"),
)
_REF_RE = re.compile(r"\b(?P<kind>PR|issue)\s*#(?P<num>\d+)\b", re.IGNORECASE)
# Ouverture de bloc de code clôturé (CommonMark : 0 à 3 espaces, 3+ ``` ou ~~~).
_FENCE_OPEN = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")
# Portion de code en ligne : suite de N accents graves, puis la même suite.
_CODE_SPAN = re.compile(r"(?<!`)(?P<ticks>`+)(?!`).*?(?<!`)(?P=ticks)(?!`)")


def _substitute_suspects(text: str, suspects: Iterable[Suspect]) -> str:
    """Remplace les zones suspectes de `text` par leurs aperçus opaques.

    Sûr par construction : les zones sont triées puis fusionnées en
    intervalles disjoints (chevauchantes, imbriquées, décalées, contiguës ou
    identiques) ; chaque intervalle est remplacé **en entier** par les aperçus
    des suspects qu'il couvre, joints par une espace. Aucun caractère d'une
    zone suspecte ne peut donc subsister ; le texte hors zones est intact.
    """
    ordered = sorted(suspects, key=lambda s: (s.start, s.end))
    merged: list[tuple[int, int, list[str]]] = []
    for suspect in ordered:
        if merged and suspect.start <= merged[-1][1]:
            start, end, previews = merged[-1]
            merged[-1] = (start, max(end, suspect.end), [*previews, suspect.preview])
        else:
            merged.append((suspect.start, suspect.end, [suspect.preview]))
    parts: list[str] = []
    last = 0
    for start, end, previews in merged:
        parts += [text[last:start], " ".join(dict.fromkeys(previews))]
        last = end
    parts.append(text[last:])
    return "".join(parts)


class _Publisher:
    """Applique la chaîne de publication et collecte les suspects."""

    def __init__(
        self, commit_map: Mapping[str, str], published: Iterable[str], config: RedactConfig
    ) -> None:
        self.commit_map = commit_map
        self.published = frozenset(sha.lower() for sha in published)
        self.known = self.published | frozenset(commit_map.values())
        self.config = config
        self.suspects: list[SuspectEntry] = []

    def _masked(self, value: str, *, field_name: str, plan: str, record: AgentRecord | None) -> str:
        """`translate_shas` → `redact` → `assert_no_secret` (message sans la valeur)."""
        translated = translate_shas(value, self.commit_map, self.published)
        masked = redact(translated, self.config)
        try:
            assert_no_secret(masked)
        except SecretDetected as exc:
            where = f"plan {plan}, champ {field_name}"
            if record is not None:
                where += f", agent {record.id}"
            raise SecretDetected(f"{exc} ({where})") from None
        return masked

    def _opaque(self, masked: str) -> tuple[str, list[Suspect]]:
        """Remplace chaque suspect de `masked` par son aperçu opaque."""
        suspects = find_suspects(masked, self.config)
        return _substitute_suspects(masked, suspects), suspects

    def _context(self, record: AgentRecord, plan: str) -> str:
        """Description de l'agent pour le rapport local : chaîne complète, puis
        chaque suspect remplacé par son aperçu — jamais la valeur en clair."""
        masked = self._masked(
            record.description, field_name="description", plan=plan, record=record
        )
        return self._opaque(masked)[0]

    def _report(
        self,
        suspects: Iterable[Suspect],
        *,
        field_name: str,
        plan: str,
        task: str | None,
        record: AgentRecord | None,
        context: str | None,
    ) -> None:
        for suspect in suspects:
            self.suspects.append(
                SuspectEntry(
                    kind=suspect.kind,
                    preview=suspect.preview,
                    field=field_name,
                    plan=plan,
                    task=task,
                    agent=record.id if record is not None else None,
                    description=context,
                )
            )

    def text(
        self,
        value: str,
        *,
        field_name: str,
        plan: str,
        record: AgentRecord | None = None,
        task: str | None = None,
    ) -> str:
        """Texte publié : chaîne complète ; les suspects vont au rapport local."""
        masked = self._masked(value, field_name=field_name, plan=plan, record=record)
        suspects = find_suspects(masked, self.config)
        if suspects:
            context = self._context(record, plan) if record is not None else None
            self._report(
                suspects,
                field_name=field_name,
                plan=plan,
                task=task,
                record=record,
                context=context,
            )
        return masked

    def private_description(self, record: AgentRecord) -> str:
        """Description d'un agent non publié (rapport local seulement) : même
        chaîne que le texte publié (un secret interrompt tout), suspects
        remplacés par leur aperçu et signalés."""
        masked = self._masked(
            record.description, field_name="description", plan=UNKNOWN, record=record
        )
        opaque, suspects = self._opaque(masked)
        self._report(
            suspects,
            field_name="description",
            plan=UNKNOWN,
            task=None,
            record=record,
            context=opaque,
        )
        return opaque


def _dedupe(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _links(texts: Iterable[str]) -> tuple[str, ...]:
    found: list[str] = []
    for text in texts:
        for match in _REF_RE.finditer(text):
            kind = "pull" if match.group("kind").lower() == "pr" else "issues"
            found.append(f"{_REPO_URL}/{kind}/{int(match.group('num'))}")
    return _dedupe(found)


def _fmt_date(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M")


def _iso_date(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _escape_inline(line: str) -> str:
    """Échappe `<` en `&lt;` hors des portions de code en ligne : aucune balise
    HTML brute (`</details>`, `<summary>`, `<script>`…) ne sort du texte."""
    parts: list[str] = []
    last = 0
    for match in _CODE_SPAN.finditer(line):
        parts += [line[last : match.start()].replace("<", "&lt;"), match.group(0)]
        last = match.end()
    parts.append(line[last:].replace("<", "&lt;"))
    return "".join(parts)


def _is_closing_fence(line: str, fence: str) -> bool:
    stripped = line.strip()
    indent = len(line) - len(line.lstrip(" "))
    return indent <= 3 and len(stripped) >= len(fence) and stripped == fence[0] * len(stripped)


def _safe_markdown(text: str) -> str:
    """Rapport prêt à insérer dans le bloc `<details>` : HTML brut neutralisé
    hors code (`_escape_inline`), blocs de code clôturés laissés intacts, et
    bloc resté ouvert refermé pour ne pas avaler la suite du journal."""
    lines: list[str] = []
    fence: str | None = None
    for line in text.rstrip().split("\n"):
        if fence is None:
            opening = _FENCE_OPEN.match(line)
            if opening is not None:
                fence = opening.group("fence")
                lines.append(line)
            else:
                lines.append(_escape_inline(line))
            continue
        lines.append(line)
        if _is_closing_fence(line, fence):
            fence = None
    if fence is not None:
        lines.append(fence)
    return "\n".join(lines)


def _inline(text: str) -> str:
    """Champ court publié sur une seule ligne Markdown : sauts de ligne
    supprimés (aucune ligne injectée) et HTML brut neutralisé."""
    return _escape_inline(_one_line(text))


def _event_markdown(event: _Event) -> list[str]:
    head = (
        f"#### {_fmt_date(event.record.started)} · {_inline(event.agent_type)}"
        f" · {_inline(event.model)}"
    )
    lines = [head, "", f"- Description : {_inline(event.description) or '—'}"]
    if event.verdict is not None:
        lines.append(f"- Verdict : {event.verdict}")
    if event.commits:
        commits = ", ".join(f"[`{sha[:7]}`]({_REPO_URL}/commit/{sha})" for sha in event.commits)
        lines.append(f"- Commits : {commits}")
    if event.links:
        refs = ", ".join(
            f"[{'PR' if '/pull/' in url else 'issue'} #{url.rsplit('/', 1)[1]}]({url})"
            for url in event.links
        )
        lines.append(f"- Liens : {refs}")
    lines += ["", "<details><summary>Rapport</summary>", ""]
    lines.append(_safe_markdown(event.report) or "_(rapport vide)_")
    lines += ["", "</details>", ""]
    return lines


def _plan_markdown(doc: PlanDoc, title: str, goal: str, tasks: list[tuple[str, list[_Event]]]):
    lines = [f"# {_inline(title)}", ""]
    if goal:
        lines += [f"**Objectif :** {_inline(goal)}", ""]
    lines += [f"Plan : [{doc.filename}](../plans/{doc.filename})", ""]
    for label, events in tasks:
        lines += [f"## {label}", ""]
        for section_role, section_title in _SECTIONS:
            section = [e for e in events if e.role == section_role]
            if not section:
                continue
            lines += [f"### {section_title}", ""]
            for event in section:
                lines += _event_markdown(event)
    return "\n".join(lines).rstrip() + "\n"


def _event_json(event: _Event) -> dict[str, object]:
    return {
        "type": event.role,
        "date": _iso_date(event.record.started),
        "agent_type": event.agent_type,
        "model": event.model,
        "description": event.description,
        "verdict": event.verdict,
        "commits": list(event.commits),
        "links": list(event.links),
    }


def render(
    agents: Sequence[AgentRecord],
    plan_docs: Sequence[PlanDoc],
    commit_map: Mapping[str, str],
    published: Iterable[str],
    config: RedactConfig,
    *,
    assignments: Mapping[str, str | None] | None = None,
    github_flow_plans: frozenset[str] = frozenset(),
) -> RenderResult:
    """Construit en mémoire `<plan>.md` (par plan ayant au moins un agent) et
    `index.json`. Aucune écriture ; `SecretDetected` interrompt tout.

    `assignments` (identifiant d'agent → plan) prime sur `assign_plan` : c'est
    ainsi que le contrôleur résout localement les agents « inconnu ». Une
    valeur `None` écarte délibérément l'agent : ni publié, ni signalé comme
    inconnu, seulement listé dans `RenderResult.excluded`. Les
    liens de PR/issue ne sont produits que pour les plans de
    `github_flow_plans` (les plus anciens précèdent la numérotation actuelle
    du dépôt).
    """
    docs = sorted(plan_docs, key=lambda d: (d.window.start, d.filename))
    doc_by_id = {doc.window.id: doc for doc in docs}
    windows = [doc.window for doc in docs]
    overrides = dict(assignments or {})
    for agent_id, plan_id in sorted(overrides.items()):
        if plan_id is not None and plan_id not in doc_by_id:
            raise ValueError(f"assignation de l'agent {agent_id} à un plan inconnu : {plan_id}")

    publisher = _Publisher(commit_map, published, config)
    unknown: list[UnknownAgent] = []
    excluded: list[str] = []
    by_plan: dict[str, list[_Event]] = {}

    for record in sorted(agents, key=lambda r: (r.started, r.id)):
        if record.id in overrides:
            assigned = overrides[record.id]
            if assigned is None:
                excluded.append(record.id)
                continue
            plan_id = assigned
        else:
            plan_id = assign_plan(record, windows)
        if plan_id == UNKNOWN or plan_id not in doc_by_id:
            unknown.append(
                UnknownAgent(
                    agent=record.id,
                    description=publisher.private_description(record),
                    date=_fmt_date(record.started),
                )
            )
            continue
        task = task_key(record)
        kind = role(record)

        description, report, agent_type, model = (
            publisher.text(value, field_name=name, plan=plan_id, record=record, task=task)
            for value, name in (
                (record.description, "description"),
                (record.report, "rapport"),
                (record.type, "type"),
                (record.model, "modèle"),
            )
        )
        commits = tuple(published_commit_refs(report, publisher.known))
        links = _links((description, report)) if plan_id in github_flow_plans else ()
        by_plan.setdefault(plan_id, []).append(
            _Event(
                record=record,
                role=kind,
                task=task,
                agent_type=_one_line(agent_type),
                model=_one_line(model),
                description=description,
                report=report,
                verdict=verdict(record.report) if kind == "review" else None,
                commits=commits,
                links=links,
            )
        )

    files: dict[str, str] = {}
    index_plans: list[dict[str, object]] = []
    for doc in docs:
        plan_id = doc.window.id
        events = by_plan.get(plan_id)
        if not events:
            continue
        title = _one_line(publisher.text(doc.title, field_name="titre", plan=plan_id))
        goal = _one_line(publisher.text(doc.goal, field_name="objectif", plan=plan_id))
        grouped: dict[str, list[_Event]] = {}
        for event in events:
            grouped.setdefault(event.task, []).append(event)
        tasks = sorted(grouped.items(), key=lambda item: _task_order(item[0]))
        files[f"{plan_id}.md"] = _plan_markdown(doc, title, goal, tasks)
        index_plans.append(
            {
                "id": plan_id,
                "title": title,
                "goal": goal,
                "plan_doc": f"docs/plans/{doc.filename}",
                "journal": f"docs/journal/{plan_id}.md",
                "tasks": [
                    {"label": label, "events": [_event_json(e) for e in task_events]}
                    for label, task_events in tasks
                ],
            }
        )

    index = {"version": _INDEX_VERSION, "repository": REPOSITORY, "plans": index_plans}
    files["index.json"] = json.dumps(index, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    return RenderResult(
        files=files, unknown=unknown, suspects=publisher.suspects, excluded=excluded
    )
