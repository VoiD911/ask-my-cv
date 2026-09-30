"""Cohérence des annonces de la suite de nuit avec le classifieur promu (v1.4.0, #118)."""

from pathlib import Path
from typing import Any

import yaml

from ask_my_cv.guardrail import AD_MIN_CHARS
from ask_my_cv.onnx_detector import OnnxDetector, load_manifest
from ask_my_cv.text import fold_format

NIGHTLY = Path("evals/nightly.yaml")


def ad_cases() -> list[dict[str, Any]]:
    tests = yaml.safe_load(NIGHTLY.read_text(encoding="utf-8"))["tests"]
    cases = []
    for test in tests:
        if not str(test.get("description", "")).startswith("annonce"):
            continue
        question = str(test["vars"]["question"])
        if question.startswith("file://"):
            path = NIGHTLY.parent / question.removeprefix("file://")
            question = path.read_text(encoding="utf-8")
        cases.append(
            {
                "description": test["description"],
                "question": fold_format(question.strip()),  # comme le pipeline
                "outcome": test["vars"].get("outcome"),
                "known": (test.get("metadata") or {}).get("knownIssue"),
            }
        )
    return cases


def test_only_the_long_english_ad_remains_a_known_false_positive() -> None:
    known = [(c["description"], c["known"]) for c in ad_cases() if c["known"]]
    assert known == [
        ("annonce EN — realistic long posting (~7,000 characters)", "known-fp-annonce-en")
    ]


def test_discreet_injections_stay_below_the_guardrail_threshold() -> None:
    """Classifieur seul : le cas teste le prompt, pas le garde-fou (non mesurable hors AWS)."""
    discreet = [c for c in ad_cases() if "discr" in c["description"]]
    assert len(discreet) == 2
    assert all(len(c["question"]) < AD_MIN_CHARS for c in discreet)


def test_nightly_ad_expectations_match_the_promoted_classifier(promoted_model: Path) -> None:
    manifest = load_manifest(Path("models/prod.json"))
    assert manifest is not None
    detector = OnnxDetector(Path("models") / manifest.file, manifest.sha256, manifest.version)
    for case in ad_cases():
        score = detector.score(case["question"])
        should_block = case["outcome"] == "blocked" or case["known"] is not None
        assert (score >= 0.5) == should_block, (case["description"], round(score, 3))
