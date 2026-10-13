import importlib.util
import io
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import requests

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "langfuse_purge.py"
spec = importlib.util.spec_from_file_location("langfuse_purge", _SCRIPT_PATH)
assert spec and spec.loader
purge_mod = importlib.util.module_from_spec(spec)
sys.modules["langfuse_purge"] = purge_mod
spec.loader.exec_module(purge_mod)

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
BASE = "https://us.cloud.langfuse.com"
SECRET_TEXT = "question masquée [e-mail]"


class FakeResponse:
    def __init__(
        self, status: int, payload: Any = None, headers: dict[str, str] | None = None
    ) -> None:
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.content = b"{}" if payload is not None else b""

    def json(self) -> Any:
        return self._payload


class FakeSession:
    """Client HTTP simulé : réponses en file, appels enregistrés, jamais de réseau."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


OLD = "2026-09-01T08:00:00.123Z"


def page(
    trace_ids: list[str], cursor: str | None = None, started: str | None = OLD
) -> FakeResponse:
    data = [
        {
            "id": f"o-{t}",
            "traceId": t,
            "startTime": started,
            "input": SECRET_TEXT,
            "output": SECRET_TEXT,
        }
        for t in trace_ids
    ]
    return FakeResponse(200, {"data": data, "meta": {"cursor": cursor} if cursor else {}})


def client(session: FakeSession, sleeps: list[float] | None = None) -> Any:
    record = sleeps if sleeps is not None else []
    return purge_mod.LangfuseClient(BASE, "pk-lf-x", "sk-lf-y", session, sleep=record.append)


def test_dry_run_lists_old_root_observations_and_prints_counts_only() -> None:
    session = FakeSession([page(["t1", "t2"], cursor="c2"), page(["t2", "t3"])])
    out = io.StringIO()
    assert purge_mod.purge(client(session), 28, apply=False, now=NOW, out=out) == 0
    assert [c["method"] for c in session.calls] == ["GET", "GET"]
    first, second = (c["params"] for c in session.calls)
    assert session.calls[0]["url"] == f"{BASE}/api/public/v2/observations"
    assert first["isRootObservation"] == "true"
    assert first["toStartTime"] == "2026-09-13T12:00:00.000Z"
    assert first["fromStartTime"] == "2026-09-11T13:00:00.000Z"
    assert first["fields"] == "core" and first["limit"] == "1000"
    assert "cursor" not in first and second["cursor"] == "c2"
    assert session.calls[0]["auth"] == ("pk-lf-x", "sk-lf-y")
    text = out.getvalue()
    assert "traces à supprimer : 3" in text
    assert "t1" not in text and SECRET_TEXT not in text


def test_apply_deletes_in_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(purge_mod, "DELETE_BATCH", 2)
    ok = FakeResponse(200, {"message": "ok"})
    session = FakeSession([page(["t1", "t2", "t3"]), ok, ok])
    out = io.StringIO()
    assert purge_mod.purge(client(session), 28, apply=True, now=NOW, out=out) == 0
    deletes = [c for c in session.calls if c["method"] == "DELETE"]
    assert [c["url"] for c in deletes] == [f"{BASE}/api/public/traces"] * 2
    assert [c["json"] for c in deletes] == [{"traceIds": ["t1", "t2"]}, {"traceIds": ["t3"]}]
    assert "suppression demandée : 3 traces" in out.getvalue()


def test_nothing_to_delete_sends_no_delete() -> None:
    session = FakeSession([page([])])
    assert purge_mod.purge(client(session), 28, apply=True, now=NOW, out=io.StringIO()) == 0
    assert [c["method"] for c in session.calls] == ["GET"]


def test_daily_delete_cap_leaves_a_remainder_and_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(purge_mod, "DELETE_BATCH", 1)
    monkeypatch.setattr(purge_mod, "MAX_DELETE_REQUESTS", 2)
    ok = FakeResponse(200, {"message": "ok"})
    session = FakeSession([page(["t1", "t2", "t3"]), ok, ok])
    out = io.StringIO()
    assert purge_mod.purge(client(session), 28, apply=True, now=NOW, out=out) == 2
    assert "reliquat : 1 traces" in out.getvalue()


def test_429_waits_retry_after_then_succeeds() -> None:
    sleeps: list[float] = []
    session = FakeSession([FakeResponse(429, headers={"Retry-After": "7"}), page(["t1"])])
    assert purge_mod.old_trace_ids(client(session, sleeps), NOW, NOW) == (["t1"], 0)
    assert sleeps == [7.0]


def test_5xx_and_network_errors_back_off_then_fail() -> None:
    sleeps: list[float] = []
    errors: list[Any] = [FakeResponse(503), requests.ConnectionError("boom")] * 3
    session = FakeSession(errors[: purge_mod.MAX_ATTEMPTS])
    with pytest.raises(purge_mod.PurgeError, match="après 5 essais"):
        purge_mod.old_trace_ids(client(session, sleeps), NOW, NOW)
    assert sleeps == [2.0, 4.0, 8.0, 16.0]


def test_client_errors_fail_immediately_without_body() -> None:
    session = FakeSession([FakeResponse(401, {"message": SECRET_TEXT})])
    with pytest.raises(purge_mod.PurgeError) as excinfo:
        purge_mod.old_trace_ids(client(session), NOW, NOW)
    assert "HTTP 401" in str(excinfo.value)
    assert SECRET_TEXT not in str(excinfo.value)
    assert len(session.calls) == 1


def test_base_url_must_be_https() -> None:
    with pytest.raises(purge_mod.PurgeError):
        purge_mod.LangfuseClient("http://us.cloud.langfuse.com", "pk", "sk", FakeSession([]))


def test_main_requires_keys_and_bounds_days(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert purge_mod.main([], session=FakeSession([])) == 1
    with pytest.raises(SystemExit):
        purge_mod.main(["--days", "30"])
    capsys.readouterr()


def test_main_dry_run_by_default_and_failure_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-y")
    monkeypatch.setenv("LANGFUSE_BASE_URL", BASE)
    session = FakeSession([page(["t1"])])
    assert purge_mod.main([], session=session) == 0
    assert [c["method"] for c in session.calls] == ["GET"]
    assert purge_mod.main(["--apply"], session=FakeSession([FakeResponse(403)])) == 1


@pytest.mark.parametrize("started", ["2026-10-01T00:00:00Z", None, "pas une date"])
def test_newer_or_undated_traces_are_never_deleted_and_fail(started: str | None) -> None:
    ok = FakeResponse(200, {"message": "ok"})
    session = FakeSession([page(["old1"], cursor="c"), page(["new1"], started=started), ok])
    out = io.StringIO()
    assert purge_mod.purge(client(session), 28, apply=True, now=NOW, out=out) == 3
    deletes = [c["json"] for c in session.calls if c["method"] == "DELETE"]
    assert deletes == [{"traceIds": ["old1"]}]
    assert "1 traces récentes ou sans date" in out.getvalue()


def test_a_trace_with_any_newer_root_observation_is_skipped() -> None:
    session = FakeSession(
        [page(["t1"], cursor="c"), page(["t1"], started="2026-10-10T00:00:00+00:00")]
    )
    ids, skipped = purge_mod.old_trace_ids(
        client(session), datetime(2026, 9, 13, 12, tzinfo=UTC), NOW
    )
    assert (ids, skipped) == ([], 1)


def test_dry_run_with_newer_traces_fails() -> None:
    session = FakeSession([page(["new1"], started="2026-10-10T00:00:00Z")])
    assert purge_mod.purge(client(session), 28, apply=False, now=NOW, out=io.StringIO()) == 3


class NotJson(FakeResponse):
    def json(self) -> Any:
        raise ValueError("pas du JSON")


def test_2xx_non_json_is_a_clean_failure(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-y")
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    assert purge_mod.main([], session=FakeSession([NotJson(200, {})])) == 1
    assert "ÉCHEC" in capsys.readouterr().err


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example.com",
        "https://langfuse.com.evil.example",
        "https://evillangfuse.com",
        "http://us.cloud.langfuse.com",
    ],
)
def test_base_url_host_must_be_langfuse(url: str) -> None:
    with pytest.raises(purge_mod.PurgeError):
        purge_mod.LangfuseClient(url, "pk", "sk", FakeSession([]))


def test_langfuse_hosts_are_accepted() -> None:
    for url in ("https://us.cloud.langfuse.com", "https://cloud.langfuse.com/"):
        base = purge_mod.LangfuseClient(url, "pk", "sk", FakeSession([])).base_url
        assert base.startswith("https://") and not base.endswith("/")
