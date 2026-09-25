from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from ask_my_cv.events import Event, StageEnd, StageStart, StageStatus

tracer = trace.get_tracer("ask_my_cv")

Emit = Callable[[Event], None]


class StageBlocked(Exception):
    """Une porte de sécurité refuse la requête : le pipeline s'arrête proprement."""

    def __init__(self, reason: str, **attrs: Any) -> None:
        super().__init__(reason)
        self.reason = reason
        self.attrs = attrs


class StageRecorder:
    """Poignée donnée à l'étape : attributs du span et drapeau de bascule."""

    def __init__(self) -> None:
        self.attrs: dict[str, Any] = {}
        self.fallback = False

    def set(self, **attrs: Any) -> None:
        self.attrs.update(attrs)


def _span_value(value: Any) -> str | int | float | bool:
    return value if isinstance(value, str | int | float | bool) else str(value)


@asynccontextmanager
async def stage(name: str, emit: Emit) -> AsyncIterator[StageRecorder]:
    recorder = StageRecorder()
    started = time.perf_counter()
    emit(StageStart(name=name, ts=time.time()))
    with tracer.start_as_current_span(
        name, record_exception=False, set_status_on_exception=False
    ) as span:
        status: StageStatus = "ok"
        try:
            yield recorder
            if recorder.fallback:
                status = "fallback"
        except StageBlocked as exc:
            status = "blocked"
            recorder.set(reason=exc.reason, **exc.attrs)
            raise
        except asyncio.CancelledError:
            status = "error"
            recorder.set(error="CancelledError")
            raise
        except Exception as exc:
            status = "error"
            recorder.set(error=type(exc).__name__)
            raise
        finally:
            for key, value in recorder.attrs.items():
                span.set_attribute(f"xops.{key}", _span_value(value))
            span.set_attribute("xops.status", status)
            if status == "error":
                span.set_status(Status(StatusCode.ERROR))
            emit(
                StageEnd(
                    name=name,
                    status=status,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    attrs=dict(recorder.attrs),
                )
            )
