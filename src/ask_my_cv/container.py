from __future__ import annotations

from ask_my_cv.budget import InMemoryLedger
from ask_my_cv.embeddings import EmbeddingProvider, HashEmbedder
from ask_my_cv.input_guard import HeuristicDetector
from ask_my_cv.llm import FakeLLM, LLMProvider, ModelPricing, OllamaLLM
from ask_my_cv.pipeline import Deps
from ask_my_cv.prompting import load_template
from ask_my_cv.settings import ModelConfig, Settings
from ask_my_cv.vectorstore import InMemoryVectorStore


def build_embedder(settings: Settings) -> EmbeddingProvider:
    return HashEmbedder(dim=settings.embed_dim)


def build_provider(model: ModelConfig, settings: Settings) -> LLMProvider:
    pricing = ModelPricing(model.input_per_mtok, model.output_per_mtok)
    if model.provider == "fake":
        return FakeLLM(id=model.id, pricing=pricing)
    return OllamaLLM(id=model.id, model=model.model, base_url=settings.ollama_url, pricing=pricing)


def build_deps(settings: Settings) -> Deps:
    return Deps(
        embedder=build_embedder(settings),
        store=InMemoryVectorStore.load(settings.index_path),
        detector=HeuristicDetector(),
        ledger=InMemoryLedger(
            daily_cap_usd=settings.daily_cap_usd,
            per_visitor_limit=settings.per_visitor_limit,
            window_s=settings.visitor_window_s,
        ),
        template=load_template(settings.prompt_path),
        providers={m.id: build_provider(m, settings) for m in settings.models},
        settings=settings,
    )
