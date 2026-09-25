from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Verdict:
    score: float
    blocked: bool
    model_version: str


class InjectionDetector(Protocol):
    version: str

    def score(self, text: str) -> float: ...


_PATTERNS = [
    r"ignore (all |your |the )?(previous |prior )?instructions",
    r"ignore (tes|les|toutes les) (\w+ )?instructions|oublie (tes|les) instructions",
    r"system prompt|prompt syst[eè]me",
    r"you are now|tu es maintenant",
    r"jailbreak|\bDAN\b",
    r"disregard .{0,40}(rules|instructions)",
]


class HeuristicDetector:
    """Règles simples, en attendant le classifieur ONNX entraîné (plan 1b)."""

    version = "heuristic-1"

    def score(self, text: str) -> float:
        hits = sum(bool(re.search(p, text, re.IGNORECASE)) for p in _PATTERNS)
        return min(1.0, hits * 0.6)


def check_input(detector: InjectionDetector, text: str, threshold: float) -> Verdict:
    score = detector.score(text)
    return Verdict(score=score, blocked=score >= threshold, model_version=detector.version)
