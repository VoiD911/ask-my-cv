from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ask_my_cv.events import Event
from ask_my_cv.limits import MAX_BODY_BYTES, BodySizeLimit
from ask_my_cv.pipeline import MAX_QUESTION_CHARS, Deps, run_pipeline
from ask_my_cv.visitor import client_ip, visitor_id

logger = logging.getLogger(__name__)

EVAL_VISITOR = "eval"  # compartiment de quota des évaluations (jamais un pseudonyme hexadécimal)


def _is_eval(presented: str | None, expected: str | None) -> bool:
    """Comparaison en temps constant ; jeton absent, vide ou non configuré = visiteur ordinaire."""
    if not expected or not presented:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(max_length=MAX_QUESTION_CHARS)
    model: str | None = Field(default=None, max_length=64)


def _sse(event: Event) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def create_app(deps: Deps | None = None, flush: Callable[[], None] | None = None) -> FastAPI:
    """Fabrique : `uvicorn --factory ask_my_cv.app:create_app`. Tout est chargé et vérifié ici."""
    if deps is None:
        from ask_my_cv.container import build_deps
        from ask_my_cv.secrets import apply_ssm_secrets
        from ask_my_cv.settings import load_settings
        from ask_my_cv.telemetry import configure_tracing

        apply_ssm_secrets()
        settings = load_settings()
        flush = configure_tracing(settings)
        deps = build_deps(settings)
    else:
        flush = flush or (lambda: None)
    current = deps

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        for name, provider in current.providers.items():
            close = getattr(provider, "aclose", None)
            if close is None:
                continue
            try:
                await close()
            except Exception:
                logger.warning("fermeture de %s échouée", name, exc_info=True)

    app = FastAPI(title="ask-my-cv", version="0.1.0", lifespan=lifespan)
    app.add_middleware(BodySizeLimit, max_bytes=MAX_BODY_BYTES)
    if current.settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=current.settings.cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["content-type"],
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # jamais l'entrée du visiteur ni le nom d'un champ inattendu dans la réponse
        details = [
            {
                "loc": [
                    p
                    for p in e["loc"]
                    if not isinstance(p, str) or p == "body" or p in AskRequest.model_fields
                ],
                "msg": e["msg"],
                "type": e["type"],
            }
            for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": details})

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "detector": current.detector.version}

    @app.get("/models")
    async def models() -> dict[str, object]:
        settings = current.settings
        return {
            "default": settings.default_model,
            "models": [{"id": m.id, "provider": m.provider} for m in settings.models if m.public],
        }

    @app.post("/ask")
    async def ask(body: AskRequest, request: Request) -> StreamingResponse:
        evaluation = _is_eval(request.headers.get("x-eval-token"), current.settings.eval_token)
        if evaluation:
            visitor = EVAL_VISITOR
        else:
            peer = request.client.host if request.client else None
            ip = client_ip(request.headers, peer, current.settings.trusted_proxy)
            visitor = visitor_id(ip, current.settings.visitor_salt)
        queue: asyncio.Queue[Event | None] = asyncio.Queue()

        async def produce() -> None:
            try:
                await run_pipeline(
                    body.question,
                    body.model or current.settings.default_model,
                    visitor,
                    current,
                    queue.put_nowait,
                    evaluation=evaluation,
                )
            finally:
                try:
                    await asyncio.to_thread(flush)
                except Exception:
                    logger.warning("envoi des traces échoué", exc_info=True)
                finally:
                    queue.put_nowait(None)

        async def stream() -> AsyncIterator[str]:
            task = asyncio.create_task(produce())
            try:
                while (event := await queue.get()) is not None:
                    yield _sse(event)
            finally:
                task.cancel()

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app
