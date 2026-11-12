"""ADOT auto-instrumentation with Oodle OTLP export.

Follows the AgentCore observability guide (levantar-ai/demos/agentcore/
07-observability). The guide's agent is a hand-written ThreadingHTTPServer
started under ADOT via ``opentelemetry-instrument python main.py`` in the
Dockerfile. ADOT handles TracerProvider creation, botocore instrumentation,
and copies baggage onto spans (the BaggageSpanProcessor) before user code
runs. The ``traced()`` context manager in the guide's main.py extracts the
runtime's trace context from request headers and sets session.id as baggage
so ADOT's processor copies it onto every child span.

This demo uses direct-code deployment with BedrockAgentCoreApp (no
Dockerfile), so the same instrumentors are installed programmatically below.
A Docker deployment would replace the CMD with the guide's wrapper and set
the OTEL_* env vars listed in deploy.py.
"""

import os
from contextlib import contextmanager

from opentelemetry import baggage, context, propagate, trace
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


class BaggageSpanProcessor(SpanProcessor):
    """Copy session.id from OTel baggage onto every span.

    In the guide's Docker path, ADOT provides this natively. This demo
    installs it explicitly for the programmatic setup path.
    """

    def on_start(self, span, parent_context=None):
        session = baggage.get_baggage("session.id", parent_context)
        if session:
            span.set_attribute("session.id", session)


@contextmanager
def traced(headers, session):
    """Run the block inside the trace the runtime started for this request.

    The runtime sends its trace context on the request's headers. This
    extracts it and sets the session id as baggage so the
    BaggageSpanProcessor copies it onto every span started inside the block.

    BedrockAgentCoreApp runs on Starlette, which ADOT instruments, so trace
    context flows without this helper. The guide's hand-written HTTP server
    uses this on every request (see 07-observability/agent/main.py).
    """
    ctx = propagate.extract(headers)
    if baggage.get_baggage("session.id", ctx) != session:
        ctx = baggage.set_baggage("session.id", session, ctx)
    token = context.attach(ctx)
    try:
        yield
    finally:
        context.detach(token)


def setup_telemetry(service_name: str) -> TracerProvider:
    """Programmatic equivalent of the guide's ``opentelemetry-instrument`` wrapper."""
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
