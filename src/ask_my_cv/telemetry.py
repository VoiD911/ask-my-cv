from __future__ import annotations

import base64
import os
from collections.abc import Callable

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter

from ask_my_cv.settings import ConfigError, Settings

# délai par envoi : 10 s par défaut, et force_flush ignore son propre délai (SDK 1.45)
EXPORT_TIMEOUT_S = 2.0


def exporter_for(name: str, settings: Settings) -> SpanExporter:
    if name == "console":
        return ConsoleSpanExporter()
    if name == "cloudwatch":
        from ask_my_cv.aws.sigv4 import SigV4Session

        return OTLPSpanExporter(
            endpoint=f"https://xray.{settings.aws_region}.amazonaws.com/v1/traces",
            session=SigV4Session(settings.aws_region, "xray"),
            timeout=EXPORT_TIMEOUT_S,
        )
    if name == "langfuse":
        public, secret = (
            os.environ.get("LANGFUSE_PUBLIC_KEY"),
            os.environ.get("LANGFUSE_SECRET_KEY"),
        )
        if not public or not secret:
            raise ConfigError(
                "tracing langfuse : LANGFUSE_PUBLIC_KEY et LANGFUSE_SECRET_KEY sont requis"
            )
        token = base64.b64encode(f"{public}:{secret}".encode()).decode()
        return OTLPSpanExporter(
            endpoint=settings.langfuse_endpoint,
            headers={"Authorization": f"Basic {token}", "x-langfuse-ingestion-version": "4"},
            timeout=EXPORT_TIMEOUT_S,
        )
    raise ConfigError(f"exportateur de traces inconnu : {name}")


def build_tracer_provider(settings: Settings) -> TracerProvider | None:
    if not settings.tracing:
        return None
    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": "ask-my-cv", "deployment.environment": settings.environment}
        )
    )
    for name in settings.tracing:
        provider.add_span_processor(BatchSpanProcessor(exporter_for(name, settings)))
    return provider


def configure_tracing(settings: Settings) -> Callable[[], None]:
    """Installer le fournisseur de traces global ; renvoie la fonction de vidage à appeler."""
    provider = build_tracer_provider(settings)
    if provider is None:
        return lambda: None
    trace.set_tracer_provider(provider)

    def flush() -> None:
        provider.force_flush(timeout_millis=2000)

    return flush
