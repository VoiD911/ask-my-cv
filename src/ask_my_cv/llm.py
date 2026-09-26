from __future__ import annotations

import json
from collections.abc import AsyncGenerator
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
    """Repli quand le fournisseur ne compte pas (flux coupé, FakeLLM)."""
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class TokenUsage:
    """Consommation comptée par le fournisseur, émise en dernier dans le flux."""

    tokens_in: int
    tokens_out: int
    stop_reason: str | None = None


Chunk = str | TokenUsage


class LLMProvider(Protocol):
    id: str
    pricing: ModelPricing

    def stream(self, system: str, user: str) -> AsyncGenerator[Chunk, None]: ...


DEFAULT_FAKE_REPLY = "D'après le CV [1], le candidat a une expérience concrète en MLOps."


class FakeLLM:
    """Fournisseur déterministe pour les tests, la CI et les démos hors ligne."""

    def __init__(
        self,
        id: str,
        pricing: ModelPricing | None = None,
        reply: str = DEFAULT_FAKE_REPLY,
        fail: bool = False,
        usage: TokenUsage | None = None,
    ) -> None:
        self.id = id
        self.pricing = pricing or ModelPricing()
        self.reply = reply
        self.fail = fail
        self.usage = usage
        self.calls = 0

    async def stream(self, system: str, user: str) -> AsyncGenerator[Chunk, None]:
        self.calls += 1
        if self.fail:
            raise LLMError(f"{self.id} indisponible")
        if self.reply:
            for i, word in enumerate(self.reply.split(" ")):
                yield word if i == 0 else f" {word}"
        if self.usage is not None:
            yield self.usage


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

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream(self, system: str, user: str) -> AsyncGenerator[Chunk, None]:
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
                        tokens_in, tokens_out = (
                            chunk.get("prompt_eval_count"),
                            chunk.get("eval_count"),
                        )
                        if tokens_in is not None and tokens_out is not None:
                            yield TokenUsage(tokens_in, tokens_out, chunk.get("done_reason"))
                        break
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.id} injoignable : {exc}") from exc
