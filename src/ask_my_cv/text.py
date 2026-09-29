from __future__ import annotations

import re

_WHITESPACE_RUNS = re.compile(r"\s\s+")

# Paramètres de découpage par défaut, ceux des modèles antérieurs à v1.4.0 qui ne les portent pas
# dans leurs métadonnées ONNX. Un modèle récent les enregistre (`window_size`, `window_overlap`)
# et le service utilise ceux du modèle.
WINDOW_SIZE = 600
WINDOW_OVERLAP = 120


def normalize_text(text: str) -> str:
    """Normalisation partagée par l'entraînement et le service (parité ONNX / scikit-learn).

    « # » devient une espace : c'est le caractère de remplissage du Tokenizer ONNX produit par
    skl2onnx. Un n-gramme du vocabulaire qui en contient (titres Markdown « ## ») fausse le score
    ONNX (écart de 0,33 à 0,6 mesuré le 2026-09-29) sans rien changer au score scikit-learn.
    """
    return _WHITESPACE_RUNS.sub(" ", text.replace("#", " "))


def injection_windows(
    text: str, size: int = WINDOW_SIZE, overlap: int = WINDOW_OVERLAP
) -> list[str]:
    """Fenêtres chevauchantes pour éviter de diluer une injection dans une annonce.

    Toutes les fenêtres font `size` caractères (sauf un texte plus court, gardé entier), au pas de
    `size - overlap`, la dernière étant alignée sur la fin du texte. Une injection de `overlap`
    caractères ou moins tient donc entière dans au moins une fenêtre ; une injection plus longue
    coupée à une frontière n'est vue que partiellement de chaque côté.
    """
    normalized = normalize_text(text)
    return [normalized[s : s + size] for s in window_starts(len(normalized), size, overlap)]


def window_starts(length: int, size: int = WINDOW_SIZE, overlap: int = WINDOW_OVERLAP) -> list[int]:
    """Débuts des fenêtres d'un texte déjà normalisé de `length` caractères."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError(f"fenêtre invalide : size={size}, overlap={overlap}")
    if length <= size:
        return [0]
    starts = list(range(0, length - size + 1, size - overlap))
    if starts[-1] != length - size:
        starts.append(length - size)
    return starts
