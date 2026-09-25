import base64

import pytest
import requests
from botocore.credentials import Credentials
from opentelemetry.exporter.http.transport._requests import RequestsHTTPTransport
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from requests.adapters import BaseAdapter

from ask_my_cv.aws.sigv4 import SigV4Session
from ask_my_cv.settings import ConfigError, ModelConfig, Settings
from ask_my_cv.telemetry import build_tracer_provider, exporter_for


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


def test_langfuse_exporter_uses_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-1")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-2")
    exporter = exporter_for("langfuse", settings(tracing=["langfuse"]))
    assert isinstance(exporter, OTLPSpanExporter)
    expected = base64.b64encode(b"pk-lf-1:sk-lf-2").decode()
    # opentelemetry-exporter-otlp-proto-http 1.45.0 : les en-têtes vivent dans
    # `exporter._client._headers` (clés normalisées en minuscules), pas `exporter._headers`.
    assert exporter._client._headers["authorization"] == f"Basic {expected}"
    assert exporter._endpoint.endswith("/api/public/otel/v1/traces")


def test_langfuse_without_keys_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    with pytest.raises(ConfigError):
        exporter_for("langfuse", settings(tracing=["langfuse"]))


def test_cloudwatch_exporter_targets_the_regional_xray_endpoint() -> None:
    exporter = exporter_for("cloudwatch", settings(tracing=["cloudwatch"]))
    assert isinstance(exporter, OTLPSpanExporter)
    assert exporter._endpoint == "https://xray.ca-central-1.amazonaws.com/v1/traces"
    # même version : la session vit dans `exporter._client._transport._session`.
    transport = exporter._client._transport
    assert isinstance(transport, RequestsHTTPTransport)
    assert isinstance(transport._session, SigV4Session)


def test_exporters_have_a_short_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    for name in ("cloudwatch", "langfuse"):
        exporter = exporter_for(name, settings(tracing=[name]))
        assert isinstance(exporter, OTLPSpanExporter)
        assert exporter._client._timeout <= 2.0


def test_cloudwatch_without_aws_credentials_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    import botocore.session

    monkeypatch.setattr(botocore.session.Session, "get_credentials", lambda self: None)
    with pytest.raises(ConfigError):
        exporter_for("cloudwatch", settings(tracing=["cloudwatch"]))
