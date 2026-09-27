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
coup à l'intérieur d'une adresse e-mail déjà jugée sûre). Chaque motif est
écrit sans quantificateurs imbriqués (`[\\/]+`, jamais `(?:\\+|/)+`) et les
motifs non ancrés (adresse e-mail) portent une garde de début (lookbehind) :
c'est ce qui garantit un temps linéaire même sur une entrée pathologique
(longue suite d'antislashs, texte d'un mégaoctet sans arobase...).

Configuration
--------------
La configuration (`RedactConfig`) peut être construite explicitement (c'est
ce que font les tests, avec des valeurs fictives), ou chargée par
`load_config()` à partir de, dans l'ordre de priorité (fusionnées, jamais
l'une à la place de l'autre) :

1. des variables d'environnement :
   - `DEVLOG_REDACT_AWS_ACCOUNT_IDS` : identifiants de compte AWS (12
     chiffres) à masquer même hors contexte ARN/ECR/compartiment, séparés par
     des virgules ;
   - `DEVLOG_REDACT_EMAIL_ALLOWLIST` : adresses e-mail à conserver telles
     quelles (en plus des domaines de test et des adresses noreply GitHub,
     toujours autorisés), séparées par des virgules, comparées sans tenir
     compte de la casse ;
   - `DEVLOG_REDACT_LOCAL_USERNAMES` : noms d'utilisateur locaux (Windows /
     Git Bash / WSL) à masquer même hors d'un chemin `Users/...`, séparés par
     des virgules ;
   - `DEVLOG_REDACT_PATH_ROOTS` : racines de chemins locaux (ex. `D:\\DEV`) à
     remplacer par `<poste>`, séparées par des virgules, quels que soient la
     casse et le séparateur (`/`, `\\` ou `\\\\` échappé) utilisés dans le
     texte ;
   - `DEVLOG_REDACT_SECRET_ALLOWLIST` : expressions régulières supplémentaires
     considérées comme sûres par `assert_no_secret` (ex. un identifiant public
     propre au dépôt qui ressemblerait à un jeton). Une regex peut contenir
     des virgules : cette variable n'est **jamais** découpée sur `,`. Elle
     accepte soit un tableau JSON de chaînes (`["motif1", "motif2"]`), soit
     une regex par ligne (séparateur `\n`).
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
   chaîne vide ou uniquement des espaces, un identifiant de compte AWS qui ne
   fait pas exactement 12 chiffres, un nom d'utilisateur de moins de 3
   caractères, une racine de chemin de moins de 2 caractères, ou une entrée de
   `secret_allowlist` qui n'est pas une regex valide, qui accepte la chaîne
   vide, ou qui accepte un texte arbitraire trop large (ex. `.*`, `.+`)
   lèvent tous `ConfigError`. Un fichier JSON syntaxiquement invalide lève
   `json.JSONDecodeError` (non interceptée). Si `DEVLOG_REDACT_CONFIG_PATH`
   est défini explicitement et que le fichier est absent, `ConfigError` est
   levée (on ne veut pas d'un masquage silencieusement incomplet quand la
   configuration est censée exister) ; si aucune variable d'environnement
   n'est définie et que le fichier par défaut est absent, la configuration
   est simplement vide (seuls les motifs génériques agissent).

Sans configuration, seuls les motifs génériques (ARN, hôte ECR, compartiment
`<préfixe-alpha>-<compte>`, champ `"Account": "<compte>"`, URL
`<compte>.signin...`, forme d'adresse e-mail, chemin `Users/<nom>`) sont
masqués.

Garde-fou des secrets
----------------------
`assert_no_secret(text, config=None)` lève `SecretDetected` si `text`
contient une chaîne ressemblant à un secret vivant : clé d'API à préfixe
connu, identifiant de clé d'accès AWS (y compris temporaire `ASIA...`), jeton
GitHub, JWT, clé privée PEM, affectation `SECRET=`/`TOKEN=`/`PASSWORD=`/
`API_KEY=` à une valeur qui n'est pas un simple gabarit, jeton hexadécimal
d'une longueur inhabituelle ou sans contexte de digest reconnu, ou tout jeton
opaque de 40+ caractères mélangeant majuscules, minuscules et chiffres. Ces
détecteurs explicites tournent **sur le texte brut, avant toute
suppression de motif jugé sûr** : un préfixe `sha1-`/`sha256:` ne peut donc
jamais servir à camoufler une clé `AKIA...` ou tout autre secret explicite.

Elle ne déclenche jamais sur un identifiant public connu : un SHA de commit
git (exactement 40 caractères hexadécimaux, casse indifférente), un digest
hexadécimal de 64 ou 128 caractères **en contexte de digest** (`sha256:`,
`sha512-`, `@sha256:`, le mot « digest », ou le champ `CodeSha256`), ou un
identifiant CamelCase/snake_case/chemin sans mélange majuscule+minuscule+
chiffre. `config.secret_allowlist` permet d'exempter, de façon explicite et
testable, un jeton générique propre à un dépôt (ex. une URL contenant par
coïncidence un identifiant mélangeant les trois classes de caractères) —
jamais un détecteur explicite (PEM, clé AWS, jeton GitHub, JWT, préfixe
`sk-`/`pk-`, affectation de mot de passe) : ceux-ci sont évalués avant toute
prise en compte de l'allowlist et ne peuvent donc pas être contournés par
elle.
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
_MIN_USERNAME_LENGTH = 3
_MIN_PATH_ROOT_LENGTH = 2

# Chaîne de test diversifiée (lettres, chiffres, séparateurs, ponctuation) :
# une regex de `secret_allowlist` qui la reconnaît entièrement est jugée trop
# permissive (elle accepterait à peu près n'importe quel texte arbitraire).
_BROAD_PATTERN_PROBE = "aB3-x_/9.zK8 Q7" * 20


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _split_secret_allowlist_env(value: str | None) -> tuple[str, ...]:
    """N'utilise jamais la virgule comme séparateur : une regex en contient
    couramment (`{1,3}`, `a,b`). Accepte un tableau JSON ou une regex par
    ligne.
    """
    if not value or not value.strip():
        return ()
    stripped = value.strip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"DEVLOG_REDACT_SECRET_ALLOWLIST n'est pas un tableau JSON valide : {exc}"
            ) from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ConfigError("DEVLOG_REDACT_SECRET_ALLOWLIST doit être un tableau JSON de chaînes")
        return tuple(item for item in parsed if item.strip())
    return tuple(line for line in stripped.splitlines() if line.strip())


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
        secret_allowlist=_split_secret_allowlist_env(os.environ.get(_ENV_SECRET_ALLOWLIST)),
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
            if not isinstance(item, str) or item.strip() == "":
                raise ConfigError(f"« {key} » ne peut contenir que des chaînes non vides")
    for account_id in data.get("aws_account_ids", []):
        if not _ACCOUNT_ID_RE.match(account_id):
            raise ConfigError(
                f"identifiant de compte AWS invalide : {account_id!r} (attendu : 12 chiffres)"
            )
    return data


def _validate_semantic(config: RedactConfig) -> None:
    """Validation qui ne dépend pas de la source (fichier ou environnement) :
    appliquée une seule fois, sur la configuration fusionnée.
    """
    for account_id in config.aws_account_ids:
        if not _ACCOUNT_ID_RE.match(account_id):
            raise ConfigError(
                f"identifiant de compte AWS invalide : {account_id!r} (attendu : 12 chiffres)"
            )
    for username in config.local_usernames:
        if len(username.strip()) < _MIN_USERNAME_LENGTH:
            raise ConfigError(
                f"nom d'utilisateur trop court ou vide : {username!r} "
                f"(minimum {_MIN_USERNAME_LENGTH} caractères)"
            )
    for root in config.path_roots:
        if len(root.strip()) < _MIN_PATH_ROOT_LENGTH:
            raise ConfigError(
                f"racine de chemin trop courte ou vide : {root!r} "
                f"(minimum {_MIN_PATH_ROOT_LENGTH} caractères)"
            )
    for raw_pattern in config.secret_allowlist:
        _compile_allowlist_pattern(raw_pattern, strict=True)


def _compile_allowlist_pattern(raw: str, *, strict: bool) -> re.Pattern[str] | None:
    """Compile une entrée de `secret_allowlist`.

    `strict=True` (utilisé par `load_config`) lève `ConfigError` sur une
    regex invalide ou trop permissive. `strict=False` (utilisé au moment de
    `assert_no_secret`, en défense en profondeur pour une `RedactConfig`
    construite directement sans passer par `load_config`) ignore silencieusement
    une regex invalide plutôt que de faire planter le garde-fou — dans ce cas
    au pire l'exemption n'a pas lieu, ce qui ne peut jamais faire fuiter un
    secret.
    """
    try:
        compiled = re.compile(raw)
    except re.error as exc:
        if strict:
            raise ConfigError(f"secret_allowlist : regex invalide {raw!r} : {exc}") from exc
        return None
    if compiled.fullmatch("") is not None:
        if strict:
            raise ConfigError(
                f"secret_allowlist : regex trop permissive (accepte la chaîne vide) : {raw!r}"
            )
        return None
    if compiled.fullmatch(_BROAD_PATTERN_PROBE) is not None:
        if strict:
            raise ConfigError(
                f"secret_allowlist : regex trop permissive (accepte un texte arbitraire) : {raw!r}"
            )
        return None
    return compiled


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

    _validate_semantic(config)
    if require_account_ids and not config.aws_account_ids:
        raise ConfigError("aucun identifiant de compte AWS configuré (require_account_ids=True)")
    return config


# --------------------------------------------------------------------------
# Motifs (comptes AWS, chemins, adresses) — combinés en une seule alternance
# --------------------------------------------------------------------------

# Compte AWS entre deux-points d'un ARN : arn:aws:<service>:<region>:<compte>:<ressource>,
# y compris quand l'ARN se termine juste après l'identifiant (`arn:aws:iam::<id>`, fin de
# ligne) : `\b` accepte aussi bien un `:` qu'une fin de chaîne ou tout séparateur non-mot.
_ARN_ACCOUNT = r"(?<=:)\d{12}\b"
# Hôte de registre ECR : <compte>.dkr.ecr.<region>.amazonaws.com
_ECR_ACCOUNT = r"\d{12}(?=\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com)"
# URL de connexion à la console : <compte>.signin.aws.amazon.com
_SIGNIN_ACCOUNT = r"\d{12}(?=\.signin\.aws\.amazon\.com)"
# Nom de compartiment/ressource suffixé par le compte : <préfixe-alpha>-<compte>. Le
# préfixe doit contenir au moins deux lettres consécutives juste avant le tiret, pour ne
# pas masquer un horodatage ou un numéro de téléphone (`x-202609271230`, `+1-514555123456`).
_BUCKET_ACCOUNT = r"(?<=[a-z]{2}-)\d{12}(?!\d)"
# Champ "Account": "<compte>" (JSON, ex. sts get-caller-identity) ou Account: <compte> (texte)
_ACCOUNT_FIELD_QUOTED = r'(?<="Account": ")\d{12}(?=")'
_ACCOUNT_FIELD_PLAIN = r"(?<=Account: )\d{12}"

# Séparateur de chemin : une seule classe quantifiée, jamais de quantificateur
# imbriqué (`(?:\+|/)+` est exponentiel sur une longue suite d'antislashs).
_PATH_SEP = r"[\\/]+"

# Préfixe d'un chemin sous `Users` : lettre de lecteur (`C:`), lettre de lecteur
# posix précédée de `/mnt` (`/mnt/c`), ou lettre de lecteur posix seule (`/c`).
# Ces deux dernières formes sont gardées par un lookbehind qui exige qu'elles
# ne soient pas déjà collées à une lettre/chiffre/`/` : ça évite de reconnaître
# un `/c` au milieu d'une URL (`https://c/users/x`) ou d'un chemin
# (`a/c/users/x`) comme une lettre de lecteur.
_DRIVE_PREFIX = r"(?:[a-z]:|(?<![A-Za-z0-9/])/mnt/[a-z]|(?<![A-Za-z0-9/])/[a-z])"


def _user_home_body(config: RedactConfig) -> str:
    """Motif du chemin `Users/<nom>`, casse indifférente (appliqué avec
    `re.IGNORECASE` par l'appelant).

    Sans configuration, le nom s'arrête au premier séparateur, espace,
    virgule, point-virgule ou parenthèse fermante : un nom avec espace
    (`Bob Smith`) n'est donc reconnu qu'à moitié (`Bob`) et le reste de la
    phrase n'est pas absorbé. Si `local_usernames` contient un nom complet
    (avec espace), ce nom littéral est essayé en priorité : configuré, il est
    donc masqué en entier.
    """
    prefix = rf"(?:file:///)?{_DRIVE_PREFIX}{_PATH_SEP}users{_PATH_SEP}"
    generic_name = r"[^\\/\r\n\"',;)\s]+"
    configured = sorted(config.local_usernames, key=len, reverse=True)
    if configured:
        name_alt = "|".join(re.escape(name) for name in configured)
        tail = f"(?:{name_alt}|{generic_name})"
    else:
        tail = generic_name
    return prefix + tail


_EMAIL_BODY = r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

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
    body = _PATH_SEP.join(re.escape(segment) for segment in segments)
    if leading_sep:
        body = _PATH_SEP + body
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

    parts.append(rf"(?P<home>{_user_home_body(config)})")

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
    (ex. une adresse e-mail autorisée qui contiendrait ce nom). Aucun des
    motifs ne comporte de quantificateur imbriqué ni de partie locale
    d'adresse non ancrée : le temps d'exécution reste linéaire en la
    longueur de `text`, y compris sur une entrée pathologique.

    Idempotente : `redact(redact(x)) == redact(x)`.
    """
    resolved = config if config is not None else load_config()
    pattern = _compile_master_pattern(resolved)
    return pattern.sub(lambda m: _dispatch(m, resolved), text)


# --------------------------------------------------------------------------
# Garde-fou : détection de secrets vivants
# --------------------------------------------------------------------------

# Champ Lambda CodeSha256 : base64 d'un digest sha256 (32 octets), toujours
# exactement 44 caractères avec un `=` de bourrage. Format strict et lié à un
# nom de champ précis : contrairement à un préfixe générique `sha256:`, il ne
# peut pas servir à camoufler un secret arbitraire de longueur quelconque.
_CODE_SHA256_FIELD_RE = re.compile(r'(?i)codesha256["\']?\s*[:=]\s*["\']?[A-Za-z0-9+/]{43}=')

# Motifs explicites de secrets connus : indépendants de la longueur/l'entropie,
# évalués sur le texte BRUT (jamais après suppression d'un motif « sûr », pour
# qu'un préfixe comme `sha1-` ne puisse jamais servir à camoufler une clé
# `AKIA...` ou un autre secret explicite : `sha1-AKIA...` doit être détecté).
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

# Placeholders usuels de documentation/exemple : une affectation à l'une de ces
# valeurs (insensible à la casse) n'est jamais un vrai secret.
_PLACEHOLDER_VALUES = frozenset(
    {
        "redacted",
        "changeme",
        "change_me",
        "example",
        "xxx",
        "xxxxx",
        "placeholder",
        "todo",
        "fixme",
        "none",
        "null",
        "...",
        "<redacted>",
        "<changeme>",
        "<placeholder>",
        "<secret>",
        "<value>",
    }
)

# Affectation à un mot-clé sensible (SECRET, TOKEN, PASSWORD, PASS, PWD,
# API[_-]KEY), quel que soit le nom exact de la variable (`DB_PASSWORD`,
# `aws_secret_access_key`, `LANGFUSE_SECRET_KEY`...). La valeur exclut `<`
# (donc un gabarit `<redacted>` ne correspond déjà pas à la classe de
# caractères) et doit faire au moins 12 caractères pour écarter les valeurs
# courtes usuelles (`true`, `xxx`, un nom de variable voisin).
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b\w*(?:secret|token|passw(?:or)?d|pass|pwd|api[_-]?key)\w*"
    r"\s*[:=]\s*[\"']?([^\s\"'<]{12,})"
)


def _is_placeholder_value(value: str) -> bool:
    return value.strip().strip("'\"").lower() in _PLACEHOLDER_VALUES


# Jeton opaque générique : 40+ caractères d'un alphabet base64url/base64, avec
# padding `=` optionnel en fin. Frontières asymétriques : un jeton peut
# commencer par `/` ou `+` (fréquent en base64) ou suivre immédiatement un
# `=` (assignation `k=...`), mais ne peut pas être collé à un autre caractère
# du même alphabet (sinon on sous-détecterait tout jeton base64url contenant
# `_`/`-`, qui n'a pas de frontière `\b`).
_LONG_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{40,}={0,2}(?![A-Za-z0-9+/_-])")

# Longueurs hexadécimales jamais suspectes en elles-mêmes (un SHA de commit
# git fait toujours exactement 40 caractères) ou uniquement en contexte de
# digest connu (64 = sha256, 128 = sha512).
_HEX_ALWAYS_SAFE_LENGTH = 40
_HEX_DIGEST_LENGTHS = (64, 128)
_HEX_RUN_RE = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{32,}(?![0-9a-f])")
_DIGEST_CONTEXT_RE = re.compile(
    r"(?i)(?:sha1|sha256|sha512)\s*[:=-]\s*$|@sha256:\s*$|digest\b.{0,10}$|"
    r"codesha256[\"']?\s*[:=]\s*[\"']?$"
)
_DIGEST_CONTEXT_WINDOW = 40


def _has_digest_context(text: str, start: int) -> bool:
    window = text[max(0, start - _DIGEST_CONTEXT_WINDOW) : start]
    return bool(_DIGEST_CONTEXT_RE.search(window))


def _check_hex_policy(text: str) -> None:
    """Toute suite hexadécimale de 32+ caractères est suspecte, sauf :

    - exactement 40 caractères (SHA de commit git, toujours accepté) ;
    - exactement 64 ou 128 caractères **et** précédée d'un contexte de digest
      reconnu (`sha256:`, `sha512-`, `@sha256:`, le mot « digest », ou un
      champ `CodeSha256`).

    Un jeton de 32, 48, 96 caractères (ex. `secrets.token_hex(16/24/48)`), ou
    un hex de 64/128 caractères sans contexte de digest (`SECRET=<64 hex>`),
    est donc toujours détecté.
    """
    for match in _HEX_RUN_RE.finditer(text):
        run = match.group(0)
        length = len(run)
        if length == _HEX_ALWAYS_SAFE_LENGTH:
            continue
        if length in _HEX_DIGEST_LENGTHS and _has_digest_context(text, match.start()):
            continue
        raise SecretDetected(
            f"jeton hexadécimal opaque ({length} caractères) détecté à la position {match.start()}"
        )


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


def _looks_like_path_or_url(token: str) -> bool:
    """Un chemin/URL décomposé en 3+ segments courts, dont AUCUN segment
    individuel ne mélange lui-même majuscule+minuscule+chiffre, n'est pas un
    jeton opaque — ex. `tools/devlog/redact`, `subagents/agent-a1b2`.

    Volontairement conservateur (voir la discussion en revue de PR) : un vrai
    secret base64 contenant un ou deux `/` peut répartir ses trois classes de
    caractères sur plusieurs segments plutôt que les concentrer dans un seul,
    et échapper à ce test — c'est voulu, la détection d'un vrai secret prime
    toujours sur l'esthétique d'un rendu de journal. `secret_allowlist` reste
    le mécanisme sanctionné pour exempter un cas de coïncidence connu et
    précis (ex. une URL GitHub contenant un nom d'utilisateur mélangé).
    """
    segments = token.split("/")
    if len(segments) < 3 or any(len(segment) >= 40 for segment in segments):
        return False
    if any(_looks_random(segment) for segment in segments):
        return False
    # Aucun segment n'est individuellement « aléatoire » : signal supplémentaire
    # qu'il s'agit bien d'un chemin/URL composé de mots ou d'identifiants
    # distincts, pas d'un secret dont les classes de caractères seraient
    # réparties sur plusieurs segments (un vrai secret garde une densité de
    # transitions de casse élevée y compris par segment ; un identifiant de
    # type nom d'utilisateur ou mot-clé n'en a jamais plus d'une poignée).
    return all(_case_transition_ratio(segment) <= 0.2 for segment in segments if len(segment) >= 4)


def _case_transition_ratio(segment: str) -> float:
    if len(segment) < 2:
        return 0.0
    transitions = sum(
        1
        for a, b in zip(segment, segment[1:], strict=False)
        if a.isalpha() and b.isalpha() and a.islower() != b.islower()
    )
    return transitions / (len(segment) - 1)


def _blank(pattern: re.Pattern[str], text: str) -> str:
    return pattern.sub(lambda m: " " * len(m.group(0)), text)


def assert_no_secret(text: str, config: RedactConfig | None = None) -> None:
    """Lève `SecretDetected` si `text` contient une chaîne ressemblant à un
    secret vivant (clé d'API, jeton, identifiant de clé d'accès AWS, JWT, clé
    privée PEM, affectation de mot de passe, jeton hexadécimal opaque...).

    Ne déclenche jamais sur un identifiant public connu (SHA de commit,
    digest `sha256:`/`sha512-`/`CodeSha256` en contexte reconnu, identifiant
    sans mélange de casse+chiffres, chemin/URL décomposable en segments
    courts). `config.secret_allowlist` (regex, validées par `load_config`)
    permet d'exempter explicitement d'autres jetons génériques propres à un
    dépôt — jamais un détecteur explicite ci-dessus, ni un jeton hexadécimal
    hors politique : l'allowlist n'est consultée que pour le détecteur
    générique de jeton opaque, en `fullmatch` sur le jeton candidat.

    Le message d'erreur donne le type de secret détecté et sa position dans
    `text`, jamais sa valeur.
    """
    resolved = config if config is not None else RedactConfig.empty()

    # 1. Détecteurs explicites sur le texte BRUT : rien ne peut les contourner,
    # ni un préfixe « sûr » (sha1-, sha256:...), ni `secret_allowlist`.
    for label, pattern in _DANGEROUS_PATTERNS:
        match = pattern.search(text)
        if match:
            raise SecretDetected(f"{label} détectée à la position {match.start()}")

    match = _SECRET_ASSIGNMENT_RE.search(text)
    if match and not _is_placeholder_value(match.group(1)):
        raise SecretDetected(
            f"affectation à un mot-clé sensible (secret/token/password/pass/pwd/api_key) "
            f"détectée à la position {match.start()}"
        )

    # 2. Politique hexadécimale (indépendante de l'entropie : un hex pur n'a
    # jamais de majuscule, donc jamais capté par `_looks_random`).
    _check_hex_policy(text)

    # 3. Jeton opaque générique. `secret_allowlist` n'agit qu'ici, en
    # fullmatch sur le jeton candidat — jamais avant les étapes 1 et 2.
    scratch = _blank(_CODE_SHA256_FIELD_RE, text)
    allow_patterns = [
        compiled
        for raw in resolved.secret_allowlist
        if (compiled := _compile_allowlist_pattern(raw, strict=False)) is not None
    ]

    pos = 0
    while True:
        match = _LONG_TOKEN_RE.search(scratch, pos)
        if match is None:
            return
        token = match.group(0)
        if (
            not _looks_like_path_or_url(token)
            and _looks_random(token)
            and not any(pattern.fullmatch(token) for pattern in allow_patterns)
        ):
            raise SecretDetected(
                f"jeton opaque non identifié ({len(token)} caractères) "
                f"détecté à la position {match.start()}"
            )
        pos = match.end()
