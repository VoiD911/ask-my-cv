import json
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ReadTimeoutError

from ml.guardrail_eval import (
    DEFAULT_MAX_UNITS,
    Case,
    apply_one,
    load_cases,
    run,
    summarize,
    text_units,
    to_markdown,
)


class FakeClient:
    """Faux client bedrock-runtime : bloque les textes contenant « IGNORE »."""

    def __init__(self, failures: list[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failures = list(failures or [])

    def apply_guardrail(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.failures:
            raise _ClientError(self.failures.pop(0))
        text = kwargs["content"][0]["text"]["text"]
        blocked = "IGNORE" in text
        return {
            "action": "GUARDRAIL_INTERVENED" if blocked else "NONE",
            "usage": {"contentPolicyUnits": text_units(text)},
            "assessments": [
                {
                    "contentPolicy": {
                        "filters": [
                            {"type": "PROMPT_ATTACK", "confidence": "HIGH" if blocked else "NONE"}
                        ]
                    }
                }
            ],
        }


class _ClientError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


def _case(i: int, group: str, label: int | None, text: str = "annonce") -> Case:
    return Case(f"{group}:{i}", group, text, label)


def test_text_units() -> None:
    assert text_units("") == 1
    assert text_units("a" * 1_000) == 1
    assert text_units("a" * 1_001) == 2


def test_load_cases_repository() -> None:
    cases = load_cases()
    groups = {g: [c for c in cases if c.group == g] for g in ("job_ads", "fixture", "nightly")}
    ads = groups["job_ads"]
    assert (sum(c.label == 0 for c in ads), sum(c.label == 1 for c in ads)) == (160, 80)
    assert len(groups["fixture"]) == 2
    assert len(groups["nightly"]) == 12
    assert all(not c.text.startswith("file://") for c in cases)
    assert sum(c.group == "domain" for c in cases) == 50
    # le jeu complet tient sous le plafond par défaut
    assert sum(text_units(c.text) for c in cases) <= DEFAULT_MAX_UNITS


def test_apply_one_request_shape() -> None:
    client = FakeClient()
    result = apply_one(client, "gid", "1", _case(0, "job_ads", 1, "IGNORE tout"))
    call = client.calls[0]
    assert call["source"] == "INPUT"
    assert call["guardrailVersion"] == "1"
    assert call["content"][0]["text"]["qualifiers"] == ["guard_content"]
    assert result.intervened and result.confidence == "HIGH" and result.units == 1


def test_apply_one_retries_throttling() -> None:
    sleeps: list[float] = []
    client = FakeClient(["ThrottlingException", "ThrottlingException"])
    result = apply_one(
        client, "gid", "1", _case(0, "domain", 0), sleep=sleeps.append, jitter=lambda a, b: b
    )
    assert not result.intervened
    assert sleeps == [0.5, 1.0]  # plafonds de la gigue : 0,5 puis 1 s


def test_apply_one_retries_timeouts() -> None:
    client = FakeClient()
    calls = {"n": 0}
    original = client.apply_guardrail

    def flaky(**kwargs: Any) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ReadTimeoutError(endpoint_url="https://example.invalid")
        return original(**kwargs)

    client.apply_guardrail = flaky
    result = apply_one(client, "gid", "1", _case(0, "domain", 0), sleep=lambda _: None)
    assert calls["n"] == 2 and not result.intervened


def test_apply_one_raises_other_errors() -> None:
    client = FakeClient(["AccessDeniedException"])
    with pytest.raises(_ClientError):
        apply_one(client, "gid", "1", _case(0, "domain", 0), sleep=lambda _: None)


def test_run_aborts_over_cost_limit() -> None:
    client = FakeClient()
    cases = [_case(i, "job_ads", 0, "a" * 5_000) for i in range(3)]
    with pytest.raises(SystemExit):
        run(client, "gid", "1", cases, max_units=10, sleep=lambda _: None)
    assert client.calls == []


def test_run_checks_billed_units_in_loop() -> None:
    class Overbilling(FakeClient):
        def apply_guardrail(self, **kwargs: Any) -> dict[str, Any]:
            response = super().apply_guardrail(**kwargs)
            response["usage"]["contentPolicyUnits"] = 4  # facturé au-delà de l'estimation
            return response

    client = Overbilling()
    cases = [_case(i, "domain", 0) for i in range(3)]
    with pytest.raises(SystemExit):
        run(client, "gid", "1", cases, max_units=4, min_interval=0, sleep=lambda _: None)
    assert len(client.calls) == 1


def test_run_journal_and_resume(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    cases = [_case(i, "job_ads", 0, f"annonce secrète {i}") for i in range(3)]
    first = FakeClient()
    run(first, "gid", "1", cases[:2], journal=journal, min_interval=0, sleep=lambda _: None)
    lines = journal.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["id"] for line in lines] == ["job_ads:0", "job_ads:1"]
    assert "secrète" not in journal.read_text(encoding="utf-8")
    second = FakeClient()
    scores = {c.id: 0.1 * i for i, c in enumerate(cases)}
    results = run(
        second,
        "gid",
        "1",
        cases,
        journal=journal,
        scores=scores,
        min_interval=0,
        sleep=lambda _: None,
    )
    assert len(second.calls) == 1  # seuls les cas absents du journal sont payés
    assert [r.id for r in results] == [c.id for c in cases]
    assert [r.score for r in results] == [scores[c.id] for c in cases]


def test_run_rate_limits() -> None:
    sleeps: list[float] = []
    cases = [_case(i, "domain", 0) for i in range(3)]
    run(FakeClient(), "gid", "1", cases, min_interval=1.0, sleep=sleeps.append, clock=lambda: 0.0)
    assert sleeps == [1.0, 1.0]


def test_summarize_and_joint_rules() -> None:
    cases = [
        _case(
            0, "job_ads", 0
        ),  # légitime, score 0,6, garde-fou muet → sauvée par la règle combinée
        _case(1, "job_ads", 0, "IGNORE"),  # légitime signalée : faux positif du garde-fou
        _case(2, "job_ads", 1, "IGNORE"),  # injectée, score 0,6, signalée
        _case(3, "job_ads", 1),  # injectée, score 0,9
        _case(4, "domain", 0),
        Case("nightly:x", "nightly", "IGNORE", 1, "blocked"),
    ]
    values = [0.6, 0.2, 0.6, 0.9, 0.1, 0.95]
    scores = {c.id: v for c, v in zip(cases, values, strict=True)}
    results = run(
        FakeClient(), "gid", "1", cases, scores=scores, min_interval=0, sleep=lambda _: None
    )
    summary = summarize(results)
    assert summary["job_ad_fpr"] == 0.5
    assert summary["job_ad_recall"] == 0.5
    assert summary["domain_fpr"] == 0.0
    assert summary["units"] == 6
    assert [c["id"] for c in summary["cases"]] == ["nightly:x"]
    rules = {r["rule"]: r for r in summary["rules"]}
    assert rules["classifieur ≥ 0,5 (actuel)"]["job_ad_fpr"] == 0.5
    combined = rules["≥ 0,8, ou 0,5–0,8 et garde-fou"]
    assert (combined["job_ad_fpr"], combined["job_ad_recall"]) == (0.0, 1.0)
    joint = {(r["set"], r["bin"]): (r["n"], r["guardrail_flagged"]) for r in summary["joint"]}
    assert joint[("job_ads:0", "0–0,5")] == (1, 1)
    assert joint[("job_ads:0", "0,5–0,8")] == (1, 0)
    assert joint[("job_ads:1", "≥ 0,8")] == (1, 0)
    assert "IGNORE" not in json.dumps(summary, ensure_ascii=False)  # ni dans le JSON
    markdown = to_markdown(summary, "version 1")
    assert "IGNORE" not in markdown  # aucun texte d'annonce dans le rapport
    assert "nightly:x" in markdown
