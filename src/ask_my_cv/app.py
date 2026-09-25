from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ask_my_cv.events import Event
from ask_my_cv.pipeline import Deps, run_pipeline


class AskRequest(BaseModel):
    question: str = Field(max_length=2000)
    model: str | None = None


def _sse(event: Event) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def create_app(deps: Deps | None = None) -> FastAPI:
    app = FastAPI(title="ask-my-cv", version="0.1.0")
    state: dict[str, Deps | None] = {"deps": deps}

    def get_deps() -> Deps:
        current = state["deps"]
        if current is None:
            from ask_my_cv.container import build_deps
            from ask_my_cv.settings import load_settings

            current = build_deps(load_settings())
            state["deps"] = current
        return current

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/models")
    async def models() -> dict[str, object]:
        settings = get_deps().settings
        return {
            "default": settings.default_model,
            "models": [{"id": m.id, "provider": m.provider} for m in settings.models if m.public],
        }

    @app.post("/ask")
    async def ask(body: AskRequest, request: Request) -> StreamingResponse:
        current = get_deps()
        ip = request.client.host if request.client else "unknown"
        visitor = hashlib.sha256(f"{current.settings.visitor_salt}:{ip}".encode()).hexdigest()[:16]
        queue: asyncio.Queue[Event | None] = asyncio.Queue()

        async def produce() -> None:
            try:
                await run_pipeline(
                    body.question,
                    body.model or current.settings.default_model,
                    visitor,
                    current,
                    queue.put_nowait,
                )
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


app = create_app()
