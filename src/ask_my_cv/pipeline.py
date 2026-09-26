from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from ask_my_cv.budget import BudgetExceeded, BudgetLedger, RateLimited
from ask_my_cv.embeddings import EmbeddingProvider
from ask_my_cv.events import Answer, Done, LLMProgress
from ask_my_cv.input_guard import InjectionDetector, check_input
from ask_my_cv.llm import LLMError, LLMProvider, TokenUsage, estimate_tokens
from ask_my_cv.output_guard import check_output
from ask_my_cv.prompting import PromptTemplate
from ask_my_cv.settings import Settings
from ask_my_cv.stages import Emit, StageBlocked, StageRecorder, stage, tracer
from ask_my_cv.vectorstore import VectorStore

logger = logging.getLogger(__name__)

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

# attente des écritures du registre à la fin de la requête : reste courte pour garder
# la latence totale sous le timeout Lambda de 60 s, même en cas de registre lent.
LEDGER_WAIT_S = 3.0


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


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


Account = Callable[[LLMProvider, str, TokenUsage | None], None]


def _log_record_failure(future: asyncio.Future[None]) -> None:
    """Récupère toujours le résultat : ni exception relancée, ni « never retrieved »."""
    if future.cancelled():
        return
    if (exc := future.exception()) is not None:
        logger.warning("registre des dépenses indisponible", exc_info=exc)


def _cancelling() -> bool:
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0


async def _stream_llm(
    chain: list[LLMProvider],
    system: str,
    user: str,
    emit: Emit,
    settings: Settings,
    recorder: StageRecorder,
    account: Account,
) -> tuple[LLMProvider, str, TokenUsage | None]:
    """Génère côté serveur. Aucun texte ne sort : on peut donc basculer à tout moment."""
    failed: list[str] = []
    chars = 0
    async with asyncio.timeout(settings.llm_deadline_s):
        for provider in chain:
            parts: list[str] = []
            reported: TokenUsage | None = None
            stream = provider.stream(system, user)
            try:
                async with asyncio.timeout(settings.first_token_timeout_s):
                    first = await anext(stream)
                if isinstance(first, TokenUsage):
                    reported = first
                else:
                    parts.append(first)
                    chars += len(first)
                    emit(LLMProgress(tokens=max(1, chars // 4)))
                async for piece in stream:
                    if isinstance(piece, TokenUsage):
                        reported = piece
                        continue
                    parts.append(piece)
                    chars += len(piece)
                    emit(LLMProgress(tokens=max(1, chars // 4)))
                if not parts:
                    # rien à répondre au visiteur (seul un TokenUsage a pu être reçu) :
                    # on facture quand même via le except ci-dessous et on bascule
                    raise LLMError(f"{provider.id} : aucun texte reçu")
            except asyncio.CancelledError:
                # délai global dépassé ou visiteur déconnecté : les tokens produits sont facturés
                account(provider, "".join(parts), reported)
                raise
            except Exception:
                account(provider, "".join(parts), reported)
                failed.append(provider.id)
                recorder.set(failed=",".join(failed))
                continue
            finally:
                with contextlib.suppress(Exception):  # ne masque pas CancelledError
                    await stream.aclose()
            recorder.set(provider=provider.id)
            if failed:
                recorder.fallback = True
            return provider, "".join(parts), reported
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
    usage = Usage()
    sources: list[str] = []
    override: str | None = None
    # écritures du registre en cours dans l'executor : référence forte jusqu'à leur fin
    pending: set[asyncio.Future[None]] = set()
    with tracer.start_as_current_span("ask") as root:
        try:
            async with stage("reception", emit) as st:
                question = question.strip()
                if not question or len(question) > MAX_QUESTION_CHARS:
                    raise StageBlocked("invalid_question", length=len(question))
                if model_id not in settings.public_model_ids():
                    raise StageBlocked("unknown_model", model_len=len(model_id))
                st.set(model=model_id)

            async with stage("quota", emit) as st:
                try:
                    async with asyncio.timeout(settings.stage_timeout_s):
                        spent = await asyncio.to_thread(deps.ledger.check, visitor, now())
                except RateLimited:
                    raise StageBlocked("rate_limited") from None
                except BudgetExceeded:
                    raise StageBlocked("budget_exceeded") from None
                st.set(spent_today_usd=round(spent, 4))

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
                async with asyncio.timeout(settings.stage_timeout_s):
                    hits = await deps.store.search(query_vector, settings.top_k)
                sources = [f"[{i}] {hit.chunk.section}" for i, hit in enumerate(hits, 1)]
                st.set(hits=len(hits), top_score=round(hits[0].score, 3) if hits else 0.0)

            async with stage("prompt", emit) as st:
                canary = secrets.token_hex(8)
                system, user = deps.template.render(question, hits, canary)
                st.set(template=f"{deps.template.name}@{deps.template.version}")

            async with stage("llm", emit) as st:
                loop = asyncio.get_running_loop()

                def account(provider: LLMProvider, text: str, reported: TokenUsage | None) -> None:
                    if reported is not None:
                        tokens_in, tokens_out = reported.tokens_in, reported.tokens_out
                        st.set(usage_source="reported", stop_reason=reported.stop_reason or "")
                    else:
                        # même sans texte (échec avant le premier jeton, déconnexion) : Bedrock
                        # a déjà lu le prompt, donc l'entrée est facturée sur l'estimation
                        tokens_in = estimate_tokens(system + user)
                        tokens_out = estimate_tokens(text) if text else 0
                        st.set(usage_source="estimated", stop_reason="")
                    cost = provider.pricing.cost(tokens_in, tokens_out)
                    # hors de la boucle, sans attendre : appelé aussi pendant une annulation
                    future = loop.run_in_executor(
                        None, deps.ledger.record, provider.id, cost, now()
                    )
                    pending.add(future)
                    future.add_done_callback(pending.discard)
                    future.add_done_callback(_log_record_failure)
                    usage.tokens_in += tokens_in
                    usage.tokens_out += tokens_out
                    usage.cost_usd += cost

                chain = _provider_chain(model_id, deps)
                provider, answer, reported = await _stream_llm(
                    chain, system, user, emit, settings, st, account
                )
                account(provider, answer, reported)
                st.set(
                    tokens_in=usage.tokens_in,
                    tokens_out=usage.tokens_out,
                    cost_usd=round(usage.cost_usd, 6),
                )

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
            interrupted = False
            if pending and not _cancelling():
                # fin normale : les dépenses sont écrites avant Done, sans bloquer la boucle ;
                # annulation : on n'attend pas, les écritures finissent dans leur thread
                try:
                    _, not_done = await asyncio.wait(set(pending), timeout=LEDGER_WAIT_S)
                    if not_done:
                        logger.warning(
                            "registre des dépenses : %d écriture(s) non terminée(s)",
                            len(not_done),
                        )
                except asyncio.CancelledError:
                    interrupted = True
            emit(
                Done(
                    tokens_in=usage.tokens_in,
                    tokens_out=usage.tokens_out,
                    cost_usd=round(usage.cost_usd, 6),
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    sources=sources,
                    answer_override=override,
                    trace_id=format(root.get_span_context().trace_id, "032x"),
                )
            )
            if interrupted:
                raise asyncio.CancelledError
