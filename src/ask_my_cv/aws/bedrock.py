from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncGenerator
from typing import Any

from ask_my_cv.llm import LLMError, ModelPricing


class BedrockLLM:
    """Claude sur Bedrock (ConverseStream). Le flux boto3 synchrone est pompé dans un thread."""

    def __init__(
        self,
        id: str,
        model_id: str,
        client: Any,
        pricing: ModelPricing | None = None,
        max_tokens: int = 400,
    ) -> None:
        self.id = id
        self.model_id = model_id
        self.pricing = pricing or ModelPricing()
        self.max_tokens = max_tokens
        self._client = client

    async def stream(self, system: str, user: str) -> AsyncGenerator[str, None]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        stop = threading.Event()

        def send(kind: str, value: Any) -> None:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, (kind, value))
            except RuntimeError:  # boucle fermée : plus personne n'écoute
                pass

        def pump() -> None:
            try:
                response = self._client.converse_stream(
                    modelId=self.model_id,
                    system=[{"text": system}],
                    messages=[{"role": "user", "content": [{"text": user}]}],
                    inferenceConfig={"maxTokens": self.max_tokens, "temperature": 0.0},
                )
                for event in response["stream"]:
                    if stop.is_set():
                        return
                    error = next((key for key in event if key.endswith("Exception")), None)
                    if error:
                        raise LLMError(f"{self.id} : {error}")
                    text = event.get("contentBlockDelta", {}).get("delta", {}).get("text")
                    if text:
                        send("text", text)
                send("end", None)
            except Exception as exc:  # botocore, réseau, événement d'erreur
                send("error", exc)

        threading.Thread(target=pump, name=f"bedrock-{self.id}", daemon=True).start()
        try:
            while True:
                kind, value = await queue.get()
                if kind == "text":
                    yield value
                elif kind == "end":
                    return
                else:
                    raise LLMError(f"{self.id} : {type(value).__name__}") from value
        finally:
            stop.set()  # le thread s'arrête au prochain événement ; aucune attente réseau ici


class BedrockEmbedder:
    """Titan Text Embeddings V2 (disponible en région dans ca-central-1)."""

    def __init__(self, model_id: str, client: Any, dim: int = 1024) -> None:
        self.model_id = model_id
        self.dim = dim
        self._client = client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [await asyncio.to_thread(self._embed_one, text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        response = self._client.invoke_model(
            modelId=self.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text, "dimensions": self.dim, "normalize": True}),
        )
        vector = json.loads(response["body"].read())["embedding"]
        if len(vector) != self.dim:
            raise ValueError(f"{self.model_id} : {len(vector)} dimensions au lieu de {self.dim}")
        return [float(v) for v in vector]
