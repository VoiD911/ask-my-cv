from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import httpx


class LLMError(Exception):
    """Le fournisseur n'a pas pu répondre : le pipeline peut basculer sur le suivant."""


@dataclass(frozen=True)
class ModelPricing:
    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0

    def cost(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in * self.input_per_mtok + tokens_out * self.output_per_mtok) / 1_000_000


def estimate_tokens(text: str) -> int:
    """Estimation grossière (~4 caractères par token), suffisante pour le suivi de budget."""
    return max(1, len(text) // 4)


class LLMProvider(Protocol):
    id: str
    pricing: ModelPricing

    def stream(self, system: str, user: str) -> AsyncIterator[str]: ...


DEFAULT_FAKE_REPLY = "D'après le CV [1], le candidat a une expérience concrète en MLOps."


class FakeLLM:
    """Fournisseur déterministe pour les tests, la CI et les démos hors ligne."""

    def __init__(
        self,
        id: str,
        pricing: ModelPricing | None = None,
        reply: str = DEFAULT_FAKE_REPLY,
        fail: bool = False,
    ) -> None:
        self.id = id
        self.pricing = pricing or ModelPricing()
        self.reply = reply
        self.fail = fail
        self.calls = 0

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        self.calls += 1
        if self.fail:
            raise LLMError(f"{self.id} indisponible")
        for i, word in enumerate(self.reply.split(" ")):
            yield word if i == 0 else f" {word}"


class OllamaLLM:
    """Modèle local servi par Ollama (API /api/chat en NDJSON)."""

    def __init__(
        self,
        id: str,
        model: str,
        base_url: str,
        pricing: ModelPricing | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.id = id
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.pricing = pricing or ModelPricing()
        self._client = client or httpx.AsyncClient(timeout=60)

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as response:
                if response.status_code != 200:
                    raise LLMError(f"{self.id} a répondu HTTP {response.status_code}")
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    text = chunk.get("message", {}).get("content", "")
                    if text:
                        yield text
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.id} injoignable : {exc}") from exc
