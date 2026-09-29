"""Langue du texte soumis (français ou anglais), par proportion de mots-outils.

Déterministe, sans dépendance : le modèle ignorait la consigne de langue du gabarit quand
les sources du CV sont en français. La langue détectée est donc écrite explicitement dans
le message utilisateur (voir prompting.py). Par défaut : français.
"""

from __future__ import annotations

import re
from typing import Literal

Language = Literal["fr", "en"]

_EN = frozenset(
    "the a an and or of to in on at for with by from as is are was were be been has have had "
    "his her he she it this that these those which who what does do did not no can will would "
    "should our your you we they their its our about into".split()
)
_FR = frozenset(
    "le la les l un une des de du d et ou en au aux dans pour par sur avec est sont ont il elle "
    "ils elles son sa ses leur leurs qui que qu ne pas ce cette ces se nous vous notre votre "
    "vos nos être été chez".split()
)
_WORD = re.compile(r"[^\W\d_]+")

# en dessous, le texte est trop court ou trop technique pour trancher
_MIN_EN_RATIO = 0.08

LABELS: dict[Language, str] = {"fr": "français", "en": "anglais"}


def detect_language(text: str) -> Language:
    """`en` si les mots-outils anglais dominent nettement, sinon `fr` (défaut)."""
    words = [w.lower() for w in _WORD.findall(text)]
    if not words:
        return "fr"
    en = sum(w in _EN for w in words)
    fr = sum(w in _FR for w in words)
    if en > fr and en / len(words) >= _MIN_EN_RATIO:
        return "en"
    return "fr"
