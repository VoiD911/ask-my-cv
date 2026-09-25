import asyncio
import io
import json
import time
from typing import Any

import pytest
from botocore.exceptions import ClientError, EventStreamError

from ask_my_cv.aws.bedrock import BedrockEmbedder, BedrockLLM
from ask_my_cv.llm import LLMError, LLMProvider


def delta(text: str) -> dict:
    return {"contentBlockDelta": {"delta": {"text": text}, "contentBlockIndex": 0}}


class FakeRuntime:
    def __init__(
        self, events: list[dict] | None = None, error: Exception | None = None, pause_s: float = 0.0
    ) -> None:
        self.events, self.error, self.pause_s = events or [], error, pause_s
        self.calls: list[dict[str, Any]] = []
        self.consumed = 0

    def converse_stream(self, **kwargs: Any) -> dict:
        self.calls.append(kwargs)
        if self.error:
            raise self.error

        def stream():
            for event in self.events:
                if self.pause_s:
                    time.sleep(self.pause_s)
                self.consumed += 1
                yield event

        return {"stream": stream()}

    def invoke_model(self, **kwargs: Any) -> dict:
        self.calls.append(kwargs)
        dims = json.loads(kwargs["body"])["dimensions"]
        return {"body": io.BytesIO(json.dumps({"embedding": [0.5] * dims}).encode())}


async def collect(llm: BedrockLLM) -> list[str]:
    return [piece async for piece in llm.stream("système", "question")]


async def test_stream_yields_text_deltas_and_sends_a_converse_request() -> None:
    runtime = FakeRuntime(
        [
            {"messageStart": {"role": "assistant"}},
            delta("Bon"),
            delta("jour [1]"),
            {"messageStop": {}},
        ]
    )
    llm = BedrockLLM(
        id="bedrock:haiku", model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0", client=runtime
    )
    provider: LLMProvider = llm
    assert await collect(llm) == ["Bon", "jour [1]"]
    assert provider.id == "bedrock:haiku"
    call = runtime.calls[0]
    assert call["modelId"].startswith("us.anthropic.claude-haiku")
    assert call["system"] == [{"text": "système"}]
    assert call["messages"] == [{"role": "user", "content": [{"text": "question"}]}]
    assert call["inferenceConfig"]["temperature"] == 0.0


async def test_client_error_becomes_llm_error() -> None:
    error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "lent"}}, "ConverseStream"
    )
    with pytest.raises(LLMError):
        await collect(BedrockLLM(id="b", model_id="m", client=FakeRuntime(error=error)))


async def test_stream_error_event_becomes_llm_error() -> None:
    runtime = FakeRuntime([delta("x"), {"modelStreamErrorException": {"message": "coupé"}}])
    with pytest.raises(LLMError):
        await collect(BedrockLLM(id="b", model_id="m", client=runtime))


async def test_closing_the_stream_stops_the_pump() -> None:
    runtime = FakeRuntime([delta("a")] * 100, pause_s=0.01)
    llm = BedrockLLM(id="b", model_id="m", client=runtime)
    stream = llm.stream("s", "u")
    assert await anext(stream) == "a"
    await stream.aclose()
    await asyncio.sleep(0.1)
    consumed = runtime.consumed
    await asyncio.sleep(0.1)
    assert runtime.consumed == consumed < 100


async def test_titan_embedder_requests_normalized_vectors() -> None:
    runtime = FakeRuntime()
    embedder = BedrockEmbedder("amazon.titan-embed-text-v2:0", runtime, dim=1024)
    [vector] = await embedder.embed(["Quelle expérience ?"])
    assert len(vector) == 1024
    body = json.loads(runtime.calls[0]["body"])
    assert body == {"inputText": "Quelle expérience ?", "dimensions": 1024, "normalize": True}


async def test_titan_embedder_rejects_a_dimension_mismatch() -> None:
    class WrongDimRuntime:
        def invoke_model(self, **kwargs: Any) -> dict:
            return {"body": io.BytesIO(json.dumps({"embedding": [0.5] * 3}).encode())}

    embedder = BedrockEmbedder("amazon.titan-embed-text-v2:0", WrongDimRuntime(), dim=1024)
    with pytest.raises(ValueError):
        await embedder.embed(["Quelle expérience ?"])


async def test_event_stream_error_becomes_llm_error() -> None:
    class ErrorRuntime:
        def converse_stream(self, **kwargs: Any) -> dict:
            def stream():
                yield delta("a")
                raise EventStreamError(
                    {"Error": {"Code": "ThrottlingException", "Message": "lent"}},
                    "ConverseStream",
                )

            return {"stream": stream()}

    with pytest.raises(LLMError):
        await collect(BedrockLLM(id="b", model_id="m", client=ErrorRuntime()))


class ClosableEvents:
    def __init__(self, events: list[dict]) -> None:
        self.events, self.closed = events, False

    def __iter__(self):
        for event in self.events:
            time.sleep(0.01)
            yield event

    def close(self) -> None:
        self.closed = True


async def test_abandoned_stream_closes_the_event_stream() -> None:
    events = ClosableEvents([delta("a")] * 100)

    class Runtime:
        def converse_stream(self, **kwargs: Any) -> dict:
            return {"stream": events}

    stream = BedrockLLM(id="b", model_id="m", client=Runtime()).stream("s", "u")
    assert await anext(stream) == "a"
    await stream.aclose()
    await asyncio.sleep(0.1)
    assert events.closed
