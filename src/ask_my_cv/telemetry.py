from __future__ import annotations

import base64
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import Link, Status
from opentelemetry.util.types import Attributes

from ask_my_cv.settings import ConfigError, Settings

# délai par envoi : 10 s par défaut, et force_flush ignore son propre délai (SDK 1.45)
EXPORT_TIMEOUT_S = 2.0

# Attributs porteurs de texte (question et réponse masquées, #154) : réservés à Langfuse.
# Tout autre exportateur (CloudWatch/X-Ray, console) les reçoit retirés (`TextFreeExporter`),
# par préfixe : conventions Langfuse, GenAI et OpenInference, présentes ou futures.
TEXT_PREFIXES = ("langfuse.", "gen_ai.", "input.", "output.")
# texte libre des exceptions (message, pile) : retiré des événements hors Langfuse
EXCEPTION_TEXT = frozenset({"exception.message", "exception.stacktrace"})
# seul exportateur autorisé à recevoir le texte masqué
TEXT_EXPORTERS = frozenset({"langfuse"})


@dataclass(frozen=True)
class ExporterConfig:
    endpoint: str
    # repr=False : le jeton Basic (Langfuse) ne doit jamais apparaître dans un repr/log
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    timeout_s: float = EXPORT_TIMEOUT_S
    sigv4: bool = False  # True : session signée SigV4 (service xray)


def exporter_config(name: str, settings: Settings) -> ExporterConfig:
    """Calcule la configuration d'un exportateur, sans toucher au réseau ni au SDK OTel."""
    if name == "cloudwatch":
        import botocore.session

        if botocore.session.Session().get_credentials() is None:
            raise ConfigError("tracing cloudwatch : aucun identifiant AWS")

        return ExporterConfig(
            endpoint=f"https://xray.{settings.aws_region}.amazonaws.com/v1/traces",
            timeout_s=EXPORT_TIMEOUT_S,
            sigv4=True,
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
        return ExporterConfig(
            endpoint=settings.langfuse_endpoint,
            headers={"Authorization": f"Basic {token}", "x-langfuse-ingestion-version": "4"},
            timeout_s=EXPORT_TIMEOUT_S,
        )
    raise ConfigError(f"exportateur de traces inconnu : {name}")


def is_text_attribute(key: str) -> bool:
    return key.startswith(TEXT_PREFIXES)


def _clean(attributes: Attributes, extra: frozenset[str] = frozenset()) -> dict[str, Any]:
    return {
        k: v for k, v in (attributes or {}).items() if not is_text_attribute(k) and k not in extra
    }


def _without_text(span: ReadableSpan) -> ReadableSpan:
    """Copie sans texte : attributs du span, des événements et des liens filtrés, messages
    et piles d'exception retirés, description du statut vidée (code conservé)."""
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=_clean(span.attributes),
        events=[
            Event(e.name, _clean(e.attributes, EXCEPTION_TEXT), e.timestamp) for e in span.events
        ],
        links=[Link(link.context, _clean(link.attributes)) for link in span.links],
        kind=span.kind,
        status=Status(span.status.status_code),
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class TextFreeExporter(SpanExporter):
    """Enveloppe qui exporte chaque span sans texte (`_without_text`, #154).

    Les compteurs d'éléments abandonnés (limites du SDK) repartent de zéro sur la copie."""

    def __init__(self, inner: SpanExporter) -> None:
        self.inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self.inner.export([_without_text(span) for span in spans])

    def shutdown(self) -> None:
        self.inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.inner.force_flush(timeout_millis)


def exporter_for(name: str, settings: Settings) -> SpanExporter:
    """Exportateur nommé ; hors Langfuse, toujours enveloppé sans texte (#154)."""
    exporter = _raw_exporter(name, settings)
    return exporter if name in TEXT_EXPORTERS else TextFreeExporter(exporter)


def _raw_exporter(name: str, settings: Settings) -> SpanExporter:
    if name == "console":
        return ConsoleSpanExporter()
    config = exporter_config(name, settings)
    session = None
    if config.sigv4:
        from ask_my_cv.aws.sigv4 import SigV4Session

        session = SigV4Session(settings.aws_region, "xray")
    return OTLPSpanExporter(
        endpoint=config.endpoint,
        headers=config.headers or None,
        session=session,
        timeout=config.timeout_s,
    )


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
