from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Chunk:
    id: str
    section: str
    text: str


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


class VectorStore(Protocol):
    async def search(self, vector: list[float], k: int) -> list[Hit]: ...


class InMemoryVectorStore:
    """Index cosinus en mémoire, persisté dans un fichier JSON."""

    def __init__(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("autant de vecteurs que de passages attendus")
        self._chunks = chunks
        self._matrix = np.array(vectors, dtype=float)

    def __len__(self) -> int:
        return len(self._chunks)

    async def search(self, vector: list[float], k: int) -> list[Hit]:
        if not self._chunks:
            return []
        query = np.array(vector, dtype=float)
        norms = np.linalg.norm(self._matrix, axis=1) * (np.linalg.norm(query) or 1.0)
        scores = (self._matrix @ query) / np.where(norms == 0, 1.0, norms)
        order = np.argsort(-scores)[:k]
        return [Hit(chunk=self._chunks[i], score=float(scores[i])) for i in order]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "chunks": [asdict(c) for c in self._chunks],
            "vectors": self._matrix.tolist(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> InMemoryVectorStore:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls([Chunk(**c) for c in payload["chunks"]], payload["vectors"])
