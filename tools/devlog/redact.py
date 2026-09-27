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
en corrompe un autre déjà appliqué. Chaque motif est écrit sans
quantificateur imbriqué ni ambigu (`[\\/]++`, possessif — jamais
`(?:\\+|/)+` ni même `[\\/]+` répété en tête de motif) et les motifs non
ancrés (adresse e-mail) portent une garde de début (lookbehind) : c'est ce
qui garantit un temps linéaire même sur une entrée pathologique (longue
suite d'antislashs, texte d'un mégaoctet sans arobase...).

Deux niveaux de détection de secrets
--------------------------------------
`assert_no_secret(text)` (**bloquant**, lève `SecretDetected`) ne couvre que
des motifs à haute confiance, qui ne se produisent essentiellement jamais
dans du code ou de la prose ordinaires : clé privée PEM, identifiant de clé
d'accès AWS (`AKIA`/`ASIA`/`AROA`/`AIDA`) et affectation
`aws_secret_access_key=`, jeton GitHub (`ghp_`/`gho_`/`ghs_`/`ghu_`/`ghr_`/
`github_pat_`), clé Langfuse (`sk-lf-`/`pk-lf-`), clé de style OpenAI/
Anthropic (`sk-proj-`/`sk-ant-`), JWT (trois segments base64url avec un
en-tête JSON `eyJ`). `secret_allowlist` ne peut **jamais** supprimer une
détection de ce niveau.

`find_suspects(text, config=None) -> list[Suspect]` (**non bloquant**, ne
lève jamais) couvre les motifs heuristiques, plus sujets aux faux positifs
sur du code ou de la prose réels : jeton opaque générique à forte entropie,
hexadécimal long hors contexte de digest connu, affectation à un mot-clé
sensible (secret/jeton/mot de passe/clé). Chaque `Suspect` porte uniquement
un type, une position (`start`/`end`), et un aperçu masqué (`ab…(40)…yz`) —
jamais la valeur en clair. `secret_allowlist` ne s'applique qu'ici. Ces
suspects sont destinés à un rapport de relecture local (jamais publié tel
quel), pas à faire échouer le rendu : avec des centaines de rapports, un
détecteur heuristique bloquant produit trop de faux positifs pour être
utilisable.

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
     considérées comme sûres par `find_suspects` (jamais par
     `assert_no_secret`). Une regex peut contenir des virgules : cette
     variable n'est **jamais** découpée sur `,`. Elle accepte soit un tableau
     JSON de chaînes (`["motif1", "motif2"]`), soit une regex par ligne
     (séparateur `\n`).
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
   vide, ou qui accepte un texte arbitraire ou un jeton de forme réaliste
   (base64/hex/base64url de longueur usuelle) trop large (ex. `.*`, `\\S+`,
   `[\\w+/-]+`) lèvent tous `ConfigError`. Un fichier JSON syntaxiquement
   invalide lève `json.JSONDecodeError` (non interceptée). Si
   `DEVLOG_REDACT_CONFIG_PATH` est défini explicitement et que le fichier est
   absent, `ConfigError` est levée ; si aucune variable d'environnement n'est
   définie et que le fichier par défaut est absent, la configuration est
   simplement vide (seuls les motifs génériques agissent).

Sans configuration, seuls les motifs génériques (ARN, hôte ECR, compartiment
`<préfixe-alpha>-<compte>`, champ `"Account": "<compte>"`, URL
`<compte>.signin...`, forme d'adresse e-mail, chemin `Users/<nom>`) sont
masqués.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ConfigError",
    "RedactConfig",
    "SecretDetected",
    "Suspect",
    "assert_no_secret",
    "find_suspects",
    "load_config",
    "redact",
]


class SecretDetected(Exception):
    """Levée quand un texte contient une chaîne ressemblant à un secret vivant
    à haute confiance (voir `assert_no_secret`)."""


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


def _make_broad_pattern_probes() -> tuple[str, ...]:
    """Jetons fictifs de forme réaliste, utilisés pour vérifier qu'une entrée
    de `secret_allowlist` n'est pas trop permissive (voir
    `_compile_allowlist_pattern`).

    Plusieurs alphabets sont couverts séparément (pas seulement un mélange
    avec `_`/`-`) : une classe qui exclut `_`/`-` (`[A-Za-z0-9+/=]+`,
    `[0-9a-f]+`, `[A-Za-z0-9]+`) doit quand même être rejetée si elle
    reconnaît un jeton en base64 pur, en hexadécimal pur, ou alphanumérique
    pur — pas seulement le mélange le plus général.
    """
    mixed_cycle = "Ab3Cd5Ef7Gh9+/_-"  # mélange lettres/chiffres/+//_/- délibéré
    base64_cycle = "Ab3Cd5Ef7Gh9+/"  # base64 pur : sans `_` ni `-`
    alnum_cycle = "Ab3Cd5Ef7Gh9"  # alphanumérique pur : sans `_`, `-`, `+`, `/`
    hex_cycle = "ab12cd34ef56"  # hexadécimal pur (minuscules)

    def _take(cycle: str, length: int) -> str:
        return (cycle * (length // len(cycle) + 1))[:length]

    return (
        "aB3-x_/9.zK8 Q7" * 20,  # texte arbitraire diversifié (avec espaces/points)
        _take(mixed_cycle, 40),  # base64 « clé » de 40 caractères, avec _/-
        _take(mixed_cycle, 43),  # base64url de 43 caractères (jeton urlsafe)
        _take(mixed_cycle, 44) + "=",  # base64 de 44 caractères avec bourrage
        _take(mixed_cycle, 64),  # hex/b64 de 64 caractères, avec _/-
        _take(base64_cycle, 40),  # clé base64 PURE (sans _/-) de 40 caractères
        _take(base64_cycle, 44) + "=",  # digest base64 PUR de 44 caractères
        _take(alnum_cycle, 40),  # jeton alphanumérique PUR de 40 caractères
        _take(hex_cycle, 48),  # hexadécimal PUR de 48 caractères
        _take(hex_cycle, 64),  # hexadécimal PUR de 64 caractères (digest sha256)
    )


_BROAD_PATTERN_PROBES = _make_broad_pattern_probes()


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
    """Compile une entrée de `secret_allowlist` (utilisée uniquement par
    `find_suspects`, jamais par `assert_no_secret`).

    `strict=True` (utilisé par `load_config`) lève `ConfigError` sur une
    regex invalide ou trop permissive — y compris une classe de caractères
    générique comme `\\S+`, `[^ ]+` ou `[\\w+/-]+`, qui reconnaîtrait
    n'importe quel jeton de forme réaliste (voir `_BROAD_PATTERN_PROBES`).
    `strict=False` (utilisé par `find_suspects`, en défense en profondeur
    pour une `RedactConfig` construite directement sans passer par
    `load_config`) ignore silencieusement une regex invalide ou trop
    permissive plutôt que de faire planter le garde-fou ou de neutraliser la
    détection générique.
    """
    try:
        compiled = re.compile(raw)
    except re.error as exc:
        if strict:
            raise ConfigError(f"secret_allowlist : regex invalide {raw!r} : {exc}") from exc
        return None
    for probe in ("", *_BROAD_PATTERN_PROBES):
        if compiled.fullmatch(probe) is not None:
            if strict:
                raise ConfigError(
                    f"secret_allowlist : regex trop permissive "
                    f"(reconnaît un texte arbitraire ou un jeton de forme réaliste) : {raw!r}"
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

# Séparateur de chemin : une seule classe quantifiée de façon POSSESSIVE
# (`++`, jamais `+` seul) : sans ça, une racine configurée commençant par un
# séparateur (`/d/DEV`) redevient quadratique sur une longue suite de
# séparateurs, le moteur réessayant `[\/]+` à chaque position plutôt que de
# s'engager sur le plus long match trouvé.
_PATH_SEP = r"[\\/]++"

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

    Le séparateur (`_PATH_SEP`) est possessif, mais ça ne suffit pas à soi
    seul quand la racine commence PAR un séparateur (`/d/DEV`) : sans garde
    supplémentaire, ce motif peut alors commencer à correspondre à N'IMPORTE
    QUELLE position d'une longue suite de séparateurs, et échouer à chacune
    d'elles après avoir consommé (de façon possessive, donc en un seul bloc,
    mais quand même en O(reste)) tout ce qui suit — ce qui redevient
    quadratique sur l'ensemble de la suite. Une garde de début de chemin
    (début de chaîne, espace, guillemet, `(` ou `=`) n'autorise cette
    tentative qu'à un véritable début de chemin, jamais au milieu d'un
    segment relatif (`a/d/DEV/b` reste intact : le `/d/DEV` y est précédé de
    `a`, pas d'un de ces caractères), ramenant aussi le coût total à O(n).
    """
    leading_sep = root[:1] in "\\/"
    segments = [segment for segment in re.split(r"[\\/]+", root) if segment]
    body = _PATH_SEP.join(re.escape(segment) for segment in segments)
    if leading_sep:
        body = r"(?:\A|(?<=[\s\"'(=]))" + _PATH_SEP + body
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
    qu'une fois. Aucun des motifs ne comporte de quantificateur imbriqué, de
    quantificateur non possessif en tête pouvant réessayer sur une longue
    suite de séparateurs, ni de partie locale d'adresse non ancrée : le temps
    d'exécution reste linéaire en la longueur de `text`, y compris sur une
    entrée pathologique (longue suite d'antislashs, avec ou sans racine
    configurée).

    Idempotente : `redact(redact(x)) == redact(x)`.
    """
    resolved = config if config is not None else load_config()
    pattern = _compile_master_pattern(resolved)
    return pattern.sub(lambda m: _dispatch(m, resolved), text)


# --------------------------------------------------------------------------
# Niveau 1 — détecteurs à haute confiance (bloquants)
# --------------------------------------------------------------------------

# Motifs à haute confiance : ils ne se produisent essentiellement jamais dans
# du code ou de la prose ordinaires. Évalués sur le texte BRUT (jamais après
# suppression d'un motif « sûr », pour qu'un préfixe comme `sha1-` ne puisse
# jamais servir à camoufler une clé `AKIA...`). `secret_allowlist` ne
# s'applique JAMAIS à ce niveau.
_BLOCKING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "clé privée PEM",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
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
        "clé d'API (préfixe sk-/pk-lf-, sk-proj- ou sk-ant-)",
        re.compile(r"(?<![A-Za-z0-9_-])(?:sk|pk)-(?:lf|proj|ant)-[A-Za-z0-9_-]+"),
    ),
    (
        "clé d'API OpenAI historique (sk-...)",
        # "sk-" suivi de 40+ caractères alphanumériques SANS tiret ni tiret bas :
        # ne recoupe jamais sk-lf-/sk-proj-/sk-ant- (qui ont un `-` juste après
        # le sous-préfixe, donc moins de 40 caractères alphanumériques d'affilée).
        re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9]{40,}(?![A-Za-z0-9_-])"),
    ),
    (
        "jeton Slack (xox...)",
        re.compile(r"(?<![A-Za-z0-9_-])xox[abprs]-[0-9A-Za-z-]{10,}(?![A-Za-z0-9_-])"),
    ),
    (
        "clé d'API Google (AIza...)",
        re.compile(r"(?<![A-Za-z0-9_-])AIza[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])"),
    ),
    (
        "JWT",
        re.compile(r"(?<![A-Za-z0-9_-])eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+(?![A-Za-z0-9_-])"),
    ),
)

# Formats de secrets AWS propres à ce projet : traités à part (pas dans
# `_BLOCKING_PATTERNS`) car la valeur n'est vérifiée qu'en Python, jamais par
# une classe de caractères imbriquée dans la regex (ça évite tout risque de
# retour arrière ambigu) — le motif lui-même reste simple et borné.
#
# Le séparateur `(?:[:=]|\s)` couvre à la fois `aws_secret_access_key=...`
# (env/.ini), `"SecretAccessKey": "..."` (JSON de sts/get-session-token/
# export-credentials) et `aws configure set aws_secret_access_key ...` (CLI,
# séparateur espace). La valeur n'a besoin QUE d'être plausible dans ce
# contexte explicite (pas tout en minuscules — un vrai secret aléatoire l'est
# rarement, un gabarit répété l'est presque toujours) : contrairement au
# niveau heuristique, on n'exige pas ici le mélange des trois classes.
_AWS_SECRET_KEY_VALUE_RE = re.compile(
    r"(?i:aws_?secret_?access_?key|secretaccesskey)[\"']?\s*(?:[:=]|\s)\s*[\"']?"
    r"([A-Za-z0-9+/]{40})(?![A-Za-z0-9+/=])"
)
# Jeton de session AWS : toujours beaucoup plus long qu'une clé secrète (au
# moins une centaine de caractères base64 en pratique). Détecté par sa seule
# présence dans ce contexte, sans exigence de contenu supplémentaire.
_AWS_SESSION_TOKEN_RE = re.compile(
    r"(?i:aws_?session_?token|sessiontoken)[\"']?\s*(?:[:=]|\s)\s*[\"']?"
    r"[A-Za-z0-9+/]{100,4000}={0,2}(?![A-Za-z0-9+/=])"
)


def _find_aws_secret_access_key_leak(text: str) -> re.Match[str] | None:
    for match in _AWS_SECRET_KEY_VALUE_RE.finditer(text):
        if not match.group(1).islower():
            return match
    return None


def assert_no_secret(text: str) -> None:
    """Lève `SecretDetected` si `text` contient une chaîne ressemblant à un
    secret vivant **à haute confiance** : clé privée PEM, identifiant de clé
    d'accès AWS, clé/jeton de session `aws_secret_access_key`/
    `aws_session_token` (env, JSON de `sts`, ou CLI `aws configure set`),
    jeton GitHub, clé Langfuse/OpenAI (actuelle ou historique)/Anthropic,
    jeton Slack, clé Google, ou JWT.

    Volontairement restreinte à des motifs qui ne se produisent
    essentiellement jamais dans du code ou de la prose ordinaires : c'est le
    niveau **bloquant**, qui ne doit jamais faire échouer le rendu d'un
    rapport légitime. Les motifs heuristiques (jeton opaque générique,
    hexadécimal long, affectation à un mot-clé sensible), plus sujets aux
    faux positifs, sont couverts par `find_suspects` (non bloquant) — jamais
    ici. Aucune configuration, aucune `secret_allowlist`, ne peut supprimer
    une détection de ce niveau.

    Le message d'erreur donne le type de secret détecté et sa position dans
    `text`, jamais sa valeur.
    """
    for label, pattern in _BLOCKING_PATTERNS:
        match = pattern.search(text)
        if match:
            raise SecretDetected(f"{label} détectée à la position {match.start()}")

    aws_secret_match = _find_aws_secret_access_key_leak(text)
    if aws_secret_match:
        raise SecretDetected(
            f"clé secrète AWS (aws_secret_access_key / SecretAccessKey) détectée "
            f"à la position {aws_secret_match.start()}"
        )

    session_match = _AWS_SESSION_TOKEN_RE.search(text)
    if session_match:
        raise SecretDetected(
            f"jeton de session AWS (aws_session_token / SessionToken) détecté "
            f"à la position {session_match.start()}"
        )

    aws_secret_match = _find_aws_secret_access_key_leak(text)
    if aws_secret_match:
        raise SecretDetected(
            f"clé secrète AWS (aws_secret_access_key=...) détectée à la position "
            f"{aws_secret_match.start()}"
        )


# --------------------------------------------------------------------------
# Niveau 2 — détecteurs heuristiques (suspects, non bloquants)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Suspect:
    """Un signal heuristique trouvé par `find_suspects` : jamais la valeur en
    clair, seulement son type, sa position dans le texte, et un aperçu masqué
    (`ab…(40)…yz`).
    """

    kind: str
    start: int
    end: int
    preview: str


def _make_preview(value: str) -> str:
    """Aperçu totalement opaque : ni le début ni la fin de `value`
    n'apparaissent (aucune sous-chaîne de la valeur, si courte soit-elle).
    Seules la longueur et une empreinte sha256 (8 caractères hexadécimaux)
    figurent, pour recouper deux occurrences de la même valeur sans jamais
    exposer un seul de ses caractères.
    """
    length = len(value)
    fingerprint = hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()[:8]
    return f"…({length})… #{fingerprint}"


# Digests connus, de longueur exacte, dans leur contexte précis : jamais des
# secrets, quelle que soit leur apparence. Contrairement à un préfixe
# générique non borné (l'ancienne source d'un contournement), la longueur
# EXACTE empêche qu'un vrai secret plus long se fasse passer pour l'un
# d'eux.
_SAFE_DIGEST_PATTERNS: tuple[re.Pattern[str], ...] = (
    # SHA256:<base64 43 ou 44> (empreinte SSH), sha256-<base64> (rare). Le
    # verrou `(?![A-Za-z0-9+/=])` final est essentiel : sans lui, un secret
    # plus long préfixé de "sha256:" ne perdrait que ses 43-44 premiers
    # caractères (toujours ≥ 40 restants après troncature, donc toujours
    # détecté) OU, pire, pourrait tomber sous le seuil après troncature —
    # exactement le contournement que la longueur exacte doit empêcher.
    re.compile(r"(?i)sha256[:=-][A-Za-z0-9+/]{43,44}=?(?![A-Za-z0-9+/=])"),
    # sha512-<base64 86 ou 88> (intégrité npm)
    re.compile(r"(?i)sha512[:=-][A-Za-z0-9+/]{86,88}={0,2}(?![A-Za-z0-9+/=])"),
    # Terraform : source_code_hash = "<base64 43 ou 44>" (digest sha256 d'un zip Lambda)
    re.compile(
        r'(?i)source_code_hash["\']?\s*[:=]\s*["\']?[A-Za-z0-9+/]{43,44}=?(?![A-Za-z0-9+/=])'
    ),
    # Lambda : "CodeSha256": "<base64 43 ou 44>"
    re.compile(r'(?i)codesha256["\']?\s*[:=]\s*["\']?[A-Za-z0-9+/]{43,44}=?(?![A-Za-z0-9+/=])'),
)

# Jeton opaque générique : 40+ caractères d'un alphabet base64url/base64, avec
# padding `=` optionnel en fin. Frontières asymétriques : un jeton peut
# commencer par `/` ou `+` (fréquent en base64) ou suivre immédiatement un
# `=` (assignation `k=...`), mais ne peut pas être collé à un autre caractère
# du même alphabet (sinon on sous-détecterait tout jeton base64url contenant
# `_`/`-`, qui n'a pas de frontière `\b`).
_LONG_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{40,}={0,2}(?![A-Za-z0-9+/_-])")

# Politique hexadécimale : en dessous de 41 caractères, jamais suspect (un
# ETag S3/md5, un UUID sans tirets, un RequestId AWS font tous 32 caractères).
# 64 et 128 (longueurs de digest sha256/sha512) ne sont suspects que hors
# contexte de digest reconnu. Toute autre longueur (41-63, 65-127, 129+) est
# toujours suspecte : ce n'est ni un SHA de commit (40, exclu par le seuil
# lui-même) ni une longueur de digest usuelle.
_HEX_SUSPECT_MIN_LENGTH = 41
_HEX_DIGEST_LENGTHS = (64, 128)
_HEX_RUN_RE = re.compile(rf"(?i)(?<![0-9a-f])[0-9a-f]{{{_HEX_SUSPECT_MIN_LENGTH},}}(?![0-9a-f])")
_DIGEST_CONTEXT_BEHIND_RE = re.compile(
    r"(?i)(?:sha1|sha256|sha512)\s*[:=-]\s*$|@sha256:\s*$|digest\b.{0,10}$|"
    r"codesha256[\"']?\s*[:=]\s*[\"']?$"
)
# sha256sum/md5sum : "<hex>  fichier" (deux espaces puis un nom de fichier).
_DIGEST_CONTEXT_AHEAD_RE = re.compile(r"^ {2}\S")
_DIGEST_CONTEXT_WINDOW = 40


def _has_digest_context(text: str, start: int, end: int) -> bool:
    behind = text[max(0, start - _DIGEST_CONTEXT_WINDOW) : start]
    if _DIGEST_CONTEXT_BEHIND_RE.search(behind):
        return True
    ahead = text[end : end + _DIGEST_CONTEXT_WINDOW]
    return bool(_DIGEST_CONTEXT_AHEAD_RE.match(ahead))


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


def _case_transition_ratio(segment: str) -> float:
    if len(segment) < 2:
        return 0.0
    transitions = sum(
        1
        for a, b in zip(segment, segment[1:], strict=False)
        if a.isalpha() and b.isalpha() and a.islower() != b.islower()
    )
    return transitions / (len(segment) - 1)


def _looks_like_path_or_url(token: str) -> bool:
    """Un chemin/URL décomposé en 3+ segments courts, dont AUCUN segment
    individuel ne mélange lui-même majuscule+minuscule+chiffre et n'a une
    densité de transitions de casse élevée, n'est pas un jeton opaque — ex.
    `tools/devlog/redact`, `subagents/agent-a1b2`.

    Volontairement conservateur : un vrai secret base64 contenant un ou deux
    `/` peut répartir ses trois classes de caractères sur plusieurs segments
    plutôt que les concentrer dans un seul, et échapper à ce test — voulu, la
    détection d'un vrai secret prime sur l'esthétique d'un rendu de journal.
    `secret_allowlist` reste le mécanisme pour exempter un cas de coïncidence
    connu et précis (ex. une URL GitHub avec un nom d'utilisateur mélangé).
    """
    segments = token.split("/")
    if len(segments) < 3 or any(len(segment) >= 40 for segment in segments):
        return False
    if any(_looks_random(segment) for segment in segments):
        return False
    return all(_case_transition_ratio(segment) <= 0.2 for segment in segments if len(segment) >= 4)


def _blank(pattern: re.Pattern[str], text: str) -> str:
    return pattern.sub(lambda m: " " * len(m.group(0)), text)


# --- Affectation à un mot-clé sensible ---------------------------------
#
# Approche « repérer puis vérifier » (jamais un unique motif monolithique
# avec un `\w*` en tête, qui redémarre son balayage à chaque caractère d'une
# longue suite comme "secret_"*20000 et devient quadratique) : on énumère
# d'abord chaque opérateur d'affectation (`:`/`=`, un caractère, linéaire),
# puis on regarde en arrière dans une fenêtre BORNÉE si le mot-clé termine
# immédiatement ce qui précède, et en avant si la valeur est un littéral
# plausible. Chaque étape est O(1) par opérateur trouvé : l'ensemble reste
# O(n).
_ASSIGNMENT_OP_RE = re.compile(r"[:=]")
# Le mot-clé doit TERMINER l'identifiant (pas de `\w*` final) : "tokens",
# "passthrough_behavior", "secret_id" ne correspondent donc pas. « pass »
# seul est exclu (trop de faux positifs : « passe », « passthrough »,
# « bypass »...).
_ASSIGNMENT_KEYWORD_RE = re.compile(
    r"(?i)(?:secret(?:_access)?_key|secret|token|passw(?:or)?d|pwd|api[_-]?key)\s*\Z"
)
_ASSIGNMENT_KEYWORD_WINDOW = 40
# La valeur doit être un littéral : entre guillemets (au moins 16 caractères
# hors espace), ou nu sans caractère de déréférencement/expression
# (`(`, `[`, `.`, `$`, `/`, `{`) — ce qui exclut par construction
# `request.headers[...]`, `get_password_from_vault()`, `${...}`,
# `settings.SECRET_KEY`, `os.environ.get(...)`, `/etc/...`. Bornée à 256
# caractères (P2) : sans borne haute, la branche nue — qui n'excluait pas
# `=` — rebalayait tout le reste d'une suite comme `"secret="*n` à CHAQUE
# opérateur trouvé, ce qui devenait quadratique. `=` est désormais exclu de
# la classe nue (un littéral ne contient normalement pas le caractère
# d'affectation lui-même), ce qui suffit à elle seule à borner le travail à
# quelques caractères sur ce cas précis ; la borne haute protège aussi les
# autres suites pathologiques (`token=aB1aB1...`).
_ASSIGNMENT_VALUE_RE = re.compile(
    r"""\s*(?:"([^"\s]{16,256})"|'([^'\s]{16,256})'|([^\s"'()\[\]{}<>$./,;=]{16,256}))"""
)


def _iter_secret_assignment_values(text: str) -> list[tuple[int, int, str]]:
    """Renvoie `(start, end, value)` pour chaque affectation à un mot-clé
    sensible dont la valeur est un littéral opaque plausible (mélange
    majuscule/minuscule/chiffre) — jamais une référence de code ni un
    gabarit court.
    """
    found: list[tuple[int, int, str]] = []
    for op_match in _ASSIGNMENT_OP_RE.finditer(text):
        op_pos = op_match.start()
        window = text[max(0, op_pos - _ASSIGNMENT_KEYWORD_WINDOW) : op_pos]
        if not _ASSIGNMENT_KEYWORD_RE.search(window):
            continue
        value_match = _ASSIGNMENT_VALUE_RE.match(text, op_pos + 1)
        if not value_match:
            continue
        quoted = value_match.group(1)
        if quoted is None:
            quoted = value_match.group(2)
        value = quoted if quoted is not None else value_match.group(3)
        if not _looks_random(value):
            continue
        found.append((op_pos, value_match.end(), value))
    return found


def find_suspects(text: str, config: RedactConfig | None = None) -> list[Suspect]:
    """Renvoie les signaux heuristiques (non bloquants) trouvés dans `text` :
    jeton opaque générique à forte entropie, hexadécimal long hors contexte
    de digest connu, affectation à un mot-clé sensible.

    Chaque `Suspect` ne porte qu'un type, une position, et un aperçu masqué —
    jamais la valeur en clair. `config.secret_allowlist` (regex, validées par
    `load_config`) exempte explicitement un motif propre à un dépôt ; une
    regex construite hors `load_config` et invalide ou trop permissive est
    ignorée sans erreur (au pire l'exemption n'a pas lieu). Destiné à un
    rapport de relecture local, jamais publié tel quel — ces suspects ne
    font jamais échouer le rendu (voir `assert_no_secret` pour les
    détecteurs bloquants).
    """
    resolved = config if config is not None else RedactConfig.empty()
    allow_patterns = [
        compiled
        for raw in resolved.secret_allowlist
        if (compiled := _compile_allowlist_pattern(raw, strict=False)) is not None
    ]

    def _is_allowlisted(value: str) -> bool:
        return any(pattern.fullmatch(value) for pattern in allow_patterns)

    suspects: list[Suspect] = []

    for match in _HEX_RUN_RE.finditer(text):
        run = match.group(0)
        length = len(run)
        if length in _HEX_DIGEST_LENGTHS and _has_digest_context(text, match.start(), match.end()):
            continue
        if _is_allowlisted(run):
            continue
        suspects.append(Suspect("hexadecimal", match.start(), match.end(), _make_preview(run)))

    scratch = text
    for safe_pattern in _SAFE_DIGEST_PATTERNS:
        scratch = _blank(safe_pattern, scratch)
    pos = 0
    while True:
        match = _LONG_TOKEN_RE.search(scratch, pos)
        if match is None:
            break
        token = match.group(0)
        if (
            not _looks_like_path_or_url(token)
            and _looks_random(token)
            and not _is_allowlisted(token)
        ):
            suspects.append(Suspect("jeton", match.start(), match.end(), _make_preview(token)))
        pos = match.end()

    for start, end, value in _iter_secret_assignment_values(text):
        if _is_allowlisted(value):
            continue
        suspects.append(Suspect("affectation", start, end, _make_preview(value)))

    suspects.sort(key=lambda s: s.start)
    return suspects
