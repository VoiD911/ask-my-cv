import hashlib
import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "smoke_prod.py"
spec = importlib.util.spec_from_file_location("smoke_prod", _SCRIPT_PATH)
assert spec and spec.loader
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_check_raises_system_exit_with_message_when_not_ok() -> None:
    with pytest.raises(SystemExit, match="ÉCHEC : motif"):
        smoke.check(False, "motif")


def test_check_does_nothing_when_ok() -> None:
    smoke.check(True, "peu importe")


def test_body_hash_matches_what_cloudfront_oac_requires() -> None:
    body, headers = smoke.signed_body({"question": "Où ?"})
    assert headers["x-amz-content-sha256"] == hashlib.sha256(body).hexdigest()


def test_parse_sse_reads_events_in_order() -> None:
    raw = 'event: stage.start\ndata: {"name": "reception"}\n\nevent: done\ndata: {"trace_id": "t"}\n\n'  # noqa: E501
    assert smoke.parse_sse(raw) == [
        ("stage.start", {"name": "reception"}),
        ("done", {"trace_id": "t"}),
    ]


def test_rate_limited_message_matches_the_api() -> None:
    from ask_my_cv.pipeline import BLOCK_MESSAGES

    assert smoke.RATE_LIMITED == BLOCK_MESSAGES["rate_limited"]
