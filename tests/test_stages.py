import pytest

from ask_my_cv.events import Event, StageEnd
from ask_my_cv.stages import StageBlocked, stage


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
