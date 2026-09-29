from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sector:
    """Phrases d'un secteur d'activité : intitulés, missions, exigences, outils."""

    key: str
    titles: tuple[str, ...]
    missions: tuple[str, ...]
    requirements: tuple[str, ...]
    stack: tuple[str, ...]
