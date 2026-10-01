from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ask_my_cv.budget import BudgetExceeded, BudgetLedger, RateLimited
from ask_my_cv.embeddings import EmbeddingProvider
from ask_my_cv.events import Answer, Done, LLMProgress
from ask_my_cv.guardrail import (
    GUARDRAIL_PROVIDER_ID,
    USD_PER_UNIT,
    GuardrailBreaker,
    GuardrailChecker,
    GuardrailStatus,
    is_ad_like,
    log_metric,
    text_units,
)
from ask_my_cv.input_guard import InjectionDetector, check_input
from ask_my_cv.language import detect_language
from ask_my_cv.llm import LLMError, LLMProvider, TokenUsage, estimate_tokens
from ask_my_cv.output_guard import check_output, is_refusal, normalize_refusal
from ask_my_cv.prompting import PromptTemplate
from ask_my_cv.settings import Settings
from ask_my_cv.stages import Emit, StageBlocked, StageRecorder, stage, tracer
from ask_my_cv.text import fold_format
from ask_my_cv.vectorstore import VectorStore
from ask_my_cv.visitor import weekly_pseudonym

logger = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 10_000

BLOCK_MESSAGES = {
    "invalid_question": "Question vide ou trop longue.",
    "unknown_model": "Ce modèle n'est pas disponible.",
    "rate_limited": "Trop de questions d'affilée : réessaie dans un moment.",
    "budget_exceeded": "Le budget du jour est atteint : la démo passe en mode rediffusion.",
    "injection_detected": (
        "Requête bloquée par le détecteur d'injection. Rien n'a été envoyé au LLM."
    ),
    "guardrail_unavailable": (
        "L'analyse des annonces est momentanément indisponible : réessaie dans quelques "
        "minutes. Les questions courtes restent possibles."
    ),
    "prompt_leak": "Réponse retirée : elle exposait des instructions internes.",
    "pii": "Réponse retirée : elle contenait des données personnelles.",
    "ungrounded": "Réponse retirée : elle ne s'appuyait pas sur le CV.",
}
ERROR_MESSAGE = "Une erreur est survenue. La trace a été enregistrée."

# Issues comptées comme réponses retirées par le garde de sortie (tableau de bord, résumé).
WITHDRAWN_REASONS = frozenset({"prompt_leak", "pii", "ungrounded", "blocked"})

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
    # second avis sur les annonces collées ; None : classifieur seul (local, CI, non configuré)
    guardrail: GuardrailChecker | None = None
    # disjoncteur du garde-fou, un par processus (container.build_deps)
    breaker: GuardrailBreaker = field(default_factory=GuardrailBreaker)


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


async def _second_opinion(
    text: str,
    visitor: str,
    deps: Deps,
    recorder: StageRecorder,
    record_spend: Callable[[str, float], None],
    now: Callable[[], float],
) -> GuardrailStatus:
    """Garde-fou Bedrock sur une annonce que le classifieur laisse passer (`text` déjà replié).

    Échec isolé : ouvert, `error`, la décision du classifieur s'applique. Échecs répétés : le
    disjoncteur renvoie `unavailable` (échec fermé, voir `ask_my_cv.guardrail`). Les unités
    sont facturées même en cas d'échec ou d'annulation (estimation : la requête a pu être
    traitée), au poste du garde-fou, dans le même plafond journalier.
    """
    settings = deps.settings
    if deps.guardrail is None or not is_ad_like(text, settings.guardrail_min_chars):
        return "skipped"
    admission = deps.breaker.admit(visitor, now())
    if admission is None:
        log_metric("unavailable", 0.0)
        return "unavailable"
    units = text_units(text)
    status: GuardrailStatus = "error"
    started = time.perf_counter()
    try:
        async with asyncio.timeout(settings.guardrail_timeout_s):
            result = await deps.guardrail.check(text)
        units = result.units
        status = "block" if result.intervened else "pass"
        deps.breaker.record(visitor, now(), "success", admission)
    except asyncio.CancelledError:
        # visiteur déconnecté : ni échec du garde-fou (métriques), ni succès (disjoncteur)
        status = "cancelled"
        deps.breaker.record(visitor, now(), "cancelled", admission)
        raise
    except Exception as exc:
        # jamais le texte : seulement le type d'erreur
        logger.warning("guardrail_status=error error=%s", type(exc).__name__)
        recorder.set(guardrail_error=type(exc).__name__)
        deps.breaker.record(visitor, now(), "failure", admission)
    finally:
        # aussi pendant une annulation (visiteur déconnecté) : Bedrock facture quand même
        elapsed_ms = (time.perf_counter() - started) * 1000
        cost = units * USD_PER_UNIT
        record_spend(GUARDRAIL_PROVIDER_ID, cost)
        recorder.set(
            guardrail_units=units,
            guardrail_cost_usd=round(cost, 6),
            guardrail_ms=round(elapsed_ms, 1),
        )
        log_metric(status, elapsed_ms)
    return status


async def run_pipeline(
    question: str,
    model_id: str,
    visitor: str,
    deps: Deps,
    emit: Emit,
    now: Callable[[], float] = time.time,
    evaluation: bool = False,
    internal: bool = False,
) -> None:
    """`evaluation` : requête authentifiée par le jeton d'évaluation (compartiment de quota
    séparé, spans `quota` et `injection` marqués `xops.eval`) ; le plafond de dépense
    s'applique toujours.

    `internal` : trafic interne authentifié (tests de fumée, propriétaire). Le span racine
    `ask` porte un résumé analytique (#143) : `xops.traffic` (`public` ou `internal`, une
    évaluation est toujours interne), `xops.visitor` (pseudonyme hebdomadaire, trafic public
    seulement), `xops.result`, `xops.kind` (question ou annonce), `xops.language`, coût et
    latence. Jamais le texte soumis ni la réponse."""
    settings = deps.settings
    started = time.perf_counter()
    usage = Usage()
    sources: list[str] = []
    override: str | None = None
    answer = ""
    # écritures du registre en cours dans l'executor : référence forte jusqu'à leur fin
    pending: set[asyncio.Future[None]] = set()

    def record_spend(provider_id: str, cost: float) -> None:
        """Écrit la dépense hors de la boucle, sans attendre (aussi pendant une annulation)."""
        future = asyncio.get_running_loop().run_in_executor(
            None, deps.ledger.record, provider_id, cost, now()
        )
        pending.add(future)
        future.add_done_callback(pending.discard)
        future.add_done_callback(_log_record_failure)
        usage.cost_usd += cost

    with tracer.start_as_current_span("ask") as root:
        root.set_attribute(
            "langfuse.observation.input",
            json.dumps({"question_chars": len(question)}, ensure_ascii=False),
        )
        traffic = "internal" if evaluation or internal else "public"
        root.set_attribute("xops.traffic", traffic)
        if traffic == "public":
            root.set_attribute("xops.visitor", weekly_pseudonym(visitor, now()))
        root.set_attribute("xops.chars", len(question))
        outcome = "answered"
        try:
            async with stage("reception", emit) as st:
                question = question.strip()
                # NFKC peut multiplier la taille (U+FDFA : 18 caractères) : plafond aussi
                # après repli, avant tout détecteur (coût, fenêtres ONNX, garde-fou)
                screened = fold_format(question)
                if not question or max(len(question), len(screened)) > MAX_QUESTION_CHARS:
                    raise StageBlocked("invalid_question", length=len(question))
                # annonce collée : même critère que le garde-fou (`guardrail_min_chars`)
                root.set_attribute(
                    "xops.kind",
                    "ad" if is_ad_like(screened, settings.guardrail_min_chars) else "question",
                )
                if model_id not in settings.public_model_ids():
                    raise StageBlocked("unknown_model", model_len=len(model_id))
                st.set(model=model_id)
                root.set_attribute("xops.model", model_id)

            async with stage("quota", emit) as st:
                if evaluation:
                    st.set(eval=True)
                try:
                    async with asyncio.timeout(settings.stage_timeout_s):
                        if evaluation:
                            spent = await asyncio.to_thread(
                                deps.ledger.check,
                                visitor,
                                now(),
                                limit=settings.eval_limit_per_window,
                            )
                        else:
                            spent = await asyncio.to_thread(deps.ledger.check, visitor, now())
                except RateLimited:
                    raise StageBlocked("rate_limited") from None
                except BudgetExceeded:
                    raise StageBlocked("budget_exceeded") from None
                st.set(spent_today_usd=round(spent, 4))

            async with stage("injection", emit) as st:
                if evaluation:
                    st.set(eval=True)
                # même texte replié (NFKC, sans Cf) pour la longueur et les deux détecteurs
                verdict = check_input(deps.detector, screened, settings.injection_threshold)
                st.set(model_version=verdict.model_version, score=round(verdict.score, 3))
                root.set_attribute("xops.model_version", verdict.model_version)
                if verdict.blocked:
                    # le classifieur suffit : pas d'appel payant au garde-fou
                    st.set(guardrail="skipped")
                    raise StageBlocked("injection_detected")
                status = await _second_opinion(screened, visitor, deps, st, record_spend, now)
                st.set(guardrail=status)
                if status == "block":
                    raise StageBlocked("injection_detected", blocked_by="guardrail")
                if status == "unavailable":
                    raise StageBlocked("guardrail_unavailable")

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
                language = detect_language(question)
                system, user = deps.template.render(question, hits, canary, language=language)
                # langue détectée seulement (jamais le texte soumis)
                st.set(template=f"{deps.template.name}@{deps.template.version}", language=language)
                root.set_attribute("xops.language", language)
                root.set_attribute("xops.template", f"{deps.template.name}@{deps.template.version}")

            async with stage("llm", emit) as st:

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
                    record_spend(provider.id, provider.pricing.cost(tokens_in, tokens_out))
                    usage.tokens_in += tokens_in
                    usage.tokens_out += tokens_out

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
                answer = normalize_refusal(answer)
                checked = check_output(
                    answer,
                    canary=canary,
                    allowed_contacts=set(settings.allowed_contacts),
                    n_sources=len(hits),
                )
                if not checked.ok:
                    raise StageBlocked(checked.reason or "blocked")
            emit(Answer(text=answer))
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except StageBlocked as exc:
            outcome = exc.reason
            override = BLOCK_MESSAGES.get(exc.reason, ERROR_MESSAGE)
        except Exception:
            outcome = "error"
            override = ERROR_MESSAGE
        finally:
            root.set_attribute("xops.result", outcome)
            root.set_attribute("xops.refusal", outcome == "answered" and is_refusal(answer))
            root.set_attribute("xops.withdrawn", outcome in WITHDRAWN_REASONS)
            root.set_attribute("xops.cost_usd", round(usage.cost_usd, 6))
            root.set_attribute("xops.latency_ms", round((time.perf_counter() - started) * 1000, 1))
            root.set_attribute(
                "langfuse.observation.output",
                json.dumps(
                    {
                        "result": outcome,
                        "answer_chars": len(answer) if outcome == "answered" else 0,
                        "source_count": len(sources),
                        "tokens_in": usage.tokens_in,
                        "tokens_out": usage.tokens_out,
                    },
                    ensure_ascii=False,
                ),
            )
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
