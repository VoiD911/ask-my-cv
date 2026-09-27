"""Masquage déterministe pour le journal de développement public.

Ce module ne contient aucune donnée privée en dur (identifiant de compte AWS,
adresse e-mail personnelle, nom d'utilisateur local) : ces valeurs sont
**configurables**, jamais codées ici. Le module fournit uniquement des motifs
génériques (forme d'un ARN, d'un hôte ECR, d'un nom de compartiment S3, d'une
URL de connexion AWS, d'une adresse e-mail, d'un chemin sous `Users`) qui
fonctionnent sans aucune configuration, et une couche de configuration
optionnelle pour les identifiants propres à ce dépôt.

Toutes les valeurs (compte, adresses, chemins) sont masquées en une seule
passe (une unique expression régulière alternée) : cela évite qu'un masquage
en corrompe un autre déjà appliqué (ex. un nom d'utilisateur masqué après
coup à l'intérieur d'une adresse e-mail déjà jugée sûre).

Configuration
--------------
La configuration (`RedactConfig`) peut être construite explicitement (c'est
ce que font les tests, avec des valeurs fictives), ou chargée par
`load_config()` à partir de, dans l'ordre de priorité (fusionnées, jamais
l'une à la place de l'autre) :

1. des variables d'environnement (listes séparées par des virgules) :
   - `DEVLOG_REDACT_AWS_ACCOUNT_IDS` : identifiants de compte AWS (12
     chiffres) à masquer même hors contexte ARN/ECR/compartiment ;
   - `DEVLOG_REDACT_EMAIL_ALLOWLIST` : adresses e-mail à conserver telles
     quelles (en plus des domaines de test et des adresses noreply GitHub,
     toujours autorisés), comparées sans tenir compte de la casse ;
   - `DEVLOG_REDACT_LOCAL_USERNAMES` : noms d'utilisateur locaux (Windows /
     Git Bash / WSL) à masquer même hors d'un chemin `Users/...` ;
   - `DEVLOG_REDACT_PATH_ROOTS` : racines de chemins locaux (ex.
     `D:\\DEV`) à remplacer par `<poste>`, quels que soient la casse et le
     séparateur (`/`, `\\` ou `\\\\` échappé) utilisés dans le texte ;
   - `DEVLOG_REDACT_SECRET_ALLOWLIST` : expressions régulières
     supplémentaires considérées comme sûres par `assert_no_secret` (ex. un
     identifiant public propre au dépôt qui ressemblerait à un jeton).
2. un fichier JSON local, non suivi par git, dont le chemin est
   `DEVLOG_REDACT_CONFIG_PATH` ou par défaut
   `~/.claude/devlog-private/redact.json`, de la forme :

   ```json
   {
     "aws_account_ids": ["111111111111"],
     "email_allowlist": ["job@example.org"],
     "local_usernames": ["swond"],
     "path_roots": ["D:\\\\DEV"],
     "secret_allowlist": []
   }
   ```

   Chaque clé doit être une liste de chaînes non vides (jamais une chaîne
   seule : `"local_usernames": "bob"` lèverait `ConfigError`, pas un masquage
   caractère par caractère). Une clé inconnue, une valeur du mauvais type, une
   chaîne vide, ou un identifiant de compte AWS qui ne fait pas exactement 12
   chiffres lèvent tous `ConfigError`. Un fichier JSON syntaxiquement invalide
   lève `json.JSONDecodeError` (non interceptée). Si
   `DEVLOG_REDACT_CONFIG_PATH` est défini explicitement et que le fichier est
   absent, `ConfigError` est levée (on ne veut pas d'un masquage silencieusement
   incomplet quand la configuration est censée exister) ; si aucune variable
   d'environnement n'est définie et que le fichier par défaut est absent, la
   configuration est simplement vide (seuls les motifs génériques agissent).

Sans configuration, seuls les motifs génériques (ARN, hôte ECR, compartiment
`<préfixe>-<compte>`, champ `"Account": "<compte>"`, URL `<compte>.signin...`,
forme d'adresse e-mail, chemin `Users/<nom>`) sont masqués.

Garde-fou des secrets
----------------------
`assert_no_secret(text, config=None)` lève `SecretDetected` si `text`
contient une chaîne ressemblant à un secret vivant (clé d'API à préfixe
connu, identifiant de clé d'accès AWS, jeton GitHub, JWT, clé privée PEM, ou
tout jeton opaque de 40+ caractères mélangeant majuscules, minuscules et
chiffres). Le message d'erreur donne le type détecté et la position dans le
texte, jamais la valeur.

Elle ne déclenche jamais sur un identifiant public connu : un SHA de commit
git (40/64/128 caractères hexadécimaux, casse indifférente), un digest
`sha256:`/`sha512-` (hexadécimal ou base64, y compris une empreinte SSH
`SHA256:...`), un `CodeSha256` Lambda, ou un identifiant CamelCase/snake_case
sans mélange majuscule+minuscule+chiffre. `config.secret_allowlist` permet
d'ajouter, de façon explicite et testable, des motifs supplémentaires jugés
sûrs pour un dépôt donné, plutôt que d'affaiblir la détection générique.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ConfigError",
    "RedactConfig",
    "SecretDetected",
    "assert_no_secret",
    "load_config",
    "redact",
]


class SecretDetected(Exception):
    """Levée quand un texte contient une chaîne ressemblant à un secret vivant."""


class ConfigError(Exception):
    """Levée quand la configuration de masquage est absente, mal formée ou invalide."""


_ENV_ACCOUNT_IDS = "DEVLOG_REDACT_AWS_ACCOUNT_IDS"
_ENV_EMAIL_ALLOWLIST = "DEVLOG_REDACT_EMAIL_ALLOWLIST"
_ENV_LOCAL_USERNAMES = "DEVLOG_REDACT_LOCAL_USERNAMES"
_ENV_PATH_ROOTS = "DEVLOG_REDACT_PATH_ROOTS"
_ENV_SECRET_ALLOWLIST = "DEVLOG_REDACT_SECRET_ALLOWLIST"  # noqa: S105 -- nom de variable d'env, pas un secret
_ENV_CONFIG_PATH = "DEVLOG_REDACT_CONFIG_PATH"
_DEFAULT_CONFIG_PATH = Path.home() / ".claude" / "devlog-private" / "redact.json"

_ACCOUNT_MASK = "<compte-aws>"
_EMAIL_MASK = "<adresse>"
_HOME_MASK = "~"
_PATH_MASK = "<poste>"
_USERNAME_MASK = "<utilisateur>"

# Domaines toujours considérés comme fictifs (fixtures de test), et tout
# sous-domaine de ceux-ci : jamais masqués.
_TEST_EMAIL_DOMAINS = ("example.com", "evil.com", "corp.com")

_ALLOWED_CONFIG_KEYS = frozenset(
    {
        "aws_account_ids",
        "email_allowlist",
        "local_usernames",
        "path_roots",
        "secret_allowlist",
    }
)
_ACCOUNT_ID_RE = re.compile(r"^\d{12}$")


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class RedactConfig:
    """Valeurs propres à un dépôt/poste, jamais codées en dur dans ce module."""

    aws_account_ids: frozenset[str] = field(default_factory=frozenset)
    email_allowlist: frozenset[str] = field(default_factory=frozenset)
    local_usernames: frozenset[str] = field(default_factory=frozenset)
    path_roots: tuple[str, ...] = field(default_factory=tuple)
    secret_allowlist: tuple[str, ...] = field(default_factory=tuple)

    @staticmethod
    def empty() -> RedactConfig:
        return RedactConfig()

    def merge(self, other: RedactConfig) -> RedactConfig:
        return RedactConfig(
            aws_account_ids=self.aws_account_ids | other.aws_account_ids,
            email_allowlist=self.email_allowlist | other.email_allowlist,
            local_usernames=self.local_usernames | other.local_usernames,
            path_roots=tuple(dict.fromkeys((*self.path_roots, *other.path_roots))),
            secret_allowlist=tuple(
                dict.fromkeys((*self.secret_allowlist, *other.secret_allowlist))
            ),
        )


def _config_from_env() -> RedactConfig:
    return RedactConfig(
        aws_account_ids=frozenset(_split_csv(os.environ.get(_ENV_ACCOUNT_IDS))),
        email_allowlist=frozenset(_split_csv(os.environ.get(_ENV_EMAIL_ALLOWLIST))),
        local_usernames=frozenset(_split_csv(os.environ.get(_ENV_LOCAL_USERNAMES))),
        path_roots=_split_csv(os.environ.get(_ENV_PATH_ROOTS)),
        secret_allowlist=_split_csv(os.environ.get(_ENV_SECRET_ALLOWLIST)),
    )


def _validate_raw_config(data: object) -> dict[str, list[str]]:
    if not isinstance(data, dict):
        raise ConfigError("la configuration doit être un objet JSON (dictionnaire)")
    unknown = sorted(set(data) - _ALLOWED_CONFIG_KEYS)
    if unknown:
        raise ConfigError(f"clé(s) de configuration inconnue(s) : {', '.join(unknown)}")
    for key, value in data.items():
        if not isinstance(value, list):
            raise ConfigError(
                f"« {key} » doit être une liste de chaînes, reçu {type(value).__name__}"
            )
        for item in value:
            if not isinstance(item, str) or item == "":
                raise ConfigError(f"« {key} » ne peut contenir que des chaînes non vides")
    for account_id in data.get("aws_account_ids", []):
        if not _ACCOUNT_ID_RE.match(account_id):
            raise ConfigError(
                f"identifiant de compte AWS invalide : {account_id!r} (attendu : 12 chiffres)"
            )
    return data


def _config_from_file(path: Path) -> RedactConfig:
    if not path.is_file():
        return RedactConfig.empty()
    data = _validate_raw_config(json.loads(path.read_text(encoding="utf-8")))
    return RedactConfig(
        aws_account_ids=frozenset(data.get("aws_account_ids", [])),
        email_allowlist=frozenset(data.get("email_allowlist", [])),
        local_usernames=frozenset(data.get("local_usernames", [])),
        path_roots=tuple(data.get("path_roots", [])),
        secret_allowlist=tuple(data.get("secret_allowlist", [])),
    )


def load_config(*, require_account_ids: bool = False) -> RedactConfig:
    """Charge la configuration depuis l'environnement puis le fichier local.

    N'est jamais appelée implicitement par les tests (qui passent toujours une
    `RedactConfig` explicite avec des valeurs fictives) ; sert uniquement aux
    appelants réels (ex. `render.py`, futur).

    `require_account_ids=True` lève `ConfigError` si aucun identifiant de
    compte AWS n'a été configuré : à utiliser par un appelant qui a besoin de
    garanties que le masquage des comptes ne reposera pas uniquement sur les
    motifs génériques.
    """
    raw_path = os.environ.get(_ENV_CONFIG_PATH)
    explicit_path = raw_path is not None
    config_path = Path(raw_path) if explicit_path else _DEFAULT_CONFIG_PATH
    if explicit_path and not config_path.is_file():
        raise ConfigError(f"fichier de configuration introuvable : {config_path}")

    config = _config_from_file(config_path).merge(_config_from_env())

    for account_id in config.aws_account_ids:
        if not _ACCOUNT_ID_RE.match(account_id):
            raise ConfigError(
                f"identifiant de compte AWS invalide : {account_id!r} (attendu : 12 chiffres)"
            )
    if require_account_ids and not config.aws_account_ids:
        raise ConfigError("aucun identifiant de compte AWS configuré (require_account_ids=True)")
    return config


# --------------------------------------------------------------------------
# Motifs (comptes AWS, chemins, adresses) — combinés en une seule alternance
# --------------------------------------------------------------------------

# Compte AWS entre deux-points d'un ARN : arn:aws:<service>:<region>:<compte>:<ressource>
_ARN_ACCOUNT = r"(?<=:)\d{12}(?=:)"
# Hôte de registre ECR : <compte>.dkr.ecr.<region>.amazonaws.com
_ECR_ACCOUNT = r"\d{12}(?=\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com)"
# URL de connexion à la console : <compte>.signin.aws.amazon.com
_SIGNIN_ACCOUNT = r"\d{12}(?=\.signin\.aws\.amazon\.com)"
# Nom de compartiment/ressource suffixé par le compte : ...-<compte>
_BUCKET_ACCOUNT = r"(?<=-)\d{12}(?!\d)"
# Champ "Account": "<compte>" (JSON, ex. sts get-caller-identity) ou Account: <compte> (texte)
_ACCOUNT_FIELD_QUOTED = r'(?<="Account": ")\d{12}(?=")'
_ACCOUNT_FIELD_PLAIN = r"(?<=Account: )\d{12}"

# Chemin local sous `Users` : Windows (`C:\Users\<nom>`, `C:/Users/<nom>`), Git
# Bash (`/c/Users/<nom>`), WSL (`/mnt/c/Users/<nom>`) ou URI de fichier
# (`file:///C:/Users/<nom>`), casse indifférente. Le nom peut contenir des
# espaces ; il s'arrête au prochain séparateur, guillemet ou fin de ligne.
_USER_HOME_BODY = (
    r"(?:file:///)?"
    r"(?:/mnt)?"
    r"(?:[a-z]:|/[a-z])"
    r"(?:\\+|/)+"
    r"users"
    r"(?:\\+|/)+"
    r"[^\\/\r\n\"']+"
)

_EMAIL_BODY = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

_GITHUB_NOREPLY_RE = re.compile(
    r"^([0-9]+\+)?[^@\s]+@users\.noreply\.github\.com$|^noreply@github\.com$",
    re.IGNORECASE,
)


def _root_pattern_body(root: str) -> str:
    """Construit le corps de motif d'une racine de chemin configurée.

    Accepte indifféremment `/` et `\\` (simple ou doublé, comme dans un
    `.jsonl` où les antislashs Windows sont échappés) à chaque séparateur, et
    est insensible à la casse (appliqué avec `re.IGNORECASE` par
    l'appelant). Une frontière finale évite qu'une racine plus longue
    (`D:\\DEVELOP`) ne soit tronquée par erreur (`D:\\DEV` configurée).
    """
    leading_sep = root[:1] in "\\/"
    segments = [segment for segment in re.split(r"[\\/]+", root) if segment]
    sep = r"(?:\\+|/)+"
    body = sep.join(re.escape(segment) for segment in segments)
    if leading_sep:
        body = sep + body
    return body + r'(?=[\\/"\'\s]|$)'


def _account_id_pattern_body(account_ids: frozenset[str]) -> str | None:
    if not account_ids:
        return None
    ids = "|".join(re.escape(a) for a in sorted(account_ids, key=len, reverse=True))
    # Frontière sur les chiffres (pas `\b`, qui ne s'applique jamais entre deux
    # chiffres et un `_` : `tfstate_<compte>` ne serait alors pas masqué).
    return rf"(?<!\d)(?:{ids})(?!\d)"


def _username_pattern_body(usernames: frozenset[str]) -> str | None:
    if not usernames:
        return None
    names = "|".join(re.escape(n) for n in sorted(usernames, key=len, reverse=True))
    return rf"(?<![A-Za-z0-9])(?:{names})(?![A-Za-z0-9])"


def _compile_master_pattern(config: RedactConfig) -> re.Pattern[str]:
    parts = [
        rf"(?P<acct_arn>{_ARN_ACCOUNT})",
        rf"(?P<acct_ecr>{_ECR_ACCOUNT})",
        rf"(?P<acct_signin>{_SIGNIN_ACCOUNT})",
        rf"(?P<acct_bucket>{_BUCKET_ACCOUNT})",
        rf"(?P<acct_field_q>{_ACCOUNT_FIELD_QUOTED})",
        rf"(?P<acct_field_p>{_ACCOUNT_FIELD_PLAIN})",
    ]
    acct_cfg_body = _account_id_pattern_body(config.aws_account_ids)
    if acct_cfg_body:
        parts.append(rf"(?P<acct_cfg>{acct_cfg_body})")

    parts.append(rf"(?P<home>{_USER_HOME_BODY})")

    for index, root in enumerate(config.path_roots):
        parts.append(rf"(?P<root_{index}>{_root_pattern_body(root)})")

    parts.append(rf"(?P<email>{_EMAIL_BODY})")

    user_cfg_body = _username_pattern_body(config.local_usernames)
    if user_cfg_body:
        parts.append(rf"(?P<user_cfg>{user_cfg_body})")

    return re.compile("|".join(parts), re.IGNORECASE)


def _is_test_domain(domain: str) -> bool:
    return any(domain == known or domain.endswith(f".{known}") for known in _TEST_EMAIL_DOMAINS)


def _is_allowed_email(address: str, config: RedactConfig) -> bool:
    if _GITHUB_NOREPLY_RE.match(address):
        return True
    address_cf = address.casefold()
    if address_cf in {allowed.casefold() for allowed in config.email_allowlist}:
        return True
    domain = address.rsplit("@", 1)[-1].casefold()
    return _is_test_domain(domain)


def _dispatch(match: re.Match[str], config: RedactConfig) -> str:
    kind = match.lastgroup or ""
    text = match.group(0)
    if kind.startswith("acct_"):
        return _ACCOUNT_MASK
    if kind == "home":
        return _HOME_MASK
    if kind.startswith("root_"):
        return _PATH_MASK
    if kind == "email":
        return text if _is_allowed_email(text, config) else _EMAIL_MASK
    if kind == "user_cfg":
        return _USERNAME_MASK
    return text  # pragma: no cover - alternance exhaustive par construction


# --------------------------------------------------------------------------
# API publique — masquage
# --------------------------------------------------------------------------


def redact(text: str, config: RedactConfig | None = None) -> str:
    """Applique tous les masquages déterministes à `text`, en une seule passe.

    `config` est optionnelle : à défaut, elle est chargée par `load_config()`
    (environnement puis fichier local non suivi par git). Les tests passent
    toujours une `RedactConfig` explicite construite avec des valeurs
    fictives, jamais les vraies.

    Une seule expression régulière alternée traite comptes, chemins et
    adresses dans le même passage : chaque caractère n'est donc consommé
    qu'une fois, ce qui élimine par construction tout risque qu'un masquage
    (ex. nom d'utilisateur) n'altère un résultat déjà décidé par un autre
    (ex. une adresse e-mail autorisée qui contiendrait ce nom).

    Idempotente : `redact(redact(x)) == redact(x)`.
    """
    resolved = config if config is not None else load_config()
    pattern = _compile_master_pattern(resolved)
    return pattern.sub(lambda m: _dispatch(m, resolved), text)


# --------------------------------------------------------------------------
# Garde-fou : détection de secrets vivants
# --------------------------------------------------------------------------

# Identifiants publics connus, jamais des secrets : remplacés par des espaces
# (de même longueur, pour préserver les positions et ne jamais recoller deux
# fragments en un faux jeton) avant la recherche de jetons opaques.
_KNOWN_SAFE_PATTERNS = (
    # sha256:<hex|base64>, sha512-<base64> (intégrité npm), SHA256:<base64> (empreinte SSH) …
    re.compile(r"(?i)\bsha(?:1|256|512)[:-][0-9A-Za-z+/=]{16,}"),
    re.compile(r'(?i)codesha256["\']?\s*[:=]\s*["\']?[A-Za-z0-9+/=]{16,}'),
    # Hex pur (SHA de commit ou digest), casse indifférente, longueurs connues uniquement.
    re.compile(r"(?i)(?<![A-Za-z0-9])[0-9a-f]{128}(?![A-Za-z0-9])"),
    re.compile(r"(?i)(?<![A-Za-z0-9])[0-9a-f]{64}(?![A-Za-z0-9])"),
    re.compile(r"(?i)(?<![A-Za-z0-9])[0-9a-f]{40}(?![A-Za-z0-9])"),
)

# Motifs explicites de secrets connus : indépendants de la longueur/l'entropie.
_DANGEROUS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "clé d'API (préfixe sk-/pk-lf- ou sk-proj-)",
        re.compile(r"(?<![A-Za-z0-9_-])(?:sk|pk)-(?:lf|proj)-[A-Za-z0-9_-]+"),
    ),
    (
        "identifiant de clé d'accès AWS",
        re.compile(r"(?<![A-Za-z0-9])(?:AKIA|ASIA|AROA|AIDA)[0-9A-Z]{16}(?![A-Za-z0-9])"),
    ),
    (
        "clé secrète AWS (aws_secret_access_key=...)",
        re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*\S+"),
    ),
    (
        "jeton GitHub (gh?_...)",
        re.compile(r"(?<![A-Za-z0-9_])gh[opsur]_[A-Za-z0-9]{36,}(?![A-Za-z0-9_])"),
    ),
    (
        "jeton GitHub (github_pat_...)",
        re.compile(r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{22,}(?![A-Za-z0-9_])"),
    ),
    (
        "JWT",
        re.compile(r"(?<![A-Za-z0-9_-])eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+(?![A-Za-z0-9_-])"),
    ),
    (
        "clé privée PEM",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
)

# Jeton opaque générique : 40+ caractères d'un alphabet base64url/base64, avec
# padding `=` optionnel en fin. Frontières asymétriques : un jeton peut
# commencer par `/` ou `+` (fréquent en base64) ou suivre immédiatement un
# `=` (assignation `k=...`), mais ne peut pas être collé à un autre caractère
# du même alphabet (sinon on sous-détecterait tout jeton base64url contenant
# `_`/`-`, qui n'a pas de frontière `\b`).
_LONG_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{40,}={0,2}(?![A-Za-z0-9+/_-])")


def _looks_random(token: str) -> bool:
    """Filtre anti-faux-positif : un chemin, un identifiant CamelCase ou
    snake_case ne mélange normalement pas majuscules, minuscules et chiffres.
    Un secret généré aléatoirement (clé, jeton) le fait presque toujours.
    """
    core = token.rstrip("=")
    return (
        any(c.islower() for c in core)
        and any(c.isupper() for c in core)
        and any(c.isdigit() for c in core)
    )


def _blank(pattern: re.Pattern[str] | str, text: str) -> str:
    compiled = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern)
    return compiled.sub(lambda m: " " * len(m.group(0)), text)


def assert_no_secret(text: str, config: RedactConfig | None = None) -> None:
    """Lève `SecretDetected` si `text` contient une chaîne ressemblant à un
    secret vivant (clé d'API, jeton, identifiant de clé d'accès AWS, JWT, clé
    privée PEM...).

    Ne déclenche jamais sur un identifiant public connu (SHA de commit,
    digest `sha256:`/`sha512-`, `CodeSha256`, identifiant sans mélange de
    casse+chiffres). `config.secret_allowlist` (regex) permet d'exempter
    explicitement d'autres motifs propres à un dépôt.

    Le message d'erreur donne le type de secret détecté et sa position dans
    `text`, jamais sa valeur.
    """
    resolved = config if config is not None else RedactConfig.empty()

    scratch = text
    for safe_pattern in _KNOWN_SAFE_PATTERNS:
        scratch = _blank(safe_pattern, scratch)
    for allow_pattern in resolved.secret_allowlist:
        scratch = _blank(allow_pattern, scratch)

    for label, pattern in _DANGEROUS_PATTERNS:
        match = pattern.search(scratch)
        if match:
            raise SecretDetected(f"{label} détectée à la position {match.start()}")

    pos = 0
    while True:
        match = _LONG_TOKEN_RE.search(scratch, pos)
        if match is None:
            return
        token = match.group(0)
        if _looks_random(token):
            raise SecretDetected(
                f"jeton opaque non identifié ({len(token)} caractères) "
                f"détecté à la position {match.start()}"
            )
        pos = match.end()
