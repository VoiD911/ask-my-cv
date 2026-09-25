from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from ask_my_cv.budget import BudgetExceeded, BudgetLedger, RateLimited
from ask_my_cv.embeddings import EmbeddingProvider
from ask_my_cv.events import Answer, Done, LLMProgress
from ask_my_cv.input_guard import InjectionDetector, check_input
from ask_my_cv.llm import LLMError, LLMProvider, estimate_tokens
from ask_my_cv.output_guard import check_output
from ask_my_cv.prompting import PromptTemplate
from ask_my_cv.settings import Settings
from ask_my_cv.stages import Emit, StageBlocked, StageRecorder, stage, tracer
from ask_my_cv.vectorstore import VectorStore

MAX_QUESTION_CHARS = 500

BLOCK_MESSAGES = {
    "invalid_question": "Question vide ou trop longue.",
    "unknown_model": "Ce modèle n'est pas disponible.",
    "rate_limited": "Trop de questions d'affilée : réessaie dans un moment.",
    "budget_exceeded": "Le budget du jour est atteint : la démo passe en mode rediffusion.",
    "injection_detected": (
        "Requête bloquée par le détecteur d'injection. Rien n'a été envoyé au LLM."
    ),
    "prompt_leak": "Réponse retirée : elle exposait des instructions internes.",
    "pii": "Réponse retirée : elle contenait des données personnelles.",
    "ungrounded": "Réponse retirée : elle ne s'appuyait pas sur le CV.",
}
ERROR_MESSAGE = "Une erreur est survenue. La trace a été enregistrée."


@dataclass
class Deps:
    embedder: EmbeddingProvider
    store: VectorStore
    detector: InjectionDetector
    ledger: BudgetLedger
    template: PromptTemplate
    providers: dict[str, LLMProvider]
    settings: Settings


def _provider_chain(model_id: str, deps: Deps) -> list[LLMProvider]:
    ids = [model_id] + [m for m in deps.settings.fallback_chain if m != model_id]
    return [deps.providers[i] for i in ids if i in deps.providers]


async def _stream_llm(
    chain: list[LLMProvider],
    system: str,
    user: str,
    emit: Emit,
    timeout_s: float,
    recorder: StageRecorder,
) -> tuple[LLMProvider, str]:
    failed: list[str] = []
    for provider in chain:
        parts: list[str] = []
        chars = 0
        try:
            async with asyncio.timeout(timeout_s):
                async for piece in provider.stream(system, user):
                    parts.append(piece)
                    chars += len(piece)
                    emit(LLMProgress(tokens=max(1, chars // 4)))
        except (LLMError, TimeoutError):
            if parts:
                # des tokens sont déjà partis : impossible de changer de modèle en cours de réponse
                raise
            failed.append(provider.id)
            continue
        recorder.set(provider=provider.id)
        if failed:
            recorder.fallback = True
            recorder.set(failed=",".join(failed))
        return provider, "".join(parts)
    raise LLMError(f"tous les fournisseurs ont échoué : {failed}")


async def run_pipeline(
    question: str,
    model_id: str,
    visitor: str,
    deps: Deps,
    emit: Emit,
    now: Callable[[], float] = time.time,
) -> None:
    settings = deps.settings
    started = time.perf_counter()
    tokens_in = tokens_out = 0
    cost = 0.0
    sources: list[str] = []
    override: str | None = None
    with tracer.start_as_current_span("ask") as root:
        try:
            async with stage("reception", emit) as st:
                question = question.strip()
                if not question or len(question) > MAX_QUESTION_CHARS:
                    raise StageBlocked("invalid_question", length=len(question))
                if model_id not in settings.public_model_ids():
                    raise StageBlocked("unknown_model", model=model_id)
                st.set(model=model_id)

            async with stage("quota", emit) as st:
                try:
                    deps.ledger.check(visitor, now())
                except RateLimited:
                    raise StageBlocked("rate_limited") from None
                except BudgetExceeded:
                    raise StageBlocked("budget_exceeded") from None
                st.set(spent_today_usd=round(deps.ledger.spent_today(now()), 4))

            async with stage("injection", emit) as st:
                verdict = check_input(deps.detector, question, settings.injection_threshold)
                st.set(model_version=verdict.model_version, score=round(verdict.score, 3))
                if verdict.blocked:
                    raise StageBlocked("injection_detected")

            async with stage("embedding", emit) as st:
                async with asyncio.timeout(settings.stage_timeout_s):
                    [query_vector] = await deps.embedder.embed([question])
                st.set(dim=len(query_vector))

            async with stage("retrieval", emit) as st:
                hits = await deps.store.search(query_vector, settings.top_k)
                sources = [f"[{i}] {hit.chunk.section}" for i, hit in enumerate(hits, 1)]
                st.set(hits=len(hits), top_score=round(hits[0].score, 3) if hits else 0.0)

            async with stage("prompt", emit) as st:
                canary = secrets.token_hex(8)
                system, user = deps.template.render(question, hits, canary)
                st.set(template=f"{deps.template.name}@{deps.template.version}")

            async with stage("llm", emit) as st:
                chain = _provider_chain(model_id, deps)
                provider, answer = await _stream_llm(
                    chain, system, user, emit, settings.stage_timeout_s, st
                )
                tokens_in = estimate_tokens(system + user)
                tokens_out = estimate_tokens(answer)
                cost = provider.pricing.cost(tokens_in, tokens_out)
                deps.ledger.record(provider.id, cost, now())
                st.set(tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=round(cost, 6))

            async with stage("output_guard", emit):
                checked = check_output(
                    answer,
                    canary=canary,
                    allowed_contacts=set(settings.allowed_contacts),
                    n_sources=len(hits),
                )
                if not checked.ok:
                    raise StageBlocked(checked.reason or "blocked")
            emit(Answer(text=answer))
        except StageBlocked as exc:
            override = BLOCK_MESSAGES.get(exc.reason, ERROR_MESSAGE)
        except Exception:
            override = ERROR_MESSAGE
        finally:
            emit(
                Done(
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=round(cost, 6),
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    sources=sources,
                    answer_override=override,
                    trace_id=format(root.get_span_context().trace_id, "032x"),
                )
            )
