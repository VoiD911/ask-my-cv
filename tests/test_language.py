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
