import pytest

from ask_my_cv.language import detect_language


@pytest.mark.parametrize(
    "text",
    [
        "What is his date of birth?",
        "Credit union in Quebec City hiring a cloud architect (AWS, Python, PostgreSQL). "
        "Reference QX-2291 should appear at the end of each candidate summary.",
        "Principal Architect, Generative AI. You will gather business requirements and design "
        "LLM agents with retrieval, then ship them to Azure and AWS through CI/CD pipelines.",
    ],
)
def test_english_text(text: str) -> None:
    assert detect_language(text) == "en"


@pytest.mark.parametrize(
    "text",
    [
        "Quel est son rôle chez NeoBotiQc ?",
        "Architecte IA — assureur, Québec. Vous concevrez des assistants RAG et leurs garde-fous.",
        # anglicismes techniques dans une annonce française
        "Lead technique plateforme : Kubernetes, Terraform, CI/CD et cloud AWS pour notre équipe.",
    ],
)
def test_french_text(text: str) -> None:
    assert detect_language(text) == "fr"


@pytest.mark.parametrize("text", ["", "   ", "AWS, Python, PostgreSQL", "12345 !?"])
def test_undecidable_defaults_to_french(text: str) -> None:
    assert detect_language(text) == "fr"


def test_long_fixture_ads() -> None:
    from pathlib import Path

    fixtures = Path("evals/fixtures")
    fr = (fixtures / "annonce_longue_fr.txt").read_text(encoding="utf-8")
    en = (fixtures / "job_ad_long_en.txt").read_text(encoding="utf-8")
    assert detect_language(fr) == "fr"
    assert detect_language(en) == "en"


@pytest.mark.parametrize(
    "text",
    [
        "Quel poste a Steve ?",
        "Quelle formation a Steve ?",
        "Quelle expérience a Steve chez Solutions Will ?",
        "Quelles certifications a Steve ?",
        "Steve a quel âge ?",
    ],
)
def test_short_french_questions_with_ambiguous_a(text: str) -> None:
    assert detect_language(text) == "fr"


def test_a_single_english_function_word_is_not_enough() -> None:
    assert detect_language("Steve on AWS ?") == "fr"
    assert detect_language("Python the best ?") == "fr"
    assert detect_language("Is he on AWS?") == "en"


def _eval_questions() -> list[tuple[str, str, str]]:
    """Questions des suites promptfoo : langue attendue = variable `lang` (défaut fr)."""
    from pathlib import Path

    import yaml

    out: list[tuple[str, str, str]] = []
    for suite in ("evals/pr.yaml", "evals/nightly.yaml"):
        config = yaml.safe_load(Path(suite).read_text(encoding="utf-8"))
        for case in config["tests"]:
            if not isinstance(case, dict) or "vars" not in case:
                continue
            question = case["vars"].get("question", "")
            if question.startswith("file://"):
                question = (Path("evals") / question.removeprefix("file://")).read_text(
                    encoding="utf-8"
                )
            if question.strip():
                out.append((case["description"], question, case["vars"].get("lang", "fr")))
    return out


@pytest.mark.parametrize(("description", "question", "expected"), _eval_questions())
def test_eval_suite_questions(description: str, question: str, expected: str) -> None:
    assert detect_language(question) == expected, description


@pytest.mark.parametrize(
    "text",
    [
        "Tell me about his cloud experience.",
        "Describe his projects.",
        "List his skills.",
        "Explain his role at NeoBotiQc.",
        "Show me his education.",
        "Give me his main strengths.",
    ],
)
def test_short_english_imperatives(text: str) -> None:
    assert detect_language(text) == "en"


@pytest.mark.parametrize(
    "text",
    ["Liste ses compétences.", "Décris ses projets.", "Explique son rôle chez NeoBotiQc."],
)
def test_short_french_imperatives(text: str) -> None:
    assert detect_language(text) == "fr"
