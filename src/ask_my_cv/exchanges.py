"""Journal des échanges publics (#150) : question et réponse masquées, conservées 30 jours.

Trafic public seulement (jamais évaluation ni interne), sans IP : le visiteur n'est connu que
par son pseudonyme hebdomadaire (`xops.visitor`). Écriture au mieux, hors de la boucle, après
la réponse : un échec n'affecte jamais le visiteur (journal + ligne de métrique).

Le masquage a lieu une seule fois, dans le pipeline (`masked_texts`) : les mêmes chaînes vont
dans DynamoDB et sur l'observation racine Langfuse (#154). `Exchange` porte donc du texte
déjà masqué.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from ask_my_cv.masking import mask, truncate

logger = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 12_000
MAX_ANSWER_CHARS = 4_000
RETENTION_S = 30 * 86_400


def masked_texts(question: str, answer: str, allowed: Iterable[str] = ()) -> tuple[str, str]:
    """Question et réponse affichée, masquées puis tronquées (un seul appel par échange)."""
    allowed = list(allowed)
    return (
        truncate(mask(question, allowed), MAX_QUESTION_CHARS),
        truncate(mask(answer, allowed), MAX_ANSWER_CHARS),
    )


@dataclass(frozen=True)
class Exchange:
    trace_id: str
    timestamp: float
    question: str  # déjà masquée (`masked_texts`)
    answer: str  # déjà masquée (`masked_texts`)
    result: str
    language: str = ""
    kind: str = ""
    block_reason: str = ""
    sources: list[str] = field(default_factory=list)
    model: str = ""
    prompt: str = ""
    detector: str = ""
    visitor: str = ""
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class ExchangeLog(Protocol):
    def write(self, exchange: Exchange) -> None: ...


def to_item(exchange: Exchange) -> dict[str, Any]:
    """Élément DynamoDB : pk = jour UTC, sk = horodatage ISO#trace ; texte déjà masqué."""
    ts = exchange.timestamp
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)) + f".{int(ts * 1000) % 1000:03d}Z"
    item: dict[str, Any] = {
        "pk": {"S": time.strftime("%Y-%m-%d", time.gmtime(ts))},
        "sk": {"S": f"{stamp}#{exchange.trace_id}"},
        # troncature de garde seulement : le texte arrive masqué et tronqué
        "question": {"S": truncate(exchange.question, MAX_QUESTION_CHARS)},
        "answer": {"S": truncate(exchange.answer, MAX_ANSWER_CHARS)},
        "result": {"S": exchange.result},
        "cost_usd": {"N": format(exchange.cost_usd, ".6f")},
        "latency_ms": {"N": format(exchange.latency_ms, ".1f")},
        "expires_at": {"N": str(int(ts + RETENTION_S))},
    }
    for name in ("language", "kind", "block_reason", "model", "prompt", "detector", "visitor"):
        if value := getattr(exchange, name):
            item[name] = {"S": value[:200]}
    if exchange.sources:
        item["sources"] = {"L": [{"S": s[:200]} for s in exchange.sources[:20]]}
    return item


class DynamoExchangeLog:
    """Une écriture `PutItem` par échange (seule permission IAM du Lambda sur la table)."""

    def __init__(self, table: str, client: Any) -> None:
        self.table = table
        self._client = client

    def write(self, exchange: Exchange) -> None:
        self._client.put_item(TableName=self.table, Item=to_item(exchange))
