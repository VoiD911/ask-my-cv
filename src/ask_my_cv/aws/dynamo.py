from __future__ import annotations

import asyncio
import time
from typing import Any

from ask_my_cv.budget import BudgetExceeded, RateLimited
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
        keep = {chunk.id for chunk in chunks}
        for page in self._client.get_paginator("scan").paginate(
            TableName=self.table, ProjectionExpression="id"
        ):
            for found in page.get("Items", []):
                if found["id"]["S"] not in keep:  # passage d'une version précédente du CV
                    self._client.delete_item(TableName=self.table, Key={"id": found["id"]})


def _day(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(now))


class DynamoLedger:
    """Quotas et dépenses dans DynamoDB : compteurs atomiques (ADD), écriture conditionnelle, TTL.

    Le quota visiteur est une fenêtre fixe (et non glissante comme en mémoire) : c'est ce qui
    permet un compteur atomique en une seule écriture conditionnelle.
    """

    def __init__(
        self, table: str, client: Any, daily_cap_usd: float, per_visitor_limit: int, window_s: float
    ) -> None:
        self.table = table
        self.daily_cap_usd = daily_cap_usd
        self.per_visitor_limit = per_visitor_limit
        self.window_s = window_s
        self._client = client

    def check(self, visitor: str, now: float) -> None:
        if self.spent_today(now) >= self.daily_cap_usd:
            raise BudgetExceeded
        window = int(now // self.window_s)
        try:
            self._client.update_item(
                TableName=self.table,
                Key={"pk": {"S": f"rate#{visitor}#{window}"}},
                UpdateExpression="ADD #count :one SET #exp = :exp",
                ConditionExpression="attribute_not_exists(#count) OR #count < :limit",
                ExpressionAttributeNames={"#count": "count", "#exp": "expires_at"},
                ExpressionAttributeValues={
                    ":one": {"N": "1"},
                    ":limit": {"N": str(self.per_visitor_limit)},
                    ":exp": {"N": str(int(now + 2 * self.window_s))},
                },
            )
        except self._client.exceptions.ConditionalCheckFailedException:
            raise RateLimited from None

    def record(self, provider_id: str, cost_usd: float, now: float) -> None:
        self._client.update_item(
            TableName=self.table,
            Key={"pk": {"S": f"spend#{_day(now)}"}},
            UpdateExpression="ADD #total :cost, #provider :cost SET #exp = :exp",
            ExpressionAttributeNames={
                "#total": "total",
                "#provider": f"p#{provider_id}",
                "#exp": "expires_at",
            },
            ExpressionAttributeValues={
                ":cost": {"N": format(cost_usd, ".10f")},
                ":exp": {"N": str(int(now + 40 * 86_400))},
            },
        )

    def _spend_item(self, now: float) -> dict[str, Any]:
        response = self._client.get_item(
            TableName=self.table, Key={"pk": {"S": f"spend#{_day(now)}"}}, ConsistentRead=True
        )
        return response.get("Item", {})

    def spent_today(self, now: float) -> float:
        return float(self._spend_item(now).get("total", {}).get("N", "0"))

    def spent_by_provider(self, now: float) -> dict[str, float]:
        return {
            k[2:]: float(v["N"]) for k, v in self._spend_item(now).items() if k.startswith("p#")
        }
