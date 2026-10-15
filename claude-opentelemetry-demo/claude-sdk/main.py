"""Claude Python SDK, traced by the SDK's own OpenTelemetry spans.

The SDK emits a CLIENT span for every request it sends, through whatever
tracer provider the application registers. Registering one, below, is the
whole setup: the Claude calls themselves don't change. Content mode comes
from ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE.

With an API tracing destination also in place (scripts/create-destination.sh),
the SDK sends `traceparent` on each request, so Anthropic's SERVER span of the
same request nests under the SDK's span in one trace.

Usage: python main.py [create|stream|tool_runner|count_tokens|conversation ...]
       (default: all five)
"""

import os
import sys
import uuid

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Register the tracer provider before the first Claude call.
provider = TracerProvider(
    resource=Resource.create(
        {"service.name": os.environ.get("OTEL_SERVICE_NAME", "claude-otel-sdk")}
    )
)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("claude-otel-sdk")

import anthropic  # noqa: E402
from anthropic import beta_tool  # noqa: E402

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")

# Re-runs a declined request on Anthropic's recommended fallback model.
FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

client = anthropic.Anthropic()


def text_of(message) -> str:
    if message.stop_reason == "refusal":
        raise RuntimeError(f"request declined: {message.stop_details}")
    return "".join(b.text for b in message.content if b.type == "text")


def create() -> None:
    """One anthropic.messages.create span."""
    message = client.beta.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": "In two sentences, what is a span in OpenTelemetry?"}],
        **FALLBACK,
    )
    print(text_of(message))


def stream() -> None:
    """A stream's span ends when the stream has been read to the end.

    Read through the stream helper, the span also carries the response in
    content mode.
    """
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": "Write a four-line poem about distributed traces."}],
        **FALLBACK,
    ) as s:
        for text in s.text_stream:
            print(text, end="", flush=True)
        message = s.get_final_message()
    print()
    text_of(message)


@beta_tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: City name, e.g. Oslo.
    """
    # A real tool would call a weather API; its spans would nest under the tool span.
    with tracer.start_as_current_span("weather.lookup") as span:
        span.set_attribute("weather.city", city)
        return f"{city}: 4°C, light rain, wind 6 m/s from the west."


def tool_runner() -> None:
    """anthropic.messages.tool_runner > messages.create, custom_tool_use, messages.create."""
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4096,
        tools=[get_weather],
        messages=[{"role": "user", "content": "Should I bring an umbrella in Oslo today?"}],
        **FALLBACK,
    )
    last = None
    for message in runner:
        last = message
    print(text_of(last))


def count_tokens() -> None:
    """anthropic.messages.count_tokens: an SDK-only span (the API emits none)."""
    result = client.messages.count_tokens(
        model=MODEL,
        messages=[{"role": "user", "content": "How many tokens is this sentence?"}],
    )
    print(f"input_tokens={result.input_tokens}")


def conversation() -> None:
    """Two turns linked by gen_ai.conversation.id.

    with_options() replaces the client's whole OpenTelemetry option, so start
    from client.open_telemetry to keep the content mode.
    """
    convo = client.with_options(
        open_telemetry={**client.open_telemetry, "conversation_id": f"demo-{uuid.uuid4().hex[:8]}"}
    )
    messages = [{"role": "user", "content": "Pick a random European capital. Just the name."}]
    first = convo.beta.messages.create(model=MODEL, max_tokens=512, messages=messages, **FALLBACK)
    print(text_of(first))
    messages += [
        {"role": "assistant", "content": first.content},
        {"role": "user", "content": "One fact about it, in one sentence."},
    ]
    second = convo.beta.messages.create(model=MODEL, max_tokens=512, messages=messages, **FALLBACK)
    print(text_of(second))


SCENARIOS = {
    "create": create,
    "stream": stream,
    "tool_runner": tool_runner,
    "count_tokens": count_tokens,
    "conversation": conversation,
}


def main() -> None:
    print(f"content_mode={client.open_telemetry['traces']['content_mode']}")
    for name in sys.argv[1:] or list(SCENARIOS):
        print(f"\n=== {name} ===")
        # The SDK's spans nest under this one.
        with tracer.start_as_current_span(f"demo.{name}") as span:
            SCENARIOS[name]()
            print(f"trace_id={span.get_span_context().trace_id:032x}")
    provider.shutdown()


if __name__ == "__main__":
    main()
