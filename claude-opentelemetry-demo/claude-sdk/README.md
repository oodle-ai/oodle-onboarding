# Claude SDK (Python SDK tracing)

The `anthropic` Python SDK emits OpenTelemetry spans on its own. It uses the
tracer provider the application registers, so the setup is only this, and
it must come before the first Claude call:

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

client = anthropic.Anthropic()   # unchanged; its calls are now traced
```

The spans go to this demo's collector and on to Oodle. No destination or
admin is needed. With the [API tracing destination](../README.md#api-tracing-destination)
also on, the SDK sends `traceparent` with each request, and Anthropic's SERVER
span of that request nests under the SDK's CLIENT span.

## Scenarios

```bash
make sdk                                                  # all five
docker compose run --rm --build claude-sdk tool_runner    # one
```

| Scenario | Call | SDK spans (under `demo.<scenario>`) |
|---|---|---|
| `create` | `beta.messages.create` | `anthropic.messages.create` |
| `stream` | `beta.messages.stream(...)` read to the end | `anthropic.messages.create` (ends when the stream is read or closed) |
| `tool_runner` | `beta.messages.tool_runner` with a `@beta_tool` | `anthropic.messages.tool_runner` > `anthropic.messages.create`, `anthropic.custom_tool_use get_weather` > `weather.lookup`, `anthropic.messages.create` |
| `count_tokens` | `messages.count_tokens` | `anthropic.messages.count_tokens` (SDK only; the API emits none) |
| `conversation` | Two turns through `with_options(open_telemetry={..., "conversation_id": ...})` | Two `anthropic.messages.create` with the same `gen_ai.conversation.id` |

`weather.lookup` is a span the tool opens itself. It nests under the SDK's
tool span with no extra wiring.

## Options

| Setting | Effect |
|---|---|
| `ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE=content` | Prompts and responses on the spans (default `metadata_only`) |
| `ANTHROPIC_OPEN_TELEMETRY_TRACES_MAX_CONTENT_BYTES` | Per-span content limit (default 750000). Over it, the oldest messages are dropped and `anthropic.content.truncated=true` |
| `ANTHROPIC_OPEN_TELEMETRY=false` | No SDK spans. Use it when a third-party Anthropic instrumentor already traces the SDK |
| `Anthropic(open_telemetry={...})` | The same options in code. Once given, the client reads none of the environment variables |

`with_options(open_telemetry=...)` replaces the client's whole option, so
spread `client.open_telemetry` into it, as `conversation()` does, to keep
the content mode.

Requests go through `client.beta.messages` so they can send
`fallbacks="default"` (beta `server-side-fallback-2026-07-01`). That
re-runs a declined request on Anthropic's recommended fallback model.
