from pathlib import Path

import pytest

from ask_my_cv.aws.bedrock import BedrockEmbedder
from ask_my_cv.aws.dynamo import DynamoVectorStore
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


def test_cli_writes_to_dynamodb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cv = tmp_path / "cv.md"
    cv.write_text(SAMPLE, encoding="utf-8")
    settings = tmp_path / "settings.yaml"
    settings.write_text(
        "default_model: fake:echo\nfallback_chain: [fake:echo]\n"
        "models: [{id: fake:echo, provider: fake}]\n"
        "embedder: bedrock\nembed_dim: 1024\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASK_SETTINGS", str(settings))
    written: list[list] = []

    def fake_write(self, chunks, vectors):
        written.append(list(chunks))

    async def fake_embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1024 for _ in texts]

    monkeypatch.setattr(DynamoVectorStore, "write", fake_write)
    monkeypatch.setattr(BedrockEmbedder, "embed", fake_embed)
    main(["--cv", str(cv), "--target", "dynamodb"])
    assert len(written) == 1
    assert len(written[0]) == 3


def test_cli_dynamodb_target_requires_the_bedrock_embedder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cv = tmp_path / "cv.md"
    cv.write_text(SAMPLE, encoding="utf-8")
    settings = tmp_path / "settings.yaml"
    settings.write_text(
        "default_model: fake:echo\nfallback_chain: [fake:echo]\n"
        "models: [{id: fake:echo, provider: fake}]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASK_SETTINGS", str(settings))
    with pytest.raises(SystemExit):
        main(["--cv", str(cv), "--target", "dynamodb"])


ROOT = Path(__file__).resolve().parent.parent


def test_only_french_cv_is_ingested() -> None:
    """data/cv.en.md (traduction pour la page /en/cv) ne doit jamais entrer dans l'index RAG."""
    from ask_my_cv.settings import Settings

    assert Settings.model_fields["cv_path"].default == Path("data/cv.md")
    for name in ("settings.yaml", "settings.ci.yaml", "settings.aws.yaml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "cv.en" not in text
        paths = [
            line.split(":", 1)[1].strip()
            for line in text.splitlines()
            if line.startswith("cv_path:")
        ]
        assert paths in ([], ["data/cv.md"]), name
    # ni copiée dans l'image de l'API (COPY data ./data)
    assert "data/cv.en.md" in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()


def test_cli_reads_only_cv_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """L'ingestion lit le seul fichier `cv_path`, jamais un voisin comme cv.en.md."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "cv.md").write_text("## Profil\nArchitecte.\n", encoding="utf-8")
    (tmp_path / "data" / "cv.en.md").write_text("## Profile\nArchitect.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    settings = tmp_path / "settings.yaml"
    settings.write_text(
        "default_model: fake:echo\nfallback_chain: [fake:echo]\n"
        "models: [{id: fake:echo, provider: fake}]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ASK_SETTINGS", str(settings))
    read: list[Path] = []
    original = Path.read_text

    def spy(self: Path, *args: object, **kwargs: object) -> str:
        read.append(self)
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", spy)
    main(["--out", str(tmp_path / "index.json")])
    cv_reads = [p for p in read if p.name.startswith("cv")]
    assert [p.as_posix() for p in cv_reads] == ["data/cv.md"]
    assert len(InMemoryVectorStore.load(tmp_path / "index.json")) == 1
