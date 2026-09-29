from __future__ import annotations

import re

_WHITESPACE_RUNS = re.compile(r"\s\s+")


def normalize_text(text: str) -> str:
    """Normalisation partagée par l'entraînement et le service (parité ONNX / scikit-learn)."""
    return _WHITESPACE_RUNS.sub(" ", text)


def injection_windows(text: str, size: int = 600, overlap: int = 120) -> list[str]:
    """Fenêtres chevauchantes pour éviter de diluer une injection dans une annonce."""
    normalized = normalize_text(text)
    if len(normalized) <= size:
        return [normalized]
    starts = list(range(0, len(normalized) - size + 1, size - overlap))
    if starts[-1] != len(normalized) - size:
        starts.append(len(normalized) - size)
    return [normalized[start : start + size] for start in starts]
