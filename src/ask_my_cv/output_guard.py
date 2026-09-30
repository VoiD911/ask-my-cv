from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_CANDIDATE = re.compile(r"\+?\d[\d .-]{7,}\d")
_CITATION = re.compile(r"\[\d+\]")
_MIN_PHONE_DIGITS = 9

REFUSAL = "Je ne trouve pas cette information dans le CV."
_DECORATION = re.compile(r"[«»\"“”\s]+")


# refus traduit par le modèle malgré la consigne : ramené à la phrase canonique (française,
# que le site localise) au lieu d'être retiré comme réponse non sourcée
_TRANSLATED_REFUSAL = re.compile(
    r"^\s*[\"“«]?\s*I\s+(?:cannot|can't|can\s+not|could\s+not|couldn't|am\s+unable\s+to|was\s+unable\s+to)"
    r"\s+find\s+(?:this|that|the|any\s+such)\s+information\s+in\s+the\s+(?:CV|resume|résumé)\s*\.?\s*[\"”»]?\s*$",
    re.IGNORECASE,
)


def normalize_refusal(text: str) -> str:
    """Un refus traduit en anglais devient la phrase de refus canonique ; sinon inchangé."""
    return REFUSAL if _TRANSLATED_REFUSAL.match(text) else text


def _is_refusal(text: str) -> bool:
    return _DECORATION.sub(" ", text).strip() == REFUSAL


@dataclass(frozen=True)
class OutputVerdict:
    ok: bool
    reason: str | None = None


def _phones(text: str) -> list[str]:
    return [
        m
        for m in _PHONE_CANDIDATE.findall(text)
        if sum(c.isdigit() for c in m) >= _MIN_PHONE_DIGITS
    ]


def check_output(
    text: str, *, canary: str, allowed_contacts: set[str], n_sources: int
) -> OutputVerdict:
    if canary in text:
        return OutputVerdict(False, "prompt_leak")
    for found in _EMAIL.findall(text) + _phones(text):
        if found.strip() not in allowed_contacts:
            return OutputVerdict(False, "pii")
    if n_sources and not _CITATION.search(text) and not _is_refusal(text):
        return OutputVerdict(False, "ungrounded")
    return OutputVerdict(True)
