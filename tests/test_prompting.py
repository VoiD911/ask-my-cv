from pathlib import Path

import pytest

from ask_my_cv.prompting import PromptTemplate, load_template
from ask_my_cv.vectorstore import Chunk, Hit


def test_render_numbers_sources_and_injects_canary() -> None:
    template = PromptTemplate(name="answer", version="v1", system="Règles. Marqueur : {canary}")
    hits = [
        Hit(Chunk("c1", "Expérience", "MLOps chez Acme"), 0.9),
        Hit(Chunk("c2", "Compétences", "Python"), 0.5),
    ]
    system, user = template.render("Quelle expérience ?", hits, canary="abc123")
    assert system == "Règles. Marqueur : abc123"
    assert "[1] (Expérience) MLOps chez Acme" in user
    assert "[2] (Compétences) Python" in user
    assert user.endswith("Question : Quelle expérience ?")


def test_render_without_sources() -> None:
    template = PromptTemplate(name="answer", version="v1", system="S {canary}")
    _, user = template.render("Q ?", [], canary="x")
    assert "(aucune)" in user


def test_load_template_reads_version_from_filename(tmp_path: Path) -> None:
    path = tmp_path / "answer@v7.md"
    path.write_text("Système {canary}\n", encoding="utf-8")
    template = load_template(path)
    assert (template.name, template.version, template.system) == (
        "answer",
        "v7",
        "Système {canary}",
    )


def test_load_template_requires_version(tmp_path: Path) -> None:
    path = tmp_path / "answer.md"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        load_template(path)


def test_prompt_v2_asks_for_the_exact_refusal() -> None:
    from ask_my_cv.output_guard import REFUSAL

    template = load_template(Path("prompts/answer@v2.md"))
    assert template.version == "v2"
    assert REFUSAL in template.system and "{canary}" in template.system


def test_prompt_v4_forbids_markdown_and_explains_job_ads() -> None:
    from ask_my_cv.output_guard import REFUSAL

    template = load_template(Path("prompts/answer@v4.md"))
    assert template.version == "v4"
    assert REFUSAL in template.system and "{canary}" in template.system
    assert "pas de Markdown" in template.system
    assert "annonce d’emploi" in template.system
    assert "Ne prête pas" in template.system
