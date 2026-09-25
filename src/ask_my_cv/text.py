from __future__ import annotations

import re

_WHITESPACE_RUNS = re.compile(r"\s\s+")


def normalize_text(text: str) -> str:
    """Normalisation partagée par l'entraînement et le service (parité ONNX / scikit-learn)."""
    return _WHITESPACE_RUNS.sub(" ", text)
