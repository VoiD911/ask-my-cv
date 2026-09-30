import asyncio
from typing import Any

import pytest

from ask_my_cv.aws.bedrock import BedrockGuardrail
from ask_my_cv.guardrail import (
    AD_MIN_CHARS,
    USD_PER_UNIT,
    FakeGuardrail,
    GuardrailResult,
    guardrail_request,
    is_ad_like,
    text_units,
)


def test_text_units_bills_per_started_thousand_chars() -> None:
    assert text_units("") == 1
    assert text_units("a" * 1_000) == 1
    assert text_units("a" * 1_001) == 2


def test_price_is_fifteen_cents_per_thousand_units() -> None:
    assert USD_PER_UNIT * 1_000 == pytest.approx(0.15)


def test_ad_like_threshold_separates_questions_from_pasted_ads() -> None:
    # jeux mesurés : questions du domaine ≤ 54 caractères, annonces d'évaluation ≥ 447
    assert AD_MIN_CHARS == 400
    assert not is_ad_like("Quelle expérience en MLOps ?")
    assert not is_ad_like("a" * (AD_MIN_CHARS - 1))
    assert is_ad_like("a" * AD_MIN_CHARS)
    assert is_ad_like("a" * 200, min_chars=100)


def test_request_shape_matches_the_measurement() -> None:
    assert guardrail_request("gid", "3", "texte") == {
        "guardrailIdentifier": "gid",
        "guardrailVersion": "3",
        "source": "INPUT",
        "outputScope": "FULL",
        "content": [{"text": {"text": "texte", "qualifiers": ["guard_content"]}}],
    }


async def test_fake_guardrail_records_calls_and_answers() -> None:
    fake = FakeGuardrail(intervene=True)
    result = await fake.check("a" * 1_500)
    assert result == GuardrailResult(intervened=True, units=2)
    assert fake.calls == 1


class FakeRuntime:
    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None):
        self.response, self.error = response or {}, error
        self.calls: list[dict[str, Any]] = []

    def apply_guardrail(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


async def test_bedrock_guardrail_intervention_and_reported_units() -> None:
    runtime = FakeRuntime({"action": "GUARDRAIL_INTERVENED", "usage": {"contentPolicyUnits": 3}})
    guardrail = BedrockGuardrail("gid", "2", runtime)
    result = await guardrail.check("annonce")
    assert result == GuardrailResult(intervened=True, units=3)
    assert runtime.calls == [guardrail_request("gid", "2", "annonce")]


async def test_bedrock_guardrail_pass_estimates_units_when_usage_is_missing() -> None:
    guardrail = BedrockGuardrail("gid", "2", FakeRuntime({"action": "NONE"}))
    assert await guardrail.check("a" * 2_500) == GuardrailResult(intervened=False, units=3)


async def test_bedrock_guardrail_errors_propagate() -> None:
    guardrail = BedrockGuardrail("gid", "2", FakeRuntime(error=RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        await guardrail.check("annonce")


async def test_bedrock_guardrail_runs_off_the_event_loop() -> None:
    import threading

    main = threading.get_ident()
    seen: list[int] = []

    class Spy(FakeRuntime):
        def apply_guardrail(self, **kwargs: Any) -> dict[str, Any]:
            seen.append(threading.get_ident())
            return {"action": "NONE"}

    await BedrockGuardrail("gid", "2", Spy()).check("x")
    assert seen and seen[0] != main
    await asyncio.sleep(0)
