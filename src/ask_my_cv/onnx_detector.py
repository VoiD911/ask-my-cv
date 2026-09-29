from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort

from ask_my_cv.text import (
    NORMALIZATION_LEGACY,
    NORMALIZATIONS,
    WINDOW_OVERLAP,
    WINDOW_SIZE,
    injection_windows,
)

# Clés des métadonnées ONNX écrites par `ml.train` depuis v1.4.0.
META_WINDOW_SIZE = "window_size"
META_WINDOW_OVERLAP = "window_overlap"
META_NORMALIZATION = "normalization"


class ModelIntegrityError(Exception):
    """Le modèle est absent, non promu ou ne correspond pas au sha256 attendu."""


@dataclass(frozen=True)
class ModelManifest:
    version: str
    sha256: str
    file: str


def load_manifest(path: Path) -> ModelManifest | None:
    """Lit `models/prod.json` ; `None` si aucun modèle n'est encore promu."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelIntegrityError(f"manifeste introuvable : {path}") from exc
    if not data.get("version"):
        return None
    return ModelManifest(version=data["version"], sha256=data["sha256"], file=data["file"])


def window_params(session: ort.InferenceSession) -> tuple[int, int]:
    """Taille et chevauchement des fenêtres enregistrés dans le modèle (600/120 s'il n'en a pas).

    Les deux clés vont ensemble : un modèle qui n'en porte qu'une, ou des valeurs invalides, est
    refusé plutôt que servi avec un découpage différent de celui de son évaluation.
    """
    meta = session.get_modelmeta().custom_metadata_map
    size, overlap = meta.get(META_WINDOW_SIZE), meta.get(META_WINDOW_OVERLAP)
    if size is None and overlap is None:
        return WINDOW_SIZE, WINDOW_OVERLAP
    try:
        params = int(size or ""), int(overlap or "")
        injection_windows("", *params)
    except ValueError as exc:
        raise ModelIntegrityError(
            f"métadonnées de fenêtre invalides : size={size!r}, overlap={overlap!r}"
        ) from exc
    return params


def normalization_version(session: ort.InferenceSession) -> int:
    """Version de normalisation du modèle ; 1 (historique) s'il ne l'enregistre pas."""
    value = session.get_modelmeta().custom_metadata_map.get(META_NORMALIZATION)
    if value is None:
        return NORMALIZATION_LEGACY
    if not value.isdigit() or int(value) not in NORMALIZATIONS:
        raise ModelIntegrityError(f"normalisation inconnue dans le modèle : {value!r}")
    return int(value)


def score_texts(session: ort.InferenceSession, texts: list[str]) -> list[float]:
    """Probabilité d'injection de chaque texte : maximum sur ses fenêtres, en un seul lot ONNX.

    Seul chemin de calcul du score : le service (`OnnxDetector`) et la porte d'évaluation
    (`ml.evaluate.onnx_scores`) l'appellent tous deux.
    """
    if not texts:
        return []
    size, overlap = window_params(session)
    normalization = normalization_version(session)
    groups = [injection_windows(text, size, overlap, normalization) for text in texts]
    windows = [window for group in groups for window in group]
    outputs = session.run(None, {"text": np.asarray(windows, dtype=object).reshape(-1, 1)})
    scores = np.asarray(outputs[1])[:, 1]
    result = []
    offset = 0
    for group in groups:
        result.append(float(scores[offset : offset + len(group)].max()))
        offset += len(group)
    return result


class OnnxDetector:
    """Classifieur d'injection entraîné (plan 1b), vérifié par sha256 avant chargement."""

    def __init__(self, model_path: Path, sha256: str, version: str) -> None:
        try:
            data = model_path.read_bytes()
        except FileNotFoundError as exc:
            raise ModelIntegrityError(f"modèle introuvable : {model_path}") from exc
        digest = hashlib.sha256(data).hexdigest()
        if digest != sha256:
            raise ModelIntegrityError(f"{model_path} : sha256 {digest} au lieu de {sha256}")
        self._session = ort.InferenceSession(data, providers=["CPUExecutionProvider"])
        self.window = window_params(self._session)
        self.normalization = normalization_version(self._session)
        self.version = f"onnx-{version}"

    def score(self, text: str) -> float:
        return score_texts(self._session, [text])[0]
