from __future__ import annotations

import asyncio
from typing import Any

from ask_my_cv.vectorstore import Chunk, Hit

INDEX_NAME = "embedding-index"


def _number(value: float) -> dict[str, str]:
    return {"N": repr(float(value))}


class DynamoVectorStore:
    """Recherche vectorielle native DynamoDB (API SearchVectors, table on-demand)."""

    def __init__(self, table: str, client: Any, index: str = INDEX_NAME) -> None:
        self.table = table
        self.index = index
        self._client = client

    async def search(self, vector: list[float], k: int) -> list[Hit]:
        return await asyncio.to_thread(self._search, vector, k)

    def _search(self, vector: list[float], k: int) -> list[Hit]:
        response = self._client.search_vectors(
            TableName=self.table,
            IndexName=self.index,
            SearchVector=[_number(v) for v in vector],
            TopK=k,
        )
        hits = []
        for result in response.get("SearchResults", []):
            found = result["Item"]
            chunk = Chunk(
                id=found["id"]["S"], section=found["section"]["S"], text=found["text"]["S"]
            )
            hits.append(Hit(chunk=chunk, score=float(result.get("Score", 0.0))))
        return hits

    def write(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._client.put_item(
                TableName=self.table,
                Item={
                    "id": {"S": chunk.id},
                    "section": {"S": chunk.section},
                    "text": {"S": chunk.text},
                    "embedding": {"L": [_number(v) for v in vector]},
                },
            )
