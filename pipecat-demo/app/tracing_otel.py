"""Path one: plain OpenTelemetry, two OTLP exporters.

Pipecat's tracing *is* OpenTelemetry. ``setup_tracing()`` builds a
``TracerProvider``, registers it as the global one and wraps the single
exporter it is given in a ``BatchSpanProcessor``; every span Pipecat
records — ``conversation``, ``turn``, ``stt``, ``llm``, ``tts`` — is
written through ``trace.get_tracer("pipecat")`` against that provider.

Dual-writing is therefore a second span processor on the same provider.
Oodle's exporter is the one handed to ``setup_tracing()``, so Pipecat
owns the resource and the service name; Langfuse's is added to the
provider afterwards. Both receive every span, in the same shape, with no
collector in between.

    conversation ─┬─► Oodle      https://<instance>-otlp.collector.oodle.ai/v1/traces
    └── turn      │
        ├── stt   │
        ├── llm   └─► Langfuse   <LANGFUSE_BASE_URL>/api/public/otel/v1/traces
        └── tts

Nothing here is Langfuse-specific: Langfuse's OTLP endpoint is addressed
exactly like any other OTLP backend, which is the point of this path.
Path two, ``tracing_langfuse.py``, goes through the Langfuse SDK instead.
"""

import atexit
import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pipecat.utils.tracing.setup import setup_tracing

from destinations import langfuse_otlp_endpoint, oodle_otlp_endpoint

logger = logging.getLogger(__name__)

BACKEND = "otel"

_initialized = False


def _exporter(endpoint: str, headers: dict[str, str]) -> OTLPSpanExporter:
    return OTLPSpanExporter(
        endpoint=endpoint,
        headers=headers,
        # Langfuse's OTLP endpoint decodes gzip only, and Oodle's accepts it.
        compression=Compression.Gzip,
        timeout=10,
    )


def init(service_name: str, console_export: bool = False) -> None:
    """Register a tracer provider that writes to Langfuse and to Oodle."""
    global _initialized
    if _initialized:
        # A second call cannot replace the global provider, so it would only
        # bolt a duplicate second leg onto the existing one and export
        # everything twice.
        logger.warning("Tracing is already set up; ignoring this call")
        return

    oodle_endpoint, oodle_headers = oodle_otlp_endpoint()
    langfuse_endpoint, langfuse_headers = langfuse_otlp_endpoint()

    # Pipecat's own entry point. It sets service.name, service.instance.id
    # and deployment.environment on the resource, and installs the Oodle
    # exporter behind a batch processor.
    if not setup_tracing(
        service_name=service_name,
        exporter=_exporter(oodle_endpoint, oodle_headers),
        console_export=console_export,
    ):
        raise SystemExit(
            "OpenTelemetry is not installed; install pipecat-ai[tracing] to trace"
        )

    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        # OpenTelemetry allows one provider per process, so the one
        # setup_tracing just built — Oodle's leg included — is unreachable.
        raise SystemExit(
            "Another library registered the tracer provider first; call init() "
            "before anything else sets one up"
        )

    # Leg two. The provider is already global, so this reaches every span
    # Pipecat records from here on.
    provider.add_span_processor(
        BatchSpanProcessor(_exporter(langfuse_endpoint, langfuse_headers))
    )

    _initialized = True

    # The runner keeps the process alive across sessions, so the provider is
    # closed at exit rather than when a session ends.
    atexit.register(shutdown)

    logger.info(
        "Tracing %s to Oodle (%s) and Langfuse (%s) over OTLP",
        service_name,
        oodle_endpoint,
        langfuse_endpoint,
    )


def _provider() -> TracerProvider | None:
    provider = trace.get_tracer_provider()
    return provider if isinstance(provider, TracerProvider) else None


def flush() -> None:
    """Deliver everything recorded so far to both destinations."""
    provider = _provider()
    if provider is not None:
        # Force-flushing the provider reaches every processor on it, so one
        # call covers both legs.
        provider.force_flush()


def shutdown() -> None:
    """Flush and close both legs. Also runs at exit."""
    global _initialized
    if not _initialized:
        return
    _initialized = False

    provider = _provider()
    if provider is not None:
        # Shutting down the provider flushes and closes every processor on
        # it, so one call covers both legs.
        provider.shutdown()
