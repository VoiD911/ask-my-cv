"""Langue du texte soumis (français ou anglais), par mots-outils.

Déterministe, sans dépendance : le modèle ignorait la consigne de langue du gabarit quand
les sources du CV sont en français. La langue détectée est donc écrite explicitement dans
le message utilisateur (voir prompting.py). Par défaut : français.

Les mots communs aux deux langues ou ambigus (« a », « as », « on », « or », « an »,
« me », « son », « en »…) ne figurent dans aucune liste : « Quel poste a Steve ? » reste
français. Le passage à l'anglais exige au moins deux mots-outils anglais DISTINCTS et
une majorité de mots-outils anglais.
"""

from __future__ import annotations

import re
from typing import Literal

Language = Literal["fr", "en"]

_AMBIGUOUS = frozenset("a as on or an me son en est no ne if la le de do die par for pour".split())
_EN = (
    frozenset(
        "the and of to in at with by from is are was were be been has have had his her he "
        "she it this that these those which who what does did not can will would should our "
        "your you we they their its about into".split()
    )
    - _AMBIGUOUS
)
_FR = (
    frozenset(
        "les un une des du et ou au aux dans avec sont ont il elle ils elles sa ses leur "
        "leurs qui que qu pas ce cette ces se nous vous notre votre vos nos être été chez "
        "quel quelle quels quelles est-il".split()
    )
    - _AMBIGUOUS
)
_WORD = re.compile(r"[^\W\d_]+")
_MIN_DISTINCT_EN = 2

LABELS: dict[Language, str] = {"fr": "français", "en": "anglais"}


def detect_language(text: str) -> Language:
    """`en` si au moins deux mots-outils anglais distincts et une majorité anglaise, sinon `fr`."""
    words = [w.lower() for w in _WORD.findall(text)]
    en_words = [w for w in words if w in _EN]
    fr_count = sum(w in _FR for w in words)
    if len(set(en_words)) >= _MIN_DISTINCT_EN and len(en_words) > fr_count:
        return "en"
    return "fr"
