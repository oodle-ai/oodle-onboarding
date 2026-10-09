"""Path two: the Langfuse SDK, with Oodle as a second Langfuse destination.

The same voice pipeline, reported through the Langfuse Python SDK rather
than through bare OTLP exporters. This is the path to take when the app
already uses the Langfuse SDK for anything else — scores, prompt links,
``update_current_trace`` — because those only exist on a Langfuse client,
and Oodle then arrives as a second destination for the client the app
already has rather than as a separate pipeline.

Three things make it different from ``tracing_otel.py``:

- The Langfuse SDK brings its own span processor, which rewrites spans
  into Langfuse observations (trace/generation shapes, app-root marking,
  media handling, masking) before export. Oodle's leg is a second
  instance of that same processor, re-addressed at the Langfuse ingest
  API Oodle serves, so both backends receive identical observations.
- Pipecat still owns the tracer provider. The client is given that
  provider rather than building its own, which is what keeps one set of
  spans flowing to both destinations.
- The SDK's default export filter drops Pipecat's ``turn`` spans, so it
  is widened here. See ``_should_export_span``.

    conversation ─┬─► Langfuse   <LANGFUSE_BASE_URL>/api/public/otel/v1/traces
    └── turn      │
        ├── stt   │
        ├── llm   └─► Oodle      https://<domain>/v1/api/instance/<id>/langfuse/…
        └── tts
"""

import atexit
import logging
import os

from langfuse import Langfuse, get_client

# Neither the span processor nor the default export filter is re-exported
# at the package root, so both come from the modules that define them.
from langfuse._client.span_filter import is_default_export_span
from langfuse._client.span_processor import LangfuseSpanProcessor
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from pipecat.utils.tracing.setup import setup_tracing

from destinations import oodle_langfuse_ingest, required

logger = logging.getLogger(__name__)

BACKEND = "langfuse-sdk"

_initialized = False

# The instrumentation scopes Pipecat records under: "pipecat" for the
# service spans and "pipecat.turn" for the conversation and turn spans.
PIPECAT_SCOPE = "pipecat"


def _scope_name(span: ReadableSpan) -> str:
    return span.instrumentation_scope.name if span.instrumentation_scope else ""


def _should_export_span(span: ReadableSpan) -> bool:
    """Export Pipecat's spans alongside the ones Langfuse exports by default.

    The SDK's default filter keeps a span only if the Langfuse SDK wrote
    it, it carries a ``gen_ai.*`` attribute, or its instrumentation scope
    is one of the LLM instrumentors Langfuse knows. Pipecat is not on that
    list, and its ``turn`` spans carry only ``turn.*`` and
    ``conversation.id`` — so without this the turn spans are dropped and
    the ``stt``/``llm``/``tts`` spans beneath them arrive parented to a
    span that was never sent.

    Set ``LANGFUSE_EXPORT_PIPECAT_SPANS=false`` to see that happen.
    """
    scope = _scope_name(span)
    if scope == PIPECAT_SCOPE or scope.startswith(f"{PIPECAT_SCOPE}."):
        return True

    return is_default_export_span(span)


def _export_filter():
    if os.environ.get("LANGFUSE_EXPORT_PIPECAT_SPANS", "true").strip().lower() == "false":
        logger.warning(
            "LANGFUSE_EXPORT_PIPECAT_SPANS=false: Pipecat's turn spans will be dropped"
        )
        return is_default_export_span

    return _should_export_span


def init(service_name: str, console_export: bool = False) -> None:
    """Register a Langfuse client whose spans reach Langfuse and Oodle."""
    global _initialized
    if _initialized:
        # A second call cannot replace the global provider, so it would only
        # bolt a duplicate second leg onto the existing one and export
        # everything twice.
        logger.warning("Tracing is already set up; ignoring this call")
        return

    langfuse_public_key = required("LANGFUSE_PUBLIC_KEY")
    required("LANGFUSE_SECRET_KEY")
    oodle_base_url, oodle_headers = oodle_langfuse_ingest()

    # Pipecat's entry point, with no exporter: it exists here only to build
    # the provider and put service.name on its resource. Both legs are
    # added below, by the Langfuse SDK.
    if not setup_tracing(
        service_name=service_name, exporter=None, console_export=console_export
    ):
        raise SystemExit(
            "OpenTelemetry is not installed; install pipecat-ai[tracing] to trace"
        )

    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        raise SystemExit(
            "Another library registered the tracer provider first; call init() "
            "before anything else sets one up"
        )

    export_filter = _export_filter()

    # Leg one. The client would pick up the already-registered provider on
    # its own, but only because it is built after setup_tracing(); built
    # first it would register one of its own, setup_tracing() would decline
    # to replace it, and every span would carry a resource with no
    # service.name. Passing it keeps that ordering explicit.
    # LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY keep
    # their usual meaning and are read from the environment.
    Langfuse(tracer_provider=provider, should_export_span=export_filter)

    # Leg two: the same processor, pointed at Oodle.
    provider.add_span_processor(
        LangfuseSpanProcessor(
            # A processor rejects any Langfuse-SDK span whose scope carries
            # a different public key — that is how the SDK keeps two
            # projects in one process from leaking into each other. The
            # spans on this leg are the ones the client above writes, so
            # this is that client's key, not Oodle's. Oodle's credentials
            # travel in the headers instead.
            public_key=langfuse_public_key,
            secret_key="unused",
            base_url=oodle_base_url,
            additional_headers=oodle_headers,
            should_export_span=export_filter,
        )
    )

    _initialized = True

    # The runner keeps the process alive across sessions, so the provider is
    # closed at exit rather than when a session ends.
    atexit.register(shutdown)

    logger.info(
        "Tracing %s to Langfuse and Oodle (%s) through the Langfuse SDK",
        service_name,
        oodle_base_url,
    )


def flush() -> None:
    """Deliver everything recorded so far to both destinations."""
    # The client force-flushes the provider it was given, which reaches the
    # Oodle processor as well, and then drains its own score and media
    # queues.
    get_client().flush()


def shutdown() -> None:
    """Flush and close both legs. Also runs at exit."""
    global _initialized
    if not _initialized:
        return
    _initialized = False

    flush()

    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.shutdown()
