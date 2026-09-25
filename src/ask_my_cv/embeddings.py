from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np


class EmbeddingProvider(Protocol):
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """Embeddings déterministes par hachage de mots : ni modèle, ni réseau.

    Suffisant pour les tests et le développement local ; remplacé par Bedrock Titan en 1c.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = np.zeros(self.dim)
        for token in re.findall(r"\w+", text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            vector[int(digest, 16) % self.dim] += 1.0
        norm = np.linalg.norm(vector)
        return (vector / norm if norm else vector).tolist()
