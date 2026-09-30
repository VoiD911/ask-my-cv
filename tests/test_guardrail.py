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


async def test_bedrock_guardrail_uses_its_own_executor() -> None:
    import threading

    names: list[str] = []

    class Spy(FakeRuntime):
        def apply_guardrail(self, **kwargs: Any) -> dict[str, Any]:
            names.append(threading.current_thread().name)
            return {"action": "NONE"}

    await BedrockGuardrail("gid", "2", Spy()).check("x")
    assert names[0].startswith("guardrail")


# --- disjoncteur (2e passage de la revue sécurité #120) ---


def _fail(breaker, visitor: str, now: float) -> None:
    admission = breaker.admit(visitor, now)
    assert admission is not None
    breaker.record(visitor, now, "failure", admission)


def _ok(breaker, visitor: str, now: float) -> None:
    admission = breaker.admit(visitor, now)
    assert admission is not None
    breaker.record(visitor, now, "success", admission)


def test_two_attackers_cannot_open_the_breaker_for_everyone() -> None:
    from ask_my_cv.guardrail import GuardrailBreaker

    breaker = GuardrailBreaker(max_failures=5, max_visitor_failures=3, min_visitors=3)
    for t in range(3):
        _fail(breaker, "a", float(t))
        _fail(breaker, "b", float(t))
    assert breaker.state == "closed"
    assert breaker.admit("a", 4.0) is None  # l'attaquant, lui, est bloqué
    assert breaker.admit("c", 4.0) is not None


def test_failures_from_three_visitors_open_it_despite_interleaved_successes() -> None:
    from ask_my_cv.guardrail import GuardrailBreaker

    breaker = GuardrailBreaker(max_failures=5, max_visitor_failures=99, min_visitors=3)
    for i, visitor in enumerate(["a", "b", "c", "a", "b"]):
        _ok(breaker, "ok", float(i))  # succès entrecoupés : aucune remise à zéro
        _fail(breaker, visitor, float(i) + 0.5)
    assert breaker.state == "open"
    assert breaker.admit("z", 6.0) is None


def test_failures_outside_the_sliding_window_are_forgotten() -> None:
    from ask_my_cv.guardrail import GuardrailBreaker

    breaker = GuardrailBreaker(max_failures=3, max_visitor_failures=99, window_s=10)
    _fail(breaker, "a", 0.0)
    _fail(breaker, "b", 1.0)
    _fail(breaker, "c", 20.0)
    assert breaker.state == "closed"


def _opened(cooldown: float = 10.0):
    from ask_my_cv.guardrail import GuardrailBreaker

    breaker = GuardrailBreaker(
        max_failures=3, max_visitor_failures=99, min_visitors=3, cooldown_s=cooldown
    )
    for i, visitor in enumerate("abc"):
        _fail(breaker, visitor, float(i))
    assert breaker.state == "open"
    return breaker


def test_half_open_admits_a_single_probe_and_closes_on_success() -> None:
    breaker = _opened()
    assert breaker.admit("x", 5.0) is None
    probe = breaker.admit("x", 13.0)
    assert probe is not None and probe.probe
    assert breaker.admit("y", 13.1) is None  # une seule sonde à la fois
    breaker.record("x", 13.2, "success", probe)
    assert breaker.state == "closed"
    # compteurs remis à zéro : deux nouveaux échecs ne rouvrent pas
    _fail(breaker, "d", 14.0)
    _fail(breaker, "e", 14.0)
    assert breaker.state == "closed"


def test_failed_probe_reopens_and_cancelled_probe_is_released() -> None:
    breaker = _opened()
    probe = breaker.admit("x", 13.0)
    assert probe is not None
    breaker.record("x", 13.0, "cancelled", probe)
    assert breaker.state == "half_open"
    probe = breaker.admit("y", 13.5)
    assert probe is not None and probe.probe
    breaker.record("y", 14.0, "failure", probe)
    assert breaker.state == "open" and breaker.admit("z", 20.0) is None


def test_a_failing_visitor_stays_blocked_for_the_whole_cooldown() -> None:
    from ask_my_cv.guardrail import GuardrailBreaker

    breaker = GuardrailBreaker(max_failures=99, max_visitor_failures=2, cooldown_s=30, window_s=5)
    _fail(breaker, "a", 0.0)
    _fail(breaker, "a", 1.0)
    assert breaker.admit("a", 20.0) is None  # au-delà de la fenêtre, dans le refroidissement
    assert breaker.admit("a", 31.5) is not None
    assert breaker.admit("b", 2.0) is not None


def test_visitor_eviction_is_lru() -> None:
    from ask_my_cv.guardrail import GuardrailBreaker

    breaker = GuardrailBreaker(max_failures=10**9, max_visitor_failures=1, cooldown_s=100)
    breaker.MAX_VISITORS = 3
    for i, visitor in enumerate("abc"):
        _fail(breaker, visitor, float(i))
    breaker.admit("a", 3.0)  # « a » vient d'être vu : c'est « b » qui doit partir
    admission = breaker.admit("d", 3.0)
    assert admission is not None
    breaker.record("d", 3.0, "failure", admission)
    assert list(breaker._visitors) == ["c", "a", "d"]
