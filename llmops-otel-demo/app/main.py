"""LLM observability demo using official OpenTelemetry GenAI instrumentation.

Google Gemini calls are auto-instrumented via opentelemetry-instrumentation-google-genai.
Traces, structured JSON logs, and prompt/response content are exported to Oodle
via an OpenTelemetry Collector.
"""

import contextvars
import json
import logging
import os
from datetime import datetime, timezone

import google.genai
from flask import Flask, jsonify, request
from opentelemetry import _logs as otel_logs
from opentelemetry import trace as otel_trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_current_user = contextvars.ContextVar("current_user", default=None)


class UserAttributeSpanProcessor(SpanProcessor):
    """Injects the current user into every span, including auto-instrumented ones."""

    def on_start(self, span, parent_context=None):
        user = _current_user.get()
        if user:
            span.set_attribute("user", user)


class JsonLogFormatter(logging.Formatter):
    """Emits each log record as a single JSON line with trace context."""

    def format(self, record):
        span = otel_trace.get_current_span()
        ctx = span.get_span_context()
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "severity": record.levelname,
            "log": record.getMessage(),
        }
        if ctx.is_valid:
            entry["trace_id"] = format(ctx.trace_id, "032x")
            entry["span_id"] = format(ctx.span_id, "016x")
        for key in ("user", "endpoint", "model", "error", "llm_input", "llm_output"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        return json.dumps(entry, default=str)


def setup_opentelemetry():
    resource = Resource.create({"service.name": "llmops-otel-demo"})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(UserAttributeSpanProcessor())
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    otel_trace.set_tracer_provider(tracer_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    otel_logs.set_logger_provider(logger_provider)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Structured JSON logs to stdout
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root.addHandler(handler)

    # Bridge Python logs to OTel (exported to Oodle via OTLP)
    root.addHandler(LoggingHandler(logger_provider=logger_provider))

    # Suppress werkzeug request logging — we emit our own structured logs
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


setup_opentelemetry()
GoogleGenAiSdkInstrumentor().instrument()

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)
client = google.genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
LOG_LLM_CONTENT = os.environ.get("LOG_LLM_CONTENT", "").lower() in ("1", "true", "yes")
logger = logging.getLogger(__name__)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "llmops-otel-demo"})


@app.route("/chat", methods=["POST"])
def chat():
    """Send a chat message to Gemini.

    Request body: {"message": "Hello!", "model": "gemini-flash-latest", "user": "alice"}
    """
    body = request.get_json(force=True)
    message = body.get("message", "Say hello!")
    model = body.get("model", DEFAULT_MODEL)
    user = body.get("user", "anonymous")

    _current_user.set(user)
    span = otel_trace.get_current_span()
    span.set_attribute("user", user)
    log_extra = {"user": user, "model": model, "endpoint": "/chat"}

    logger.info("Chat request received", extra=log_extra)

    try:
        response = client.models.generate_content(
            model=model,
            contents=message,
            config={"system_instruction": "You are a helpful assistant. Keep responses concise."},
        )
        reply = response.text
    except Exception as e:
        logger.error("Chat request failed", extra={**log_extra, "error": str(e)})
        return jsonify({"error": str(e)}), 502

    completed_extra = {**log_extra}
    if LOG_LLM_CONTENT:
        completed_extra["llm_input"] = message
        completed_extra["llm_output"] = reply
    logger.info("Chat request completed", extra=completed_extra)
    return jsonify({"reply": reply, "model": model})


@app.route("/summarize", methods=["POST"])
def summarize():
    """Summarize a block of text.

    Request body: {"text": "Long text to summarize...", "user": "alice"}
    """
    body = request.get_json(force=True)
    text = body.get("text", "")
    user = body.get("user", "anonymous")

    if not text:
        return jsonify({"error": "text is required"}), 400

    _current_user.set(user)
    span = otel_trace.get_current_span()
    span.set_attribute("user", user)
    log_extra = {"user": user, "endpoint": "/summarize"}

    logger.info("Summarize request received", extra=log_extra)

    try:
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=text,
            config={"system_instruction": "Summarize the following text in 1-2 sentences."},
        )
        summary = response.text
    except Exception as e:
        logger.error("Summarize request failed", extra={**log_extra, "error": str(e)})
        return jsonify({"error": str(e)}), 502

    completed_extra = {**log_extra}
    if LOG_LLM_CONTENT:
        completed_extra["llm_input"] = text
        completed_extra["llm_output"] = summary
    logger.info("Summarize request completed", extra=completed_extra)
    return jsonify({"summary": summary})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8090"))
    app.run(host="0.0.0.0", port=port)
