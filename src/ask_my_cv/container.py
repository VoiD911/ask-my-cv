from __future__ import annotations

from ask_my_cv.embeddings import EmbeddingProvider, HashEmbedder
from ask_my_cv.llm import FakeLLM, LLMProvider, ModelPricing, OllamaLLM
from ask_my_cv.settings import ModelConfig, Settings


def build_embedder(settings: Settings) -> EmbeddingProvider:
    return HashEmbedder(dim=settings.embed_dim)


def build_provider(model: ModelConfig, settings: Settings) -> LLMProvider:
    pricing = ModelPricing(model.input_per_mtok, model.output_per_mtok)
    if model.provider == "fake":
        return FakeLLM(id=model.id, pricing=pricing)
    return OllamaLLM(id=model.id, model=model.model, base_url=settings.ollama_url, pricing=pricing)
