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


def test_breaker_opens_after_consecutive_failures_and_recloses_after_cooldown() -> None:
    from ask_my_cv.guardrail import GuardrailBreaker

    breaker = GuardrailBreaker(max_failures=2, max_visitor_failures=99, cooldown_s=10)
    breaker.failure("a", 0.0)
    assert breaker.allows("b", 0.0)
    breaker.failure("b", 1.0)
    assert not breaker.allows("c", 5.0)
    assert breaker.allows("c", 11.5)  # refroidissement écoulé : demi-ouvert
    breaker.failure("c", 12.0)  # échec immédiat : rouvert
    assert not breaker.allows("d", 13.0)
    breaker.success()
    assert breaker.allows("d", 22.5)


def test_success_resets_the_consecutive_count() -> None:
    from ask_my_cv.guardrail import GuardrailBreaker

    breaker = GuardrailBreaker(max_failures=2, max_visitor_failures=99)
    breaker.failure("a", 0.0)
    breaker.success()
    breaker.failure("a", 1.0)
    assert breaker.allows("b", 2.0)


def test_breaker_isolates_a_failing_visitor_for_the_cooldown() -> None:
    from ask_my_cv.guardrail import GuardrailBreaker

    breaker = GuardrailBreaker(max_failures=99, max_visitor_failures=2, cooldown_s=10)
    breaker.failure("a", 0.0)
    breaker.failure("a", 1.0)
    assert not breaker.allows("a", 2.0)
    assert breaker.allows("b", 2.0)
    assert breaker.allows("a", 11.5)


def test_breaker_memory_is_bounded() -> None:
    from ask_my_cv.guardrail import GuardrailBreaker

    breaker = GuardrailBreaker(max_failures=10**9)
    for i in range(GuardrailBreaker.MAX_VISITORS + 50):
        breaker.failure(str(i), 0.0)
    assert len(breaker._visitors) <= GuardrailBreaker.MAX_VISITORS


async def test_bedrock_guardrail_uses_its_own_executor() -> None:
    import threading

    names: list[str] = []

    class Spy(FakeRuntime):
        def apply_guardrail(self, **kwargs: Any) -> dict[str, Any]:
            names.append(threading.current_thread().name)
            return {"action": "NONE"}

    await BedrockGuardrail("gid", "2", Spy()).check("x")
    assert names[0].startswith("guardrail")
