"""Messages API over plain HTTP, traced by Claude's API tracing.

No Claude SDK here: every request is an httpx POST to /v1/messages. The
spans of what happens inside Anthropic (the request, each model request,
server tools) come from Anthropic's side, sent to the OTLP destination
added with scripts/create-destination.sh. This app only opens one span of
its own per scenario and passes its trace context in the `traceparent`
header, so Anthropic's spans land in the same trace, under that span.

Usage: python main.py [chat|web_search|stream|vision ...]   (default: all four)
"""

import base64
import json
import os
import sys
from pathlib import Path

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
    """Copy the response's summary onto the app span.

    Deliberately not gen_ai.*: Anthropic's spans under this one already carry
    gen_ai.usage.*, and a backend that sums them over every span would count
    each token twice.
    """
    span.set_attribute("anthropic.request_id", response.headers.get("request-id", ""))
    span.set_attribute("demo.response.model", message.get("model", ""))
    span.set_attribute("demo.stop_reason", message.get("stop_reason") or "")
    usage = message.get("usage", {})
    span.set_attribute("demo.usage.input_tokens", usage.get("input_tokens", 0))
    span.set_attribute("demo.usage.output_tokens", usage.get("output_tokens", 0))


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


def read_stream(response: httpx.Response) -> dict:
    """Print a streamed response as it arrives and return the whole message.

    Thinking summaries (with `display: "summarized"`) arrive as thinking
    deltas before the answer; they're printed dimmed.
    """
    message: dict = {}
    for line in response.iter_lines():
        if not line.startswith("data: "):
            continue
        event = json.loads(line[len("data: ") :])
        if event["type"] == "message_start":
            message = event["message"]
        elif event["type"] == "content_block_start":
            message["content"].append(event["content_block"])
        elif event["type"] == "content_block_delta":
            block, delta = message["content"][event["index"]], event["delta"]
            if delta["type"] == "text_delta":
                block["text"] += delta["text"]
                print(delta["text"], end="", flush=True)
            elif delta["type"] == "thinking_delta":
                block["thinking"] += delta["thinking"]
                print(f"\033[2m{delta['thinking']}\033[0m", end="", flush=True)
        elif event["type"] == "message_delta":
            # Cumulative usage and the stop reason arrive at the end.
            message["usage"] = {**message.get("usage", {}), **event["usage"]}
            message["stop_reason"] = event["delta"].get("stop_reason")
    print()
    return message


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
    with client.stream("POST", API_URL, headers=headers(), json=body) as response:
        response.raise_for_status()
        message = read_stream(response)
    record(span, response, message)
    check_refusal(message)


IMAGES = Path(__file__).parent / "images"

# (image, question) per turn, in order.
VISION_TURNS = [
    ("eye.png", "Describe this image. Hint: its a body part"),
    ("bee.png", "Describe this image. Hint: its an insect"),
    ("letter-m.png", "Describe this image. Hint: its a letter of the alphabet"),
]


def image_block(name: str) -> dict:
    data = base64.standard_b64encode((IMAGES / name).read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}


def vision(client: httpx.Client, span: trace.Span) -> None:
    """A multi-turn image conversation, one request per turn.

    Replays a captured chat: a system prompt, adaptive thinking with summaries
    shown, effort high, and an image with each question. Only the latest turn
    sends its image; earlier turns stay in the history as text, the question
    and Claude's description, so the history doesn't resend every image.

    Anthropic's span of each request records the image as a part of type
    `anthropic_image` without its data, the thinking summary as a `reasoning`
    part, the system prompt in gen_ai.system_instructions, and the effort in
    gen_ai.request.reasoning.level.
    """
    history: list[dict] = []
    for turn, (image, question) in enumerate(VISION_TURNS, start=1):
        print(f"\n[turn {turn}] {question}")
        body = {
            "model": MODEL,
            # A large max_tokens needs streaming, or the request can time out.
            "max_tokens": 128000,
            "stream": True,
            "fallbacks": "default",
            "system": "You are a helpful assistant.",
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": "high"},
            "messages": history
            + [{"role": "user", "content": [image_block(image), {"type": "text", "text": question}]}],
        }
        with client.stream("POST", API_URL, headers=headers(), json=body) as response:
            response.raise_for_status()
            message = read_stream(response)
        check_refusal(message)
        history += [
            {"role": "user", "content": question},
            {"role": "assistant", "content": text_of(message)},
        ]
    record(span, response, message)
    span.set_attribute("demo.turns", len(VISION_TURNS))


SCENARIOS = {"chat": chat, "web_search": web_search, "stream": stream, "vision": vision}


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
