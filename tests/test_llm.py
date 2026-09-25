import httpx
import pytest

from ask_my_cv.llm import FakeLLM, LLMError, ModelPricing, OllamaLLM, estimate_tokens


def test_pricing_cost() -> None:
    pricing = ModelPricing(input_per_mtok=1.0, output_per_mtok=5.0)
    assert pricing.cost(1_000_000, 0) == 1.0
    assert pricing.cost(3000, 400) == pytest.approx(0.005)


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100


async def test_fake_llm_streams_reply_and_counts_calls() -> None:
    llm = FakeLLM(id="fake:echo", reply="Bonjour le monde [1]")
    pieces = [p async for p in llm.stream("sys", "user")]
    assert "".join(pieces) == "Bonjour le monde [1]"
    assert len(pieces) == 4
    assert llm.calls == 1


async def test_fake_llm_failure() -> None:
    llm = FakeLLM(id="fake:down", fail=True)
    with pytest.raises(LLMError):
        [p async for p in llm.stream("sys", "user")]


async def test_ollama_streams_ndjson() -> None:
    body = (
        b'{"message":{"content":"Bon"},"done":false}\n'
        b'{"message":{"content":"jour"},"done":true}\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(200, content=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    llm = OllamaLLM(id="ollama:test", model="test", base_url="http://ollama", client=client)
    assert [p async for p in llm.stream("sys", "user")] == ["Bon", "jour"]


async def test_ollama_http_error_becomes_llm_error() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    llm = OllamaLLM(id="ollama:test", model="test", base_url="http://ollama", client=client)
    with pytest.raises(LLMError):
        [p async for p in llm.stream("sys", "user")]


async def test_ollama_unreachable_becomes_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    llm = OllamaLLM(id="ollama:test", model="test", base_url="http://ollama", client=client)
    with pytest.raises(LLMError):
        [p async for p in llm.stream("sys", "user")]
