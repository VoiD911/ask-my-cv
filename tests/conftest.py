import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ask_my_cv.budget import InMemoryLedger
from ask_my_cv.embeddings import HashEmbedder
from ask_my_cv.ingest import build_index
from ask_my_cv.input_guard import HeuristicDetector, InjectionDetector
from ask_my_cv.llm import FakeLLM, LLMProvider
from ask_my_cv.pipeline import Deps
from ask_my_cv.prompting import PromptTemplate
from ask_my_cv.settings import ModelConfig, Settings
from ask_my_cv.vectorstore import InMemoryVectorStore

_exporter = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_exporter))
trace.set_tracer_provider(_provider)


@pytest.fixture(autouse=True)
def isolated_aws(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Jamais de profil ni d'identifiants réels : aucun test ne peut joindre AWS."""
    empty = tmp_path_factory.getbasetemp() / "aws-empty"
    empty.mkdir(exist_ok=True)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(empty / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(empty / "credentials"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ca-central-1")


@pytest.fixture
def promoted_model() -> Path:
    """Modèle promu téléchargé (`models/model.onnx`) : ignoré s'il manque, sauf en CI.

    `REQUIRE_PROMOTED_MODEL=1` (job `test` de ci.yml, après téléchargement et cosign) change
    l'absence en échec : la promotion est toujours testée avec le vrai modèle avant fusion.
    """
    path = Path("models/model.onnx")
    if not path.exists():
        if os.environ.get("REQUIRE_PROMOTED_MODEL") == "1":
            pytest.fail("REQUIRE_PROMOTED_MODEL=1 mais models/model.onnx est absent")
        pytest.skip("modèle promu non téléchargé")
    return path


@pytest.fixture
def spans() -> InMemorySpanExporter:
    _exporter.clear()
    return _exporter


SAMPLE_CV = """# Alex Martin

## Expérience
Ingénieur MLOps chez Acme (2022-2026). Pipelines d'entraînement, déploiement canary, dérive.

## Compétences
Python, FastAPI, Terraform, AWS, OpenTelemetry.

## Contact
alex.martin@example.com
"""


@pytest.fixture
async def store() -> InMemoryVectorStore:
    return await build_index(SAMPLE_CV, HashEmbedder(dim=64))


@pytest.fixture
def make_deps(store: InMemoryVectorStore) -> Callable[..., Deps]:
    def _make(
        *,
        providers: dict[str, LLMProvider] | None = None,
        detector: InjectionDetector | None = None,
        ledger: InMemoryLedger | None = None,
        **overrides: Any,
    ) -> Deps:
        providers = providers or {"fake:echo": FakeLLM(id="fake:echo")}
        settings = Settings(
            models=[ModelConfig(id=pid, provider="fake") for pid in providers],
            default_model=next(iter(providers)),
            fallback_chain=list(providers),
            embed_dim=64,
            allowed_contacts=["alex.martin@example.com"],
            **overrides,
        )
        return Deps(
            embedder=HashEmbedder(dim=64),
            store=store,
            detector=detector or HeuristicDetector(),
            ledger=ledger
            or InMemoryLedger(daily_cap_usd=1.0, per_visitor_limit=100, window_s=3600),
            template=PromptTemplate(name="answer", version="v1", system="Règles {canary}"),
            providers=providers,
            settings=settings,
        )

    return _make
