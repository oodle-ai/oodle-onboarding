# OpenClaw Demo — Langfuse-attribute tracing into Oodle

Runs the real [OpenClaw](https://github.com/openclaw/openclaw) agent with a
plugin that records its runs through the real
[Langfuse SDK](https://github.com/langfuse/langfuse-js) and exports the spans
over OTLP to Oodle.

Nothing here is simulated: OpenClaw calls a real model, and every `langfuse.*`
attribute on the resulting spans is written by `@langfuse/tracing` itself.

## Why this exists

The Langfuse SDKs describe an observation in their own **`langfuse.*`**
namespace rather than the GenAI semantic conventions:

| Langfuse attribute | Semconv equivalent |
|---|---|
| `langfuse.observation.type` | `gen_ai.operation.name` |
| `langfuse.observation.input` / `.output` | `gen_ai.input.messages` / `.output.messages` |
| `langfuse.observation.model.name` | `gen_ai.request.model` |
| `langfuse.observation.usage_details` | `gen_ai.usage.*`, **cache reads included** |
| `langfuse.trace.input` / `.output` | the run's payload, on the root span |
| `langfuse.session.id` | `gen_ai.conversation.id` |

Oodle resolves these at ingest, so the trace reaches Agent Observability with
a transcript, model, tokens and cost. Use this demo to verify that end to end
against a genuine producer.

Note what OpenClaw's own OTel exporter (`diagnostics-otel`) does instead: it
emits standard `gen_ai.*` spans. This demo is deliberately the *other* path.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   openclaw container                             │
│                                                                  │
│  openclaw agent --local -m "…"        (real CLI, real model)     │
│    │                                                             │
│    ├─ before_agent_start ─┐                                      │
│    ├─ llm_input ──────────┤  plugin: langfuse-tracer             │
│    ├─ llm_output ─────────┤  @langfuse/tracing startObservation  │
│    ├─ after_tool_call ────┤  → NodeTracerProvider                │
│    └─ agent_end ──────────┘  → OTLP exporter                     │
│                                                                  │
└────────────────────────────┬─────────────────────────────────────┘
                             ▼
                  OTel Collector (:4318) ──► Oodle
```

Spans produced per turn:

| Span | Observation type | Carries |
|---|---|---|
| `openclaw.agent_run` | `span` (root) | trace name, session id, tags, agent/channel/trigger metadata, `langfuse.trace.input` / `.output` |
| `openclaw.llm_generation` | `generation` | model, the prompt payload OpenClaw built, the reply, `usage_details` incl. cache reads |
| `openclaw.tool_call` | `tool` | tool params and result |

## Prerequisites

- Docker and Docker Compose
- An [Oodle](https://oodle.ai) account (instance ID + API key)
- A [Google Gemini](https://aistudio.google.com/apikey) API key — OpenClaw
  calls the model for real

## Quick start

```bash
cp .env.example .env
# Edit .env with your Oodle credentials and Gemini key

make up
make heartbeat        # one agent turn
make tools            # a turn that uses a tool
```

Every turn is a one-shot `openclaw agent --local`, so its spans are flushed
before the process exits.

```bash
make ask MESSAGE="What is OpenTelemetry in one sentence?"
make ask SESSION=morning MESSAGE="…"   # same session key groups turns
```

## The plugin

`plugin/index.js` is a normal OpenClaw plugin (`definePluginEntry`), installed
into the container with `openclaw plugins install --link /plugin`. It maps
OpenClaw's typed hooks onto Langfuse observations and owns nothing else — the
attribute names all come from `@langfuse/tracing`.

Two things it needs in `openclaw.json`, both in `openclaw/openclaw.json`:

- `plugins.allow` must list `langfuse-tracer`.
- `plugins.entries.langfuse-tracer.hooks.allowConversationAccess` must be
  `true`. Without it OpenClaw withholds `llm_input`, `llm_output` and
  `agent_end` from non-bundled plugins — they carry raw conversation content —
  and you get the run span with no generation under it.

`agent_end` and `llm_output` can arrive in either order (on the embedded
harness `agent_end` comes first), so whichever lands last finishes the run.

## Verifying in Oodle

1. **Agent Observability → Traces** lists the run. This is the check that
   matters: the list filters on `span::gen_ai.operation.name=~".+"`, so the
   trace only appears if the Langfuse observation type was resolved onto an
   operation.
2. Open the trace. The **Transcript** tab shows system / user / assistant
   turns — OpenClaw logs its payload as `{systemPrompt, prompt,
   historyMessages}`, which Oodle reads as a conversation.
3. The `openclaw.llm_generation` observation shows the model, tokens and cost,
   cache reads included. Those exist **only** in
   `langfuse.observation.usage_details`.
4. **Sessions** groups turns that share a session key (`make ask SESSION=…`).

## Troubleshooting

```bash
make plugins    # the plugin should be listed as enabled, source /plugin/index.js
make logs-collector
```

- `plugin not found: langfuse-tracer` — the link install did not run; restart
  the container (`make restart`).
- Run span but no generation span — `allowConversationAccess` is not set.
- No spans at all — check the collector is reachable at
  `OTEL_EXPORTER_OTLP_ENDPOINT` and that the turn actually reached the model.
