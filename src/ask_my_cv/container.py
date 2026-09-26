from __future__ import annotations

from typing import Any

from ask_my_cv.budget import BudgetLedger, InMemoryLedger
from ask_my_cv.embeddings import EmbeddingProvider, HashEmbedder
from ask_my_cv.input_guard import HeuristicDetector, InjectionDetector
from ask_my_cv.llm import FakeLLM, LLMProvider, ModelPricing, OllamaLLM
from ask_my_cv.onnx_detector import ModelIntegrityError, OnnxDetector, load_manifest
from ask_my_cv.pipeline import Deps
from ask_my_cv.prompting import load_template
from ask_my_cv.settings import ModelConfig, Settings
from ask_my_cv.vectorstore import InMemoryVectorStore, VectorStore

# (connexion, lecture) en secondes, par service. DynamoDB doit échouer vite : `check`/
# `spent_today` tournent désormais dans un thread du pool avec un timeout d'étape (étage quota de
# pipeline.py), mais un appel qui atteint son timeout continue d'occuper un thread de l'executor
# par défaut, d'où l'importance de délais courts ; `ledger.record` (étage llm), lui, reste
# synchrone sur la boucle d'événements (à en sortir, plan 1j). Bedrock lit un flux, la lecture
# borne l'écart maximal entre deux morceaux plutôt que la durée totale.
_TIMEOUTS = {"dynamodb": (2, 3), "bedrock-runtime": (3, 30)}


def aws_client(service: str, settings: Settings) -> Any:
    import boto3
    from botocore.config import Config

    connect, read = _TIMEOUTS.get(service, (3, 30))
    return boto3.client(
        service,
        region_name=settings.aws_region,
        config=Config(
            retries={"mode": "standard", "max_attempts": 3},
            connect_timeout=connect,
            read_timeout=read,
        ),
    )


def build_embedder(settings: Settings) -> EmbeddingProvider:
    if settings.embedder == "bedrock":
        from ask_my_cv.aws.bedrock import BedrockEmbedder

        return BedrockEmbedder(
            settings.embed_model, aws_client("bedrock-runtime", settings), dim=settings.embed_dim
        )
    return HashEmbedder(dim=settings.embed_dim)


def build_provider(model: ModelConfig, settings: Settings) -> LLMProvider:
    pricing = ModelPricing(model.input_per_mtok, model.output_per_mtok)
    if model.provider == "fake":
        return FakeLLM(id=model.id, pricing=pricing)
    if model.provider == "bedrock":
        from ask_my_cv.aws.bedrock import BedrockLLM

        return BedrockLLM(
            id=model.id,
            model_id=model.model,
            client=aws_client("bedrock-runtime", settings),
            pricing=pricing,
        )
    return OllamaLLM(id=model.id, model=model.model, base_url=settings.ollama_url, pricing=pricing)


def build_store(settings: Settings) -> VectorStore:
    if settings.vector_store == "dynamodb":
        from ask_my_cv.aws.dynamo import DynamoVectorStore

        return DynamoVectorStore(settings.chunks_table, aws_client("dynamodb", settings))
    return InMemoryVectorStore.load(settings.index_path)


def build_ledger(settings: Settings) -> BudgetLedger:
    if settings.ledger == "dynamodb":
        from ask_my_cv.aws.dynamo import DynamoLedger

        return DynamoLedger(
            settings.ledger_table,
            aws_client("dynamodb", settings),
            daily_cap_usd=settings.daily_cap_usd,
            per_visitor_limit=settings.per_visitor_limit,
            window_s=settings.visitor_window_s,
        )
    return InMemoryLedger(
        daily_cap_usd=settings.daily_cap_usd,
        per_visitor_limit=settings.per_visitor_limit,
        window_s=settings.visitor_window_s,
    )


def build_detector(settings: Settings) -> InjectionDetector:
    if settings.detector == "heuristic":
        return HeuristicDetector()
    manifest = load_manifest(settings.model_manifest)
    if manifest is None:
        raise ModelIntegrityError(
            f"detector: onnx mais aucun modèle promu dans {settings.model_manifest}"
        )
    return OnnxDetector(
        settings.model_manifest.parent / manifest.file, manifest.sha256, manifest.version
    )


def build_deps(settings: Settings) -> Deps:
    return Deps(
        embedder=build_embedder(settings),
        store=build_store(settings),
        detector=build_detector(settings),
        ledger=build_ledger(settings),
        template=load_template(settings.prompt_path),
        providers={m.id: build_provider(m, settings) for m in settings.models},
        settings=settings,
    )
