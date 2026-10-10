"""Per-call tracing to Oodle, with or without personal data.

LiveKit Agents records every call as an OpenTelemetry span tree under the
instrumentation scope ``livekit-agents``. Content that may identify a
person — the transcript, the reply, the chat context, a tool's arguments
and result, the room name and the participant identity — is written under
``lk.pii.*``, and the GenAI content attributes (``gen_ai.input.messages``,
``gen_ai.output.messages`` …) carry the same text under names the
conventions fix.

``set_tracer_provider(..., allow_pii=...)`` decides what an exporter that
is not LiveKit Cloud's receives:

- ``allow_pii=True`` (LiveKit's default) — everything. Oodle can render
  the conversation.
- ``allow_pii=False`` — LiveKit strips those attributes, and the GenAI
  message events, in-process before any exporter runs. Oodle receives the
  timings, models, token counts, tool names and agent labels, and no text.

A provider is built for each call, as LiveKit's own Langfuse example does,
because the ``metadata`` stamped on every span is per call. Each call runs
in its own job process, so ``allow_pii`` is per call as well.
"""

import logging
import os

from livekit.agents.telemetry import set_tracer_provider
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.util.types import AttributeValue

logger = logging.getLogger(__name__)

PII_ALLOW = "allow"
PII_WITHHOLD = "withhold"
PII_MODES = (PII_ALLOW, PII_WITHHOLD)


def pii_mode(requested: str | None) -> str:
    """The call's PII mode, falling back to ``DEFAULT_PII_MODE``.

    The browser asks for a mode when it starts a call. A client that does
    not — LiveKit's own playground, say — gets the default, which is
    LiveKit's own: allow.
    """
    mode = (requested or os.environ.get("DEFAULT_PII_MODE", PII_ALLOW)).strip().lower()
    if mode not in PII_MODES:
        raise ValueError(f"pii_mode {mode!r} is not one of {', '.join(PII_MODES)}")

    return mode


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required to send traces to Oodle")

    return value


def oodle_otlp_endpoint() -> tuple[str, dict[str, str]]:
    """Oodle's OTLP/HTTP traces endpoint and the headers it authenticates by."""
    instance = _required("OODLE_INSTANCE")
    endpoint = os.environ.get(
        "OODLE_TRACES_ENDPOINT", f"https://{instance}-otlp.collector.oodle.ai/v1/traces"
    )

    return endpoint, {"X-API-KEY": _required("OODLE_API_KEY"), "X-OODLE-INSTANCE": instance}


def _resource(service_name: str) -> Resource:
    environment = os.environ.get("ENVIRONMENT", "demo")
    # Resource.create also merges OTEL_RESOURCE_ATTRIBUTES.
    return Resource.create(
        {
            "service.name": service_name,
            "service.version": os.environ.get("SERVICE_VERSION", "0.1.0"),
            "deployment.environment": environment,
            "env": environment,
        }
    )


def init(
    service_name: str,
    *,
    metadata: dict[str, AttributeValue],
    allow_pii: bool,
) -> TracerProvider:
    """Point LiveKit's spans for this call at Oodle.

    ``metadata`` is stamped on every span the call records. LiveKit does
    not filter it: it is the application's own attribution, so it holds
    pseudonymous ids only and is the same in both modes.
    """
    endpoint, headers = oodle_otlp_endpoint()

    provider = TracerProvider(resource=_resource(service_name))
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=endpoint,
                headers=headers,
                compression=Compression.Gzip,
                timeout=10,
            )
        )
    )
    if os.environ.get("OTEL_CONSOLE_EXPORT", "").strip().lower() in ("1", "true"):
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    # LiveKit puts its PII filter ahead of every processor already on the
    # provider, so the exporter above only ever sees the filtered span.
    set_tracer_provider(provider, metadata=metadata, allow_pii=allow_pii)

    logger.info(
        "Tracing %s to Oodle (%s), personal data %s",
        service_name,
        endpoint,
        "included" if allow_pii else "withheld",
    )

    return provider
