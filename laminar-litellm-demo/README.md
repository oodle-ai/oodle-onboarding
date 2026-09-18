# Laminar + LiteLLM Demo

One LiteLLM coding agent, traced three ways, so the spans each
instrumentation writes can be read side by side:

| `TRACER` | Who writes the spans | Where they go |
|---|---|---|
| `litellm-otel` | LiteLLM's own `otel` callback (the setup the Oodle LiteLLM tile ships) | Oodle |
| `laminar` | Laminar's `LaminarLiteLLMCallback` plus `@observe` around turns and tools | Self-hosted [Laminar](https://github.com/lmnr-ai/lmnr) (Apache-2.0) |
| `laminar-to-oodle` | The same Laminar instrumentation, exporter pointed at Oodle | Oodle |

The agent is the same in every mode: a session of turns, each turn
a loop of model calls and tool executions until the model answers.
The prompt is built to make the differences show:

- the system prompt is over a thousand tokens, so the provider
  caches it from the second call on;
- every model call carries a session id and a user id in LiteLLM
  `metadata`;
- the task needs several tool calls per turn.

## Quick start

```bash
cp .env.example .env      # Oodle instance and key, provider key
make build

TRACER=litellm-otel      make run   # -> Oodle
TRACER=laminar-to-oodle  make run   # -> Oodle, Laminar's spans

make laminar-up                     # self-hosted Laminar on :5667
# sign in, create a project, copy its API key into .env
TRACER=laminar           make run   # -> Laminar
```

`make run-all` runs the three in turn. Each run prints, per model
call, the prompt tokens, the cached tokens and the tool calls the
model asked for, which is the ground truth to compare the traces
against.

## What each instrumentation writes

Measured on one run of this demo, `gpt-4o-mini` through OpenRouter,
`litellm` 1.101 and `lmnr` 0.7.62.

| | LiteLLM `otel` callback | Laminar callback |
|---|---|---|
| Trace shape | Every model call is its own trace. LiteLLM opens no span of its own and joins no parent, so a turn of eight calls is eight traces. | `agent_turn` root, `litellm.completion` children (`lmnr.span.type=LLM`), one TOOL span per tool execution with `lmnr.span.input` / `lmnr.span.output`. |
| Session and user | Not written. LiteLLM copies `metadata.*` from a fixed allowlist (`user_api_key_*`, `applied_guardrails`, `usage_object`, …); `session_id` and `user_id` are not on it. | `lmnr.association.properties.session_id`, `.user_id`, `.tags` on every span of the trace. |
| Cache | `gen_ai.usage.cache_read.input_tokens` only for Anthropic-shaped usage. OpenAI, xAI and every OpenAI-compatible provider report the hit as `prompt_tokens_details.cached_tokens`, which lands inside `metadata.usage_object` as a Python repr and nowhere else. | `gen_ai.usage.cache_read_input_tokens` from `cached_tokens`. |
| Tool calls the model asked for | `gen_ai.completion.N.function_call.name` / `.arguments`. `gen_ai.output.messages` carries the text part only, even when `finish_reason` is `tool_calls`. | Inside `gen_ai.output.messages`, as the assistant message's `tool_calls`. |
| Tools offered | `llm.request.functions.N.name` / `.description` / `.parameters` | `gen_ai.tool.definitions`, one JSON array. |
| Cost | `gen_ai.cost.total_cost` and a breakdown (`input_cost`, `output_cost`, `cache_read_cost`, …), cache accounted. | Not written; Laminar prices server-side. |
| Operation | `gen_ai.operation.name=chat` (with `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`) | Not written. `lmnr.span.type` says LLM / TOOL / DEFAULT. |
| Service name | `OTEL_SERVICE_NAME` | The script path. The Laminar SDK builds its own resource. |

## What Oodle shows today

With `TRACER=litellm-otel`, Agent Observability lists the run as
one trace per model call, each with one generation, `tool_calls: 0`,
no session and no user. Cache tokens read zero, so the cost is the
price-table estimate at the full input rate: with 90% of the input
cached, about four times what the provider bills.

With `TRACER=laminar-to-oodle`, the run is one trace per turn with a
proper tree, and Agent Observability does not list it at all: the
list filters on `gen_ai.operation.name`, which Laminar does not
write. The raw trace view has everything.

## Pointing the Laminar SDK at Oodle

The Laminar SDK exports over OTLP, and with no project API key it
reads the standard `OTEL_EXPORTER_OTLP_*` variables. That is all
`laminar-to-oodle` does:

```python
from lmnr import Laminar, LaminarLiteLLMCallback

Laminar.initialize(force_http=True)   # no key: OTEL_EXPORTER_OTLP_* wins
litellm.callbacks = [LaminarLiteLLMCallback()]
```

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=https://<instance>-otlp.collector.oodle.ai
export OTEL_EXPORTER_OTLP_HEADERS="X-API-KEY=<key>,X-OODLE-INSTANCE=<instance>"
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

## Self-hosting Laminar

`make laminar-up` clones `lmnr-ai/lmnr` into `.lmnr/` and runs its
`docker compose up -d`: Postgres, ClickHouse, Quickwit, the app
server (HTTP `:8000`, gRPC `:8001`) and the UI on
http://localhost:5667. Sign in, create a project and copy its API
key to `LMNR_PROJECT_API_KEY` in `.env`. The SDK is pointed at it
with `LMNR_BASE_URL=http://host.docker.internal` from inside the
container, or `http://localhost` from the host.
