"""Traceloop (OpenLLMetry) demo app with Google Gemini instrumentation.

This app demonstrates LLM observability using the Traceloop SDK.
All Gemini calls are automatically instrumented and traces are exported
to Oodle via an OpenTelemetry Collector.
"""

import os

from flask import Flask, jsonify, request
from google import genai
from traceloop.sdk import Traceloop
from traceloop.sdk.decorators import workflow

app = Flask(__name__)
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Initialize Traceloop SDK.
# When TRACELOOP_BASE_URL is set (e.g., to the OTel Collector at http://otel-collector:4318),
# the SDK exports traces there via OTLP HTTP. The collector then forwards them to Oodle.
Traceloop.init(app_name="traceloop-demo")


@workflow(name="chat")
def run_chat(user_message: str, model: str) -> str:
    """Run a simple chat completion and return the response."""
    response = client.models.generate_content(
        model=model,
        contents=user_message,
        config={"system_instruction": "You are a helpful assistant. Keep responses concise."},
    )
    return response.text


@workflow(name="summarize")
def run_summarize(text: str) -> str:
    """Summarize the given text."""
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=text,
        config={"system_instruction": "Summarize the following text in 1-2 sentences."},
    )
    return response.text


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "traceloop-demo"})


@app.route("/chat", methods=["POST"])
def chat():
    """Send a chat message to Gemini.

    Request body: {"message": "Hello!", "model": "gemini-2.0-flash"}
    """
    body = request.get_json(force=True)
    message = body.get("message", "Say hello!")
    model = body.get("model", "gemini-2.0-flash")

    reply = run_chat(message, model)
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

    summary = run_summarize(text)
    return jsonify({"summary": summary})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8090"))
    app.run(host="0.0.0.0", port=port)
