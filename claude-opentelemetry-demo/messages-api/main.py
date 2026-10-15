"""Messages API over plain HTTP, traced by Claude's API tracing.

No Claude SDK here: every request is an httpx POST to /v1/messages. The
spans of what happens inside Anthropic (the request, each model request,
server tools) come from Anthropic's side, sent to the OTLP destination
added with scripts/create-destination.sh. This app only opens one span of
its own per scenario and passes its trace context in the `traceparent`
header, so Anthropic's spans land in the same trace, under that span.

Usage: python main.py [chat|web_search|stream ...]   (default: all three)
"""

import json
import os
import sys

import httpx
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

API_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/") + "/v1/messages"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")

# Re-runs a declined request on Anthropic's recommended fallback model.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

provider = TracerProvider(
    resource=Resource.create(
        {"service.name": os.environ.get("OTEL_SERVICE_NAME", "claude-otel-messages-api")}
    )
)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("claude-otel-messages-api")

propagator = TraceContextTextMapPropagator()


def headers() -> dict[str, str]:
    """Request headers carrying the active span's trace context."""
    h = {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "anthropic-beta": FALLBACK_BETA,
        "content-type": "application/json",
    }
    # An API key not scoped to a workspace must name one on every request.
    if workspace_id := os.environ.get("ANTHROPIC_WORKSPACE_ID"):
        h["anthropic-workspace-id"] = workspace_id
    # Adds `traceparent: 00-<trace id>-<span id>-<flags>`. The flags' sampled
    # bit (01) must be on, or Anthropic emits no span for the request.
    propagator.inject(h)
    return h


def text_of(message: dict) -> str:
    return "".join(b["text"] for b in message["content"] if b["type"] == "text")


def record(span: trace.Span, response: httpx.Response, message: dict) -> None:
    span.set_attribute("anthropic.request_id", response.headers.get("request-id", ""))
    span.set_attribute("gen_ai.response.model", message.get("model", ""))
    span.set_attribute("gen_ai.response.finish_reasons", [message.get("stop_reason") or ""])
    usage = message.get("usage", {})
    span.set_attribute("gen_ai.usage.input_tokens", usage.get("input_tokens", 0))
    span.set_attribute("gen_ai.usage.output_tokens", usage.get("output_tokens", 0))


def check_refusal(message: dict) -> None:
    if message.get("stop_reason") == "refusal":
        raise RuntimeError(f"request declined: {message.get('stop_details')}")


def chat(client: httpx.Client, span: trace.Span) -> None:
    """One request: anthropic.messages.create > anthropic.model_request."""
    body = {
        "model": MODEL,
        "max_tokens": 1024,
        "fallbacks": "default",
        "messages": [
            {"role": "user", "content": "In two sentences, what is a span in OpenTelemetry?"}
        ],
    }
    response = client.post(API_URL, headers=headers(), json=body)
    response.raise_for_status()
    message = response.json()
    record(span, response, message)
    check_refusal(message)
    print(text_of(message))


def web_search(client: httpx.Client, span: trace.Span) -> None:
    """A server tool: the API runs the search itself.

    Anthropic's spans show one anthropic.model_request per model turn and an
    anthropic.tool_use web_search span for each search, none of which a
    client can see on its own.
    """
    messages = [
        {
            "role": "user",
            "content": "Search the web: what is the latest stable release of the "
            "OpenTelemetry Collector? Answer in one line with the version.",
        }
    ]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 2}]
    # A long server-tool turn can come back paused; send it back to resume.
    for _ in range(3):
        body = {
            "model": MODEL,
            "max_tokens": 4096,
            "fallbacks": "default",
            "tools": tools,
            "messages": messages,
        }
        response = client.post(API_URL, headers=headers(), json=body)
        response.raise_for_status()
        message = response.json()
        check_refusal(message)
        if message["stop_reason"] != "pause_turn":
            break
        messages.append({"role": "assistant", "content": message["content"]})
    record(span, response, message)
    searches = sum(1 for b in message["content"] if b["type"] == "server_tool_use")
    span.set_attribute("demo.web_searches", searches)
    print(f"({searches} searches) {text_of(message)}")


def stream(client: httpx.Client, span: trace.Span) -> None:
    """A streamed response, read to the end over SSE."""
    body = {
        "model": MODEL,
        "max_tokens": 2048,
        "fallbacks": "default",
        "stream": True,
        "messages": [
            {"role": "user", "content": "Write a four-line poem about distributed traces."}
        ],
    }
    output_tokens = 0
    with client.stream("POST", API_URL, headers=headers(), json=body) as response:
        response.raise_for_status()
        span.set_attribute("anthropic.request_id", response.headers.get("request-id", ""))
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[len("data: ") :])
            if event["type"] == "content_block_delta" and event["delta"]["type"] == "text_delta":
                print(event["delta"]["text"], end="", flush=True)
            elif event["type"] == "message_delta":
                output_tokens = event["usage"].get("output_tokens", output_tokens)
                if event["delta"].get("stop_reason") == "refusal":
                    raise RuntimeError("request declined")
    print()
    span.set_attribute("gen_ai.usage.output_tokens", output_tokens)


SCENARIOS = {"chat": chat, "web_search": web_search, "stream": stream}


def main() -> None:
    names = sys.argv[1:] or list(SCENARIOS)
    with httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        for name in names:
            print(f"\n=== {name} ===")
            # One span of our own per scenario; Anthropic's spans nest under it.
            with tracer.start_as_current_span(f"demo.{name}") as span:
                SCENARIOS[name](client, span)
                print(f"trace_id={span.get_span_context().trace_id:032x}")
    provider.shutdown()


if __name__ == "__main__":
    main()
