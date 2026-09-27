"""Masquage déterministe pour le journal de développement public.

Ce module ne contient aucune donnée privée en dur (identifiant de compte AWS,
adresse e-mail personnelle, nom d'utilisateur local) : ces valeurs sont
**configurables**, jamais codées ici. Le module fournit uniquement des motifs
génériques (forme d'un ARN, d'un hôte ECR, d'une adresse e-mail, d'un chemin
sous `Users`) qui fonctionnent sans aucune configuration, et une couche de
configuration optionnelle pour les identifiants propres à ce dépôt.

Configuration
--------------
La configuration (`RedactConfig`) peut être construite explicitement (c'est
ce que font les tests, avec des valeurs fictives), ou chargée par
`load_config()` à partir de, dans l'ordre de priorité :

1. des variables d'environnement (listes séparées par des virgules) :
   - `DEVLOG_REDACT_AWS_ACCOUNT_IDS` : identifiants de compte AWS (12 chiffres)
     à masquer même hors contexte ARN/ECR ;
   - `DEVLOG_REDACT_EMAIL_ALLOWLIST` : adresses e-mail à conserver telles
     quelles (en plus des domaines de test et des adresses noreply GitHub,
     toujours autorisés) ;
   - `DEVLOG_REDACT_LOCAL_USERNAMES` : noms d'utilisateur locaux (Windows /
     Git Bash) à masquer même hors d'un chemin `Users/...` ;
   - `DEVLOG_REDACT_PATH_ROOTS` : racines de chemins locaux (ex.
     `D:\\DEV`, `/d/DEV`) à remplacer par `<poste>`.
2. un fichier JSON local, non suivi par git, dont le chemin est
   `DEVLOG_REDACT_CONFIG_PATH` ou par défaut
   `~/.claude/devlog-private/redact.json`, de la forme :

   ```json
   {
     "aws_account_ids": ["111111111111"],
     "email_allowlist": ["job@example.org"],
     "local_usernames": ["swond"],
     "path_roots": ["D:\\\\DEV", "/d/DEV"]
   }
   ```

Les deux sources sont fusionnées (union). Aucune valeur par défaut non vide
n'est fournie par ce module : sans configuration, seuls les motifs génériques
(ARN, hôte ECR, forme d'adresse e-mail, chemin `Users/<nom>`) sont masqués.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "RedactConfig",
    "SecretDetected",
    "assert_no_secret",
    "load_config",
    "redact",
]


class SecretDetected(Exception):
    """Levée quand un texte contient une chaîne ressemblant à un secret vivant."""


_ENV_ACCOUNT_IDS = "DEVLOG_REDACT_AWS_ACCOUNT_IDS"
_ENV_EMAIL_ALLOWLIST = "DEVLOG_REDACT_EMAIL_ALLOWLIST"
_ENV_LOCAL_USERNAMES = "DEVLOG_REDACT_LOCAL_USERNAMES"
_ENV_PATH_ROOTS = "DEVLOG_REDACT_PATH_ROOTS"
_ENV_CONFIG_PATH = "DEVLOG_REDACT_CONFIG_PATH"
_DEFAULT_CONFIG_PATH = Path.home() / ".claude" / "devlog-private" / "redact.json"

_ACCOUNT_MASK = "<compte-aws>"
_EMAIL_MASK = "<adresse>"
_HOME_MASK = "~"
_PATH_MASK = "<poste>"

# Domaines toujours considérés comme fictifs (fixtures de test) : jamais masqués.
_TEST_EMAIL_DOMAINS = frozenset({"example.com", "evil.com", "corp.com"})


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

    @staticmethod
    def empty() -> RedactConfig:
        return RedactConfig()

    def merge(self, other: RedactConfig) -> RedactConfig:
        return RedactConfig(
            aws_account_ids=self.aws_account_ids | other.aws_account_ids,
            email_allowlist=self.email_allowlist | other.email_allowlist,
            local_usernames=self.local_usernames | other.local_usernames,
            path_roots=tuple(dict.fromkeys((*self.path_roots, *other.path_roots))),
        )


def _config_from_env() -> RedactConfig:
    return RedactConfig(
        aws_account_ids=frozenset(_split_csv(os.environ.get(_ENV_ACCOUNT_IDS))),
        email_allowlist=frozenset(_split_csv(os.environ.get(_ENV_EMAIL_ALLOWLIST))),
        local_usernames=frozenset(_split_csv(os.environ.get(_ENV_LOCAL_USERNAMES))),
        path_roots=_split_csv(os.environ.get(_ENV_PATH_ROOTS)),
    )


def _config_from_file(path: Path) -> RedactConfig:
    if not path.is_file():
        return RedactConfig.empty()
    data = json.loads(path.read_text(encoding="utf-8"))
    return RedactConfig(
        aws_account_ids=frozenset(data.get("aws_account_ids", [])),
        email_allowlist=frozenset(data.get("email_allowlist", [])),
        local_usernames=frozenset(data.get("local_usernames", [])),
        path_roots=tuple(data.get("path_roots", [])),
    )


def load_config() -> RedactConfig:
    """Charge la configuration depuis l'environnement puis le fichier local.

    N'est jamais appelée implicitement par les tests (qui passent toujours une
    `RedactConfig` explicite avec des valeurs fictives) ; sert uniquement aux
    appelants réels (ex. `render.py`, futur).
    """
    config_path = Path(os.environ.get(_ENV_CONFIG_PATH, str(_DEFAULT_CONFIG_PATH)))
    return _config_from_file(config_path).merge(_config_from_env())


# --------------------------------------------------------------------------
# Identifiants de compte AWS
# --------------------------------------------------------------------------

_ARN_ACCOUNT_RE = re.compile(r"(?<=:)\d{12}(?=:)")
_ECR_HOST_RE = re.compile(r"\b\d{12}(?=\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com\b)")


def _redact_aws_accounts(text: str, config: RedactConfig) -> str:
    # Motifs génériques : n'importe quel identifiant à 12 chiffres dans un
    # contexte d'ARN (`arn:aws:...:<id>:...`) ou d'hôte ECR, indépendamment de
    # toute configuration.
    text = _ARN_ACCOUNT_RE.sub(_ACCOUNT_MASK, text)
    text = _ECR_HOST_RE.sub(_ACCOUNT_MASK, text)
    # Identifiants configurés : masqués même hors contexte ARN/ECR (occurrence
    # « nue »).
    for account_id in config.aws_account_ids:
        text = re.sub(rf"\b{re.escape(account_id)}\b", _ACCOUNT_MASK, text)
    return text


# --------------------------------------------------------------------------
# Adresses e-mail
# --------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_GITHUB_NOREPLY_RE = re.compile(
    r"^([0-9]+\+)?[A-Za-z0-9._-]+@users\.noreply\.github\.com$|^noreply@github\.com$"
)


def _is_allowed_email(address: str, config: RedactConfig) -> bool:
    if _GITHUB_NOREPLY_RE.match(address):
        return True
    if address in config.email_allowlist:
        return True
    domain = address.rsplit("@", 1)[-1].lower()
    return domain in _TEST_EMAIL_DOMAINS


def _redact_emails(text: str, config: RedactConfig) -> str:
    def _replace(match: re.Match[str]) -> str:
        address = match.group(0)
        return address if _is_allowed_email(address, config) else _EMAIL_MASK

    return _EMAIL_RE.sub(_replace, text)


# --------------------------------------------------------------------------
# Chemins locaux
# --------------------------------------------------------------------------

# `C:\Users\<nom>` (et toute autre lettre de lecteur) -> `~`
_WINDOWS_USER_HOME_RE = re.compile(r"[A-Za-z]:\\+Users\\+[^\\\s\"']+")
# `/c/Users/<nom>` (Git Bash) -> `~`
_GITBASH_USER_HOME_RE = re.compile(r"/[A-Za-z]/Users/[^/\s\"']+")


def _redact_paths(text: str, config: RedactConfig) -> str:
    text = _WINDOWS_USER_HOME_RE.sub(_HOME_MASK, text)
    text = _GITBASH_USER_HOME_RE.sub(_HOME_MASK, text)
    for username in config.local_usernames:
        # Occurrence du nom d'utilisateur hors d'un chemin `Users/...` déjà
        # traité ci-dessus (ex. dans un nom de service, un e-mail déjà masqué
        # laisse passer, un chemin `\\host\c$\Users\<nom>\...`, etc.).
        text = re.sub(rf"\b{re.escape(username)}\b", "<utilisateur>", text)
    for root in config.path_roots:
        text = text.replace(root, _PATH_MASK)
    return text


# --------------------------------------------------------------------------
# API publique
# --------------------------------------------------------------------------


def redact(text: str, config: RedactConfig | None = None) -> str:
    """Applique tous les masquages déterministes à `text`.

    `config` est optionnelle : à défaut, elle est chargée par `load_config()`
    (environnement puis fichier local non suivi par git). Les tests passent
    toujours une `RedactConfig` explicite construite avec des valeurs
    fictives, jamais les vraies.

    Idempotente : `redact(redact(x)) == redact(x)`.
    """
    resolved = config if config is not None else load_config()
    text = _redact_aws_accounts(text, resolved)
    text = _redact_emails(text, resolved)
    text = _redact_paths(text, resolved)
    return text


# --------------------------------------------------------------------------
# Garde-fou : détection de secrets vivants
# --------------------------------------------------------------------------

_SECRET_PREFIX_RE = re.compile(r"\b(?:sk|pk)-lf-[A-Za-z0-9_-]+")
_AWS_ACCESS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_SHA256_DIGEST_RE = re.compile(r"\bsha256:[0-9a-f]{64}\b")
_COMMIT_SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")
_LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")


def assert_no_secret(text: str) -> None:
    """Lève `SecretDetected` si `text` contient une chaîne ressemblant à un
    secret vivant (clé d'API, jeton, identifiant de clé d'accès AWS).

    Ne déclenche jamais sur un SHA de commit git (40 caractères hexadécimaux)
    ni sur un digest `sha256:...` connu : ce sont des identifiants publics,
    pas des secrets.
    """
    match = _SECRET_PREFIX_RE.search(text)
    if match:
        raise SecretDetected(f"jeton de type clé détecté : {match.group(0)[:8]}…")

    match = _AWS_ACCESS_KEY_RE.search(text)
    if match:
        raise SecretDetected("identifiant de clé d'accès AWS détecté (AKIA…)")

    # Les digests sha256: et les SHA de commit sont retirés d'une copie de
    # travail avant la recherche générique, pour ne jamais les confondre avec
    # un jeton long inconnu.
    scratch = _SHA256_DIGEST_RE.sub("", text)
    scratch = _COMMIT_SHA_RE.sub("", scratch)

    match = _LONG_TOKEN_RE.search(scratch)
    if match:
        raise SecretDetected(f"jeton long non identifié détecté ({len(match.group(0))} caractères)")
