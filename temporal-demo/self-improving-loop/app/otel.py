"""OpenTelemetry wiring shared by the worker and the starter.

Every span this process emits is stamped with the prompt version that was pinned
for the current run, so score, cost and latency can be charted per prompt version.
"""

import contextvars
import json
import logging
import os
from datetime import datetime, timezone

from opentelemetry import _logs as otel_logs
from opentelemetry import trace as otel_trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from temporalio.runtime import OpenTelemetryConfig, Runtime, TelemetryConfig

AGENT_NAME = os.environ.get("AGENT_NAME", "order_support_agent")
ENDPOINT_GRPC = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
ENDPOINT_HTTP = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT_HTTP", "http://otel-collector:4318")

prompt_version = contextvars.ContextVar("prompt_version", default=None)


class RunContextSpanProcessor(SpanProcessor):
    """Stamps agent name and pinned prompt version onto every span, including
    the ones the google-genai auto-instrumentation creates."""

    def on_start(self, span, parent_context=None):
        span.set_attribute("gen_ai.agent.name", AGENT_NAME)
        version = prompt_version.get()
        if version is not None:
            # A string, deliberately: this is a label to group by, not a number
            # to do arithmetic on.
            span.set_attribute("prompt_version", str(version))


class JsonLogFormatter(logging.Formatter):
    def __init__(self, service):
        super().__init__()
        self.service = service

    def format(self, record):
        ctx = otel_trace.get_current_span().get_span_context()
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "severity": record.levelname,
            "service": self.service,
            "log": record.getMessage(),
        }
        if ctx.is_valid:
            entry["trace_id"] = format(ctx.trace_id, "032x")
            entry["span_id"] = format(ctx.span_id, "016x")
        version = prompt_version.get()
        if version is not None:
            entry["prompt_version"] = version
        return json.dumps(entry, default=str)


def setup(service_name: str) -> Runtime:
    """Wire traces, logs and Temporal SDK metrics to the collector."""
    resource = Resource.create({"service.name": service_name})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(RunContextSpanProcessor())
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=ENDPOINT_GRPC, insecure=True))
    )
    otel_trace.set_tracer_provider(tracer_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{ENDPOINT_HTTP}/v1/logs"))
    )
    otel_logs.set_logger_provider(logger_provider)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter(service_name))
    root.addHandler(handler)
    root.addHandler(LoggingHandler(logger_provider=logger_provider))

    return Runtime(telemetry=TelemetryConfig(metrics=OpenTelemetryConfig(url=ENDPOINT_GRPC)))


def tracer():
    return otel_trace.get_tracer("self-improving-loop")


def flush():
    """Drain the batch processors. A short-lived CLI exits before they tick."""
    otel_trace.get_tracer_provider().force_flush()
    otel_logs.get_logger_provider().force_flush()
