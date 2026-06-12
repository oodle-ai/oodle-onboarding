"""LLM observability demo using official OpenTelemetry GenAI instrumentation.

Google Gemini calls are auto-instrumented via opentelemetry-instrumentation-google-genai.
Traces and logs (prompt/response content) are exported to Oodle
via an OpenTelemetry Collector.
"""

import os

import google.genai
from flask import Flask, jsonify, request
from opentelemetry import _logs as otel_logs
from opentelemetry import trace as otel_trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_opentelemetry():
    resource = Resource.create({"service.name": "llmops-otel-demo"})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    otel_trace.set_tracer_provider(tracer_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    otel_logs.set_logger_provider(logger_provider)


setup_opentelemetry()
GoogleGenAiSdkInstrumentor().instrument()

app = Flask(__name__)
client = google.genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "llmops-otel-demo"})


@app.route("/chat", methods=["POST"])
def chat():
    """Send a chat message to Gemini.

    Request body: {"message": "Hello!", "model": "gemini-flash-latest"}
    """
    body = request.get_json(force=True)
    message = body.get("message", "Say hello!")
    model = body.get("model", DEFAULT_MODEL)

    try:
        response = client.models.generate_content(
            model=model,
            contents=message,
            config={"system_instruction": "You are a helpful assistant. Keep responses concise."},
        )
        reply = response.text
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    return jsonify({"reply": reply, "model": model})


@app.route("/summarize", methods=["POST"])
def summarize():
    """Summarize a block of text.

    Request body: {"text": "Long text to summarize..."}
    """
    body = request.get_json(force=True)
    text = body.get("text", "")
    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=text,
            config={"system_instruction": "Summarize the following text in 1-2 sentences."},
        )
        summary = response.text
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    return jsonify({"summary": summary})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8090"))
    app.run(host="0.0.0.0", port=port)
