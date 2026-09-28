"""Laminar + Oodle dual write, set up the way production agent platforms run it.

Laminar is the primary SDK. It owns its own TracerProvider, records the agent
spans (session, turn loop, tool calls, subagents) and the manual LLM spans
that carry token usage. Its LiteLLM auto-instrumentation is disabled because
its streaming handler drops usage.

Oodle gets two span sources, both exported straight to the Oodle collector:

1. A LiteLLM ``OpenTelemetry`` callback on a private TracerProvider, which
   emits one ``chat <model>`` GenAI span per completion. Laminar attaches its
   spans to the global OpenTelemetry context, so each of these is created as a
   child of the Laminar ``llm_call_stream`` span around it.
2. A mirror of every Laminar span. Without it the parents of the LiteLLM
   spans never reach Oodle, and a session arrives as a flat list of orphaned
   model calls. Set ``OODLE_MIRROR_LAMINAR_SPANS=false`` to see that.
"""

import os
from collections.abc import Mapping
from typing import Any

import litellm
from litellm.integrations.opentelemetry import OpenTelemetry, OpenTelemetryConfig
from litellm.integrations.opentelemetry_utils.gen_ai_semconv import OTELSemconvCategory
from lmnr import Laminar
from lmnr.opentelemetry_lib.tracing import TracerWrapper
from lmnr.opentelemetry_lib.tracing.instruments import Instruments
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Prompt, completion and tool-schema attributes. Dropped from mirrored spans
# when content capture is off, so one flag governs what leaves the process.
_CONTENT_KEYS = frozenset(
    {"lmnr.span.input", "lmnr.span.output", "gen_ai.input.messages", "gen_ai.output.messages"}
)


class _OodleLiteLLMCallback(OpenTelemetry):
    """LiteLLM's OTel callback, kept off LiteLLM's proxy globals."""

    def _init_otel_logger_on_litellm_proxy(self) -> None:
        return

    def set_attributes(self, span, kwargs, response_obj) -> None:
        super().set_attributes(span, kwargs, response_obj)
        # LiteLLM 1.102 writes gen_ai.operation.name only when it captures
        # content, and Oodle's Agent Observability lists spans by it.
        if "gen_ai.operation.name" not in (getattr(span, "attributes", None) or {}):
            span.set_attribute("gen_ai.operation.name", self._gen_ai_operation_name(kwargs))


class _LaminarMirror(SpanProcessor):
    """Re-export finished Laminar spans to Oodle under the app's resource.

    Laminar names its resource after ``sys.argv[0]``, so each span is rebuilt
    with the Oodle resource before it reaches the batch exporter.
    """

    def __init__(self, delegate: BatchSpanProcessor, resource: Resource, capture_content: bool) -> None:
        self._delegate = delegate
        self._resource = resource
        self._capture_content = capture_content

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        return

    def on_end(self, span: ReadableSpan) -> None:
        attributes: Mapping[str, Any] | None = span.attributes
        if attributes and not self._capture_content:
            attributes = {k: v for k, v in attributes.items() if k not in _CONTENT_KEYS}
        self._delegate.on_end(
            ReadableSpan(
                name=span.name,
                context=span.context,
                parent=span.parent,
                resource=self._resource,
                attributes=attributes,
                events=span.events,
                links=span.links,
                kind=span.kind,
                instrumentation_scope=span.instrumentation_scope,
                status=span.status,
                start_time=span.start_time,
                end_time=span.end_time,
            )
        )

    def shutdown(self) -> None:
        self._delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._delegate.force_flush(timeout_millis)


_oodle_provider: TracerProvider | None = None
_mirror: _LaminarMirror | None = None


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() == "true"


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


def init_oodle(service_name: str) -> None:
    """Register the LiteLLM callback and, unless disabled, the Laminar mirror."""
    global _oodle_provider, _mirror
    capture = _flag("OODLE_CAPTURE_MESSAGE_CONTENT", "true")
    resource = Resource.create(
        {"service.name": service_name, "deployment.environment": os.environ.get("ENV", "demo")}
    )
    _oodle_provider = TracerProvider(resource=resource)
    _oodle_provider.add_span_processor(BatchSpanProcessor(_oodle_exporter(), max_export_batch_size=16))
    litellm.callbacks.append(
        _OodleLiteLLMCallback(
            config=OpenTelemetryConfig(
                skip_set_global=True,
                service_name=service_name,
                capture_message_content="SPAN_ONLY" if capture else "NO_CONTENT",
                semconv_stability_opt_in={OTELSemconvCategory.GEN_AI_LATEST_EXPERIMENTAL},
                ignore_context_propagation=True,
                enable_metrics=False,
                enable_events=False,
            ),
            tracer_provider=_oodle_provider,
        )
    )
    if not _flag("OODLE_MIRROR_LAMINAR_SPANS", "true"):
        return
    # lmnr has no public accessor for its provider, so read the singleton.
    laminar_provider = TracerWrapper.instance._tracer_provider
    _mirror = _LaminarMirror(
        BatchSpanProcessor(_oodle_exporter(), max_queue_size=2048, max_export_batch_size=16),
        resource,
        capture,
    )
    laminar_provider.add_span_processor(_mirror)


def flush() -> None:
    Laminar.flush()
    if _mirror is not None:
        _mirror.force_flush()
    if _oodle_provider is not None:
        _oodle_provider.force_flush()
