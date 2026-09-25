from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort

from ask_my_cv.text import normalize_text


class ModelIntegrityError(Exception):
    """Le modèle est absent, non promu ou ne correspond pas au sha256 attendu."""


@dataclass(frozen=True)
class ModelManifest:
    version: str
    sha256: str
    file: str


def load_manifest(path: Path) -> ModelManifest | None:
    """Lit `models/prod.json` ; `None` si aucun modèle n'est encore promu."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("version"):
        return None
    return ModelManifest(version=data["version"], sha256=data["sha256"], file=data["file"])


class OnnxDetector:
    """Classifieur d'injection entraîné (plan 1b), vérifié par sha256 avant chargement."""

    def __init__(self, model_path: Path, sha256: str, version: str) -> None:
        data = model_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != sha256:
            raise ModelIntegrityError(f"{model_path} : sha256 {digest} au lieu de {sha256}")
        self._session = ort.InferenceSession(data, providers=["CPUExecutionProvider"])
        self.version = f"onnx-{version}"

    def score(self, text: str) -> float:
        outputs = self._session.run(
            None, {"text": np.array([[normalize_text(text)]], dtype=object)}
        )
        return float(np.asarray(outputs[1])[0, 1])
