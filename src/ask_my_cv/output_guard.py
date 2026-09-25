from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_CANDIDATE = re.compile(r"\+?\d[\d .-]{7,}\d")
_CITATION = re.compile(r"\[\d+\]")
_MIN_PHONE_DIGITS = 9

REFUSAL = "Je ne trouve pas cette information dans le CV."
_DECORATION = re.compile(r"[«»\"“”\s]+")


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
