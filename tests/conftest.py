from collections.abc import Callable
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
