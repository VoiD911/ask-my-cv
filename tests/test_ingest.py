from pathlib import Path

import pytest

from ask_my_cv.embeddings import HashEmbedder
from ask_my_cv.ingest import build_index, chunk_markdown, main
from ask_my_cv.vectorstore import InMemoryVectorStore

SAMPLE = """# Alex Martin

## Expérience
Ingénieur MLOps chez Acme (2022-2026). Pipelines d'entraînement, déploiement canary.

## Compétences
Python, FastAPI, Terraform, AWS, OpenTelemetry.

## Contact
alex.martin@example.com
"""


def test_chunk_markdown_splits_on_sections() -> None:
    chunks = chunk_markdown(SAMPLE)
    assert [c.section for c in chunks] == ["Expérience", "Compétences", "Contact"]
    assert [c.id for c in chunks] == ["c1", "c2", "c3"]
    assert chunks[1].text == "Python, FastAPI, Terraform, AWS, OpenTelemetry."


def test_long_section_is_split_on_paragraphs() -> None:
    md = "## A\n\n" + "\n\n".join(["x" * 300] * 4)
    chunks = chunk_markdown(md, max_chars=700)
    assert len(chunks) == 2
    assert all(c.section == "A" for c in chunks)


async def test_build_index_retrieves_relevant_section() -> None:
    embedder = HashEmbedder(dim=256)
    store = await build_index(SAMPLE, embedder)
    [query] = await embedder.embed(["Compétences Python Terraform"])
    hits = await store.search(query, k=1)
    assert hits[0].chunk.section == "Compétences"


def test_cli_writes_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cv = tmp_path / "cv.md"
    cv.write_text(SAMPLE, encoding="utf-8")
    out = tmp_path / "index.json"
    settings = tmp_path / "settings.yaml"
    settings.write_text(
        "default_model: fake:echo\nfallback_chain: [fake:echo]\n"
        "models: [{id: fake:echo, provider: fake}]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASK_SETTINGS", str(settings))
    main(["--cv", str(cv), "--out", str(out)])
    assert len(InMemoryVectorStore.load(out)) == 3
