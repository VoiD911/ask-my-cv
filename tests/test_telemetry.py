import base64

import pytest
import requests
from botocore.credentials import Credentials
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from requests.adapters import BaseAdapter

from ask_my_cv.aws.sigv4 import SigV4Session
from ask_my_cv.settings import ConfigError, ModelConfig, Settings
from ask_my_cv.telemetry import (
    ExporterConfig,
    TextFreeExporter,
    build_tracer_provider,
    exporter_config,
    exporter_for,
)


class Capture(BaseAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.request: requests.PreparedRequest | None = None

    def send(self, request, **kwargs):  # type: ignore[override]
        self.request = request
        response = requests.Response()
        response.status_code = 200
        response._content = b""
        return response

    def close(self) -> None:
        pass


def settings(**extra) -> Settings:
    return Settings(
        models=[ModelConfig(id="fake:echo", provider="fake")],
        default_model="fake:echo",
        fallback_chain=["fake:echo"],
        **extra,
    )


def test_sigv4_session_signs_for_xray() -> None:
    session = SigV4Session("ca-central-1", "xray", Credentials("AKIDEXAMPLE", "secret"))
    capture = Capture()
    session.mount("https://", capture)
    session.headers.update({"Content-Type": "application/x-protobuf"})
    session.post("https://xray.ca-central-1.amazonaws.com/v1/traces", data=b"\x0a\x00")
    assert capture.request is not None
    auth = str(capture.request.headers["Authorization"])
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/")
    assert "/ca-central-1/xray/aws4_request" in auth
    assert "X-Amz-Date" in capture.request.headers


def test_no_tracing_means_no_provider() -> None:
    assert build_tracer_provider(settings()) is None


def test_langfuse_exporter_config_uses_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-1")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-2")
    config = exporter_config("langfuse", settings(tracing=["langfuse"]))
    expected = base64.b64encode(b"pk-lf-1:sk-lf-2").decode()
    assert config.headers["Authorization"] == f"Basic {expected}"
    assert config.headers["x-langfuse-ingestion-version"] == "4"
    assert config.endpoint.endswith("/api/public/otel/v1/traces")
    assert config.sigv4 is False
    assert config.timeout_s <= 2.0


def test_langfuse_without_keys_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    with pytest.raises(ConfigError):
        exporter_config("langfuse", settings(tracing=["langfuse"]))


def test_cloudwatch_exporter_config_targets_the_regional_xray_endpoint() -> None:
    config = exporter_config("cloudwatch", settings(tracing=["cloudwatch"]))
    assert config.endpoint == "https://xray.ca-central-1.amazonaws.com/v1/traces"
    assert config.sigv4 is True
    assert config.timeout_s <= 2.0


def test_cloudwatch_without_aws_credentials_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    import botocore.session

    monkeypatch.setattr(botocore.session.Session, "get_credentials", lambda self: None)
    with pytest.raises(ConfigError):
        exporter_config("cloudwatch", settings(tracing=["cloudwatch"]))


def test_exporter_config_repr_hides_the_headers_token() -> None:
    config = ExporterConfig(
        endpoint="https://example.test", headers={"Authorization": "Basic secret-token"}
    )
    assert "secret-token" not in repr(config)
    assert "Authorization" not in repr(config)


def test_unknown_exporter_name_fails_fast() -> None:
    with pytest.raises(ConfigError):
        exporter_config("bogus", settings())


def test_exporter_for_langfuse_builds_a_real_otlp_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    exporter = exporter_for("langfuse", settings(tracing=["langfuse"]))
    assert isinstance(exporter, OTLPSpanExporter)


def test_exporter_for_cloudwatch_builds_a_real_otlp_exporter() -> None:
    exporter = exporter_for("cloudwatch", settings(tracing=["cloudwatch"]))
    assert isinstance(exporter, TextFreeExporter)
    assert isinstance(exporter.inner, OTLPSpanExporter)


SENTINEL = "SENTINELLE-question-a.b@acme.fr"
TEXT_KEYS = (
    "langfuse.observation.input",
    "langfuse.observation.output",
    "langfuse.trace.metadata.note",
    "gen_ai.prompt.0.content",
    "gen_ai.input.messages",
    "input.value",
    "output.value",
)


def test_only_langfuse_receives_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import Link, StatusCode

    import ask_my_cv.telemetry as telemetry

    exporters = {"cloudwatch": InMemorySpanExporter(), "langfuse": InMemorySpanExporter()}
    monkeypatch.setattr(telemetry, "_raw_exporter", lambda name, _settings: exporters[name])
    provider = build_tracer_provider(settings(tracing=["cloudwatch", "langfuse"]))
    assert provider is not None
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("other") as other:
        pass
    link = Link(other.get_span_context(), {"input.value": SENTINEL, "kind": "suite"})
    # span par défaut (record_exception, set_status_on_exception) : le pire cas
    with pytest.raises(RuntimeError):
        with tracer.start_as_current_span("ask", links=[link]) as root:
            root.set_attribute("xops.result", "answered")
            for key in TEXT_KEYS:
                root.set_attribute(key, SENTINEL)
            root.add_event("fin", {"n": 1, "gen_ai.completion": SENTINEL})
            with tracer.start_as_current_span("llm") as child:
                child.set_attribute("tokens_in", 12)
            raise RuntimeError(SENTINEL)
    assert provider.force_flush(timeout_millis=2000)
    by_name = {
        name: {s.name: s for s in exporter.get_finished_spans()}
        for name, exporter in exporters.items()
    }
    cloudwatch, langfuse = by_name["cloudwatch"]["ask"], by_name["langfuse"]["ask"]
    # aucun champ exporté vers CloudWatch ne contient la sentinelle
    for span in by_name["cloudwatch"].values():
        assert SENTINEL not in span.to_json(), span.name
    assert SENTINEL in langfuse.to_json()
    assert dict(cloudwatch.attributes or {}) == {"xops.result": "answered"}
    for field in ("context", "parent", "resource", "kind", "start_time", "end_time"):
        assert getattr(cloudwatch, field) == getattr(langfuse, field), field
    assert cloudwatch.status.status_code is StatusCode.ERROR
    assert cloudwatch.status.description is None
    assert [e.name for e in cloudwatch.events] == ["fin", "exception"]
    assert dict(cloudwatch.events[0].attributes or {}) == {"n": 1}
    assert (cloudwatch.events[1].attributes or {})["exception.type"] == "RuntimeError"
    assert [dict(lk.attributes or {}) for lk in cloudwatch.links] == [{"kind": "suite"}]
    assert cloudwatch.links[0].context == other.get_span_context()
    assert cloudwatch.instrumentation_scope == langfuse.instrumentation_scope
    assert by_name["cloudwatch"]["llm"].parent == cloudwatch.context
    assert dict(by_name["cloudwatch"]["llm"].attributes or {}) == {"tokens_in": 12}
    assert set(TEXT_KEYS) <= set(langfuse.attributes or {})
    assert SENTINEL in (langfuse.status.description or "")
    provider.shutdown()


def test_every_exporter_but_langfuse_is_text_free(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    for name in ("cloudwatch", "console"):
        assert isinstance(exporter_for(name, settings(tracing=[name])), TextFreeExporter)
    assert not isinstance(exporter_for("langfuse", settings()), TextFreeExporter)
