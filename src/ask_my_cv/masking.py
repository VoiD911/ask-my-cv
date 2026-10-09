"""Masquage du texte des échanges avant conservation (#150).

Motifs génériques, en une seule passe (une expression alternée) pour qu'un masquage n'en
corrompe pas un autre : secrets à haute confiance (adaptés de tools/devlog/redact.py, sans
l'importer), URL, adresses e-mail, numéros de téléphone (FR, CA, international). Les contacts
autorisés (ex. job@stevelang.net) restent lisibles. Motifs sans quantificateur imbriqué.

Avant les motifs : repli NFKC sans caractères de format (`text.fold_format` : largeur nulle,
arobase pleine chasse…) puis désobfuscation courante (« [at] », « (dot) », « x at y dot com »,
« hxxp », « [.] »). Masquage au mieux : du texte libre (nom, domaine nu, adresse postale) peut
rester lisible.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ask_my_cv.text import fold_format

_PATTERNS: tuple[tuple[str, str], ...] = (
    ("secret", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
    ("secret", r"(?<![A-Za-z0-9])(?:AKIA|ASIA|AROA|AIDA)[0-9A-Z]{16}(?![A-Za-z0-9])"),
    ("secret", r"(?<![A-Za-z0-9_])gh[opsur]_[A-Za-z0-9]{36,}"),
    ("secret", r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{22,}"),
    ("secret", r"(?<![A-Za-z0-9_-])(?:sk|pk)-(?:lf|proj|ant)-[A-Za-z0-9_-]+"),
    ("secret", r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9]{40,}"),
    ("secret", r"(?<![A-Za-z0-9_-])xox[abprs]-[0-9A-Za-z-]{10,}"),
    ("secret", r"(?<![A-Za-z0-9_-])AIza[A-Za-z0-9_-]{35}"),
    ("secret", r"(?<![A-Za-z0-9_-])eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+"),
    ("url", r"(?i:\b(?:h(?:tt|xx)ps?://|www\.)[^\s<>\"'«»]+)"),
    ("email", r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    # +33 6 12 34 56 78, 06.12.34.56.78, (514) 555-1234, +1 514 555 1234, +44 20 7946 0958
    # candidat retenu s'il compte au moins 9 chiffres (comme le garde de sortie)
    ("phone", r"(?<![\w+])\+?\(?\d[\d ().-]{6,22}\d(?!\w)"),
)
_COMBINED = re.compile("|".join(f"(?P<{kind}{i}>{p})" for i, (kind, p) in enumerate(_PATTERNS)))
_MIN_PHONE_DIGITS = 9
_LABELS = {"secret": "[secret]", "url": "[url]", "email": "[e-mail]", "phone": "[téléphone]"}

_AT = re.compile(r"(?i) ?[\[(] ?(?:at|arobase) ?[\])] ?")
_DOT = re.compile(r"(?i) ?[\[(] ?(?:dot|point|\.) ?[\])] ?")
# « prenom at acme dot com » / « prenom at acme.com » : seulement suivi d'un domaine pointé
_SPELLED = re.compile(r"(?i)(?<![\w.+-])([\w.+-]+) at ([\w-]+(?:(?: dot |\.)[\w-]+)+)(?![\w-])")


def _deobfuscate(text: str) -> str:
    text = _DOT.sub(".", _AT.sub("@", text))
    return _SPELLED.sub(lambda m: f"{m[1]}@{m[2].replace(' dot ', '.')}", text)


def mask(text: str, allowed: Iterable[str] = ()) -> str:
    """Texte masqué ; les valeurs de `allowed` (comparées sans casse) restent intactes."""
    keep = {a.strip().lower() for a in allowed}

    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        if value.strip().lower() in keep:
            return value
        kind = (match.lastgroup or "secret").rstrip("0123456789")
        if kind == "phone" and sum(c.isdigit() for c in value) < _MIN_PHONE_DIGITS:
            return value
        return _LABELS.get(kind, "[masqué]")

    return _COMBINED.sub(replace, _deobfuscate(fold_format(text)))


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
