import ast
import asyncio
from pathlib import Path

import pytest
from opentelemetry.trace import StatusCode

from ask_my_cv import pipeline
from ask_my_cv.events import Event, StageEnd
from ask_my_cv.stages import PIPELINE_STAGES, StageBlocked, stage


async def test_stage_emits_start_and_end_and_span(spans) -> None:
    events: list[Event] = []
    async with stage("demo", events.append) as st:
        st.set(score=0.5)
    assert [e.type for e in events] == ["stage.start", "stage.end"]
    end = events[1]
    assert isinstance(end, StageEnd)
    assert end.status == "ok"
    assert end.attrs == {"score": 0.5}
    finished = spans.get_finished_spans()
    assert finished[-1].name == "demo"
    assert finished[-1].attributes["xops.score"] == 0.5
    assert finished[-1].attributes["xops.status"] == "ok"


async def test_stage_blocked_records_reason() -> None:
    events: list[Event] = []
    with pytest.raises(StageBlocked):
        async with stage("injection", events.append):
            raise StageBlocked("injection_detected", score=0.9)
    end = events[-1]
    assert isinstance(end, StageEnd)
    assert end.status == "blocked"
    assert end.attrs == {"reason": "injection_detected", "score": 0.9}


async def test_stage_error_records_exception_type() -> None:
    events: list[Event] = []
    with pytest.raises(ValueError):
        async with stage("retrieval", events.append):
            raise ValueError("boom")
    end = events[-1]
    assert isinstance(end, StageEnd)
    assert end.status == "error"
    assert end.attrs == {"error": "ValueError"}


async def test_stage_fallback_status() -> None:
    events: list[Event] = []
    async with stage("llm", events.append) as st:
        st.fallback = True
    end = events[-1]
    assert isinstance(end, StageEnd)
    assert end.status == "fallback"


async def test_stage_cancelled_is_recorded_as_error() -> None:
    events: list[Event] = []
    with pytest.raises(asyncio.CancelledError):
        async with stage("llm", events.append):
            raise asyncio.CancelledError
    end = events[-1]
    assert isinstance(end, StageEnd)
    assert end.status == "error"
    assert end.attrs == {"error": "CancelledError"}


async def test_blocked_stage_span_is_not_an_error(spans) -> None:
    with pytest.raises(StageBlocked):
        async with stage("injection", lambda e: None):
            raise StageBlocked("injection_detected")
    span = spans.get_finished_spans()[-1]
    assert span.status.status_code is not StatusCode.ERROR
    assert not span.events


async def test_failed_stage_span_is_an_error(spans) -> None:
    with pytest.raises(ValueError):
        async with stage("retrieval", lambda e: None):
            raise ValueError("boom")
    assert spans.get_finished_spans()[-1].status.status_code is StatusCode.ERROR


def test_pipeline_opens_declared_stages_in_order() -> None:
    """PIPELINE_STAGES (lu par la page /architecture du site) suit le code réel."""
    tree = ast.parse(Path(pipeline.__file__).read_text(encoding="utf-8"))
    calls = sorted(
        (node.lineno, node.args[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "stage"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    )
    assert tuple(name for _, name in calls) == PIPELINE_STAGES
