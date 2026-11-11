"""Export managed-agent trace events and local tool spans to Oodle."""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_telemetry(service_name: str) -> TracerProvider:
    instance = os.environ.get("OODLE_INSTANCE", "").strip()
    api_key = os.environ.get("OODLE_API_KEY", "").strip()
    if not instance or not api_key or instance == "your-instance-id" or api_key == "your-api-key":
        raise ValueError("Set OODLE_INSTANCE and OODLE_API_KEY in .env before running the demo")
    endpoint = os.environ.get("OODLE_OTLP_ENDPOINT") or f"https://{instance}-otlp.collector.oodle.ai"

    provider = TracerProvider(resource=Resource.create({
        "service.name": service_name,
        "service.namespace": "oodle-amazon-demos",
        "cloud.provider": "aws",
        "cloud.region": os.environ.get("AWS_REGION", "us-west-2"),
    }))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
        endpoint=f"{endpoint.rstrip('/')}/v1/traces",
        headers={"X-OODLE-INSTANCE": instance, "X-API-KEY": api_key},
        compression=Compression.Gzip,
        timeout=10,
    )))
    trace.set_tracer_provider(provider)
    return provider
