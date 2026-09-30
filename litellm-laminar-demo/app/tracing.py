"""Laminar + Oodle dual write, set up the way production agent platforms run it.

Laminar is the primary SDK. It owns its own TracerProvider, records the agent
spans (session, turn loop, tool calls, subagents) and the manual LLM spans
that carry token usage. Its LiteLLM auto-instrumentation is disabled because
its streaming handler drops usage.

Oodle gets a mirror of every Laminar span, exported straight to the Oodle
collector, so both backends hold the same trace. There is no LiteLLM
OpenTelemetry callback: it would add a ``chat <model>`` child under every
Laminar LLM span that repeats its model, tokens and prompt. Oodle reads the
model call from the Laminar span itself and prices it from the token counts.

Message content (prompts, completions, tool schemas, tool and turn payloads)
stays out of Oodle unless ``OODLE_CAPTURE_MESSAGE_CONTENT=true``. Laminar
receives it either way. Telemetry failures never reach the app: every hook
that runs inside span handling logs and moves on.
"""

import logging
import os
import threading
from collections.abc import Sequence
from typing import Any

from lmnr import Laminar
from lmnr.opentelemetry_lib.tracing.instruments import Instruments
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.util.types import Attributes

logger = logging.getLogger(__name__)

# Content on mirrored spans is dropped when content capture is off. Laminar and
# its bundled instrumentors (OpenAI, Anthropic, Google GenAI, ...) write content
# under three key shapes, all matched here:
#   - whole-payload keys, e.g. ``lmnr.span.input`` or ``gen_ai.input.messages``
#   - indexed semconv keys, e.g. ``gen_ai.prompt.0.content``,
#     ``gen_ai.completion.0.tool_calls.1.arguments``, ``llm.request.functions.0.parameters``
#   - any key whose leaf is a content field, e.g. ``*.content`` or ``*.arguments``
_CONTENT_KEYS = frozenset(
    {
        "lmnr.span.input",
        "lmnr.span.output",
        "gen_ai.prompt",
        "gen_ai.completion",
        "gen_ai.input.messages",
        "gen_ai.output.messages",
        "gen_ai.system_instructions",
        "gen_ai.request.instructions",
        "gen_ai.request.structured_output_schema",
        "gen_ai.tool.definitions",
        "gen_ai.tool.call.arguments",
        "gen_ai.tool.call.result",
    }
)
_CONTENT_PREFIXES = ("gen_ai.prompt.", "gen_ai.completion.", "llm.request.functions.")
_CONTENT_SUFFIXES = (".content", ".reasoning", ".arguments")

# GenAI semconv events whose attributes are message content. Marker events
# (``llm.content.completion.chunk``) and errors (``exception``) carry no content
# once their attributes are filtered, so they are kept.
_CONTENT_EVENT_PREFIXES = ("gen_ai.content.", "gen_ai.client.inference.")
_CONTENT_EVENT_SUFFIXES = (".message", ".choice")


def _is_content_key(key: str) -> bool:
    return key in _CONTENT_KEYS or key.startswith(_CONTENT_PREFIXES) or key.endswith(_CONTENT_SUFFIXES)


def _without_content(attributes: Attributes) -> Attributes:
    if not attributes:
        return attributes
    return {key: value for key, value in attributes.items() if not _is_content_key(key)}


def _events_without_content(events: Sequence[Event]) -> list[Event]:
    return [
        Event(event.name, _without_content(event.attributes), event.timestamp)
        for event in events
        if not event.name.startswith(_CONTENT_EVENT_PREFIXES)
        and not event.name.endswith(_CONTENT_EVENT_SUFFIXES)
    ]


def _laminar_tracing_disabled(span: ReadableSpan) -> bool:
    """Apply Laminar's own export gate, so the mirror never outlives it.

    Laminar drops a span when ``LMNR_DISABLE_TRACING`` is set, or when it
    stamped ``lmnr.internal.disabled`` on the span at start. The mirror sits on
    the same provider, so it must honor the same switch.
    """
    if os.environ.get("LMNR_DISABLE_TRACING", "false").strip().lower() == "true":
        return True
    return bool((span.attributes or {}).get("lmnr.internal.disabled"))


class _LaminarMirror(SpanProcessor):
    """Re-export finished Laminar spans to Oodle under the app's resource.

    Laminar names its resource after ``sys.argv[0]``, so each span is rebuilt
    with the Oodle resource before it reaches the batch exporter. A processor
    cannot be removed from Laminar's provider, so after shutdown it drops
    spans silently instead of failing on every span Laminar still records.
    """

    def __init__(self, delegate: BatchSpanProcessor, resource: Resource, capture_content: bool) -> None:
        self._delegate = delegate
        self._resource = resource
        self._capture_content = capture_content
        self._closed = False

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        return

    def on_end(self, span: ReadableSpan) -> None:
        if self._closed or _laminar_tracing_disabled(span):
            return
        try:
            self._delegate.on_end(self._rebind(span))
        except Exception:
            logger.debug("Failed to mirror Laminar span to Oodle", exc_info=True)

    def _rebind(self, span: ReadableSpan) -> ReadableSpan:
        attributes: Attributes = span.attributes
        events: Sequence[Event] = span.events
        if not self._capture_content:
            attributes = _without_content(attributes)
            events = _events_without_content(events)
        return ReadableSpan(
            name=span.name,
            context=span.context,
            parent=span.parent,
            resource=self._resource,
            attributes=attributes,
            events=events,
            links=span.links,
            kind=span.kind,
            instrumentation_scope=span.instrumentation_scope,
            status=span.status,
            start_time=span.start_time,
            end_time=span.end_time,
        )

    def shutdown(self) -> None:
        self._closed = True
        self._delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._delegate.force_flush(timeout_millis)


_lock = threading.Lock()
_initialized = False
_mirror: _LaminarMirror | None = None


def init_laminar() -> None:
    Laminar.initialize(
        project_api_key=os.environ["LMNR_PROJECT_API_KEY"],
        disabled_instruments={Instruments.LITELLM},
        max_export_batch_size=16,
        export_timeout_seconds=60,
    )


def _oodle_exporter() -> OTLPSpanExporter:
    instance = os.environ["OODLE_INSTANCE"]
    endpoint = os.environ.get(
        "OODLE_TRACES_ENDPOINT", f"https://{instance}-otlp.collector.oodle.ai/v1/traces"
    )
    return OTLPSpanExporter(
        endpoint=endpoint,
        headers={"X-API-KEY": os.environ["OODLE_API_KEY"], "X-OODLE-INSTANCE": instance},
        compression=Compression.Gzip,
        timeout=10,
    )


def _batch_processor(exporter: OTLPSpanExporter) -> BatchSpanProcessor:
    return BatchSpanProcessor(
        exporter,
        max_export_batch_size=16,
        schedule_delay_millis=5000,
        export_timeout_millis=10000,
    )


def _laminar_tracer_provider() -> Any | None:
    """Laminar's SDK TracerProvider, or None when Laminar is not initialized.

    lmnr has no public accessor for its provider, so this reads the private
    ``_tracer_provider`` slot of its ``TracerWrapper`` singleton, guarded so an
    SDK change degrades to "no mirror" instead of an exception.
    """
    try:
        from lmnr.opentelemetry_lib.tracing import TracerWrapper

        if not TracerWrapper.verify_initialized():
            return None
        provider = getattr(getattr(TracerWrapper, "instance", None), "_tracer_provider", None)
    except Exception:
        return None
    return provider if hasattr(provider, "add_span_processor") else None


def init_oodle(service_name: str) -> bool:
    """Attach the Laminar mirror. False when Laminar is not initialized.

    Safe to call more than once: later calls are no-ops, so spans are never
    exported twice.
    """
    global _initialized, _mirror
    with _lock:
        if _initialized:
            return True
        laminar_provider = _laminar_tracer_provider()
        if laminar_provider is None:
            logger.warning("Laminar is not initialized; Oodle receives no spans")
            return False
        capture = os.environ.get("OODLE_CAPTURE_MESSAGE_CONTENT", "false").lower() == "true"
        resource = Resource.create(
            {"service.name": service_name, "deployment.environment": os.environ.get("ENV", "demo")}
        )
        _mirror = _LaminarMirror(_batch_processor(_oodle_exporter()), resource, capture)
        laminar_provider.add_span_processor(_mirror)
        _initialized = True
        return True


def flush() -> None:
    Laminar.flush()
    if _mirror is not None:
        _mirror.force_flush()


def shutdown_oodle() -> None:
    """Flush and close the Oodle mirror."""
    global _initialized, _mirror
    with _lock:
        mirror, _mirror, _initialized = _mirror, None, False
        if mirror is None:
            return
        try:
            mirror.force_flush(10000)
            mirror.shutdown()
        except Exception:
            logger.warning("Failed to shut down the Oodle mirror", exc_info=True)
