"""ADOT auto-instrumentation with Oodle OTLP export.

Follows the AgentCore observability guide: ADOT instruments botocore,
a BaggageSpanProcessor copies session.id onto every span, and traced()
propagates the runtime's trace context for hand-written servers.

The guide's Dockerfile uses ``opentelemetry-instrument`` to bootstrap ADOT.
This demo uses direct-code deployment, so the same instrumentors are
installed programmatically below; a Docker deployment would replace the
CMD with ``["opentelemetry-instrument", "python", "main.py"]`` and set
the OTEL_* env vars listed in deploy.py.
"""

import os
from contextlib import contextmanager

from opentelemetry import baggage, context, trace
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


class BaggageSpanProcessor(SpanProcessor):
    """Copy session.id from OTel baggage onto every span.

    Plain OpenTelemetry leaves baggage off spans.  This processor propagates
    the session identifier set in the entrypoint so every span in the trace
    carries it and queries can filter by session.
    """

    def on_start(self, span, parent_context=None):
        session = baggage.get_baggage("session.id", parent_context)
        if session:
            span.set_attribute("session.id", session)


@contextmanager
def traced(headers, session):
    """Propagate the runtime's trace context and set session.id as baggage.

    BedrockAgentCoreApp runs on Starlette, which ADOT instruments, so trace
    context flows without this helper.  Use traced() when running a
    hand-written HTTP server or when the runtime headers are not propagated
    automatically.
    """
    ctx = extract(dict(headers) if headers else {})
    if session and baggage.get_baggage("session.id", ctx) != session:
        ctx = baggage.set_baggage("session.id", session, ctx)
    token = context.attach(ctx)
    try:
        yield
    finally:
        context.detach(token)


def setup_telemetry(service_name: str) -> TracerProvider:
    """Install ADOT instrumentors, configure Oodle export, add BaggageSpanProcessor."""
    instance = os.environ.get("OODLE_INSTANCE", "").strip()
    api_key = os.environ.get("OODLE_API_KEY", "").strip()
    if not instance or not api_key or instance == "your-instance-id" or api_key == "your-api-key":
        raise ValueError("Set OODLE_INSTANCE and OODLE_API_KEY in .env before running the demo")
    endpoint = os.environ.get("OODLE_OTLP_ENDPOINT") or f"https://{instance}-otlp.collector.oodle.ai"

    # Strands content capture via semconv opt-in, set before creating the Agent.
    conventions = "gen_ai_latest_experimental,gen_ai_span_attributes_only"
    if os.environ.get("CAPTURE_CONTENT", "true").lower() != "true":
        conventions += ",gen_ai_unredacted_attributes="
    os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = conventions

    provider = TracerProvider(resource=Resource.create({
        "service.name": service_name,
        "service.namespace": "oodle-amazon-demos",
        "cloud.provider": "aws",
        "cloud.region": os.environ.get("AWS_REGION", "us-west-2"),
    }))
    provider.add_span_processor(BaggageSpanProcessor())
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
        endpoint=f"{endpoint.rstrip('/')}/v1/traces",
        headers={"X-OODLE-INSTANCE": instance, "X-API-KEY": api_key},
        compression=Compression.Gzip,
        timeout=10,
    )))
    trace.set_tracer_provider(provider)

    # ADOT botocore instrumentor: adds spans for every AWS SDK call (DynamoDB,
    # SSM, Bedrock).  The guide's Dockerfile uses opentelemetry-instrument
    # which installs these at startup; here they are installed programmatically
    # for direct-code deployment.
    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
    BotocoreInstrumentor().instrument()

    return provider
