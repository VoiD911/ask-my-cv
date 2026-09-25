import json

from ask_my_cv.events import Done, StageEnd, StageStart, Token


def test_events_serialize_with_type() -> None:
    assert json.loads(StageStart(name="llm", ts=1.0).model_dump_json())["type"] == "stage.start"
    end = StageEnd(name="llm", status="ok", duration_ms=12.5, attrs={"provider": "fake:echo"})
    assert json.loads(end.model_dump_json()) == {
        "type": "stage.end",
        "name": "llm",
        "status": "ok",
        "duration_ms": 12.5,
        "attrs": {"provider": "fake:echo"},
    }
    assert Token(text="Bon").type == "token"


def test_done_has_no_override_by_default() -> None:
    done = Done(
        tokens_in=10, tokens_out=5, cost_usd=0.0, latency_ms=3.0, sources=["[1] Expérience"]
    )
    assert done.answer_override is None
    assert done.type == "done"
