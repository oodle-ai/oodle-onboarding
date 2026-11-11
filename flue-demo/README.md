# Flue Demo

Agent observability demo using [Flue](https://flueframework.com), the
agent framework from the creators of Astro, exporting traces to Oodle
through an OTel Collector.

Flue's OpenTelemetry adapter, `@flue/opentelemetry`, turns the
runtime events of every agent into spans that follow the
[OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).
Oodle ingests them with no vendor mapping. This is the setup that the
**Flue** tile on the Oodle Integrations page ships.

## Architecture

```
make test-chat  (scripts/chat.mjs, the Flue Agent SDK)
     |
     v
Flue server (:8099) — TripPlanner agent, two tools, a packing subagent
     |
     +---> OpenAI API (gpt-4.1-mini)
     |
     v
OTel Collector (OTLP :4328 on the host) --> Oodle (traces)
```

## What Gets Traced

One message to the agent is one trace:

```
invoke_agent TripPlanner            AGENT       the user message and the reply
├── chat gpt-4.1-mini               GENERATION  messages, system prompt, tools, tokens
├── execute_tool get_weather        TOOL        arguments and result
├── chat gpt-4.1-mini
├── execute_tool find_activities    TOOL
├── chat gpt-4.1-mini
├── invoke_agent packing            AGENT       the subagent task
│   └── chat gpt-4.1-mini
└── chat gpt-4.1-mini               GENERATION  the final reply
```

| Span | `gen_ai.operation.name` | Key attributes |
|------|------------------------|----------------|
| Agent run, subagent task | `invoke_agent` | `gen_ai.agent.name`, `gen_ai.conversation.id`, `gen_ai.input.messages`, `gen_ai.output.messages` |
| Model turn | `chat` | `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.system_instructions`, `gen_ai.tool.definitions`, `gen_ai.usage.*` |
| Tool call | `execute_tool` | `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result` |

Only the `chat` spans carry token counts, so totals in Oodle are not
counted twice.

Every turn of one Flue conversation carries the same
`gen_ai.conversation.id`, so the Sessions view groups them. That id is
the one Flue makes (`conv_...`). The id you put in the agent URL
(`demo-trip` below) is on every span as `flue.instance.id`.

## The settings that decide what arrives

Read this before you copy the demo into your own agent.

- **`import './telemetry.ts'` comes first in `src/app.ts`.** It
  registers the instrumentation before any agent runs.
- **`flue run` never loads `app.ts`.** Under the CLI a telemetry
  module imported from `app.ts` does not run, and nothing is sent.
  Import it from the agent module as well if you trace `flue run`.
- **Name the service in code.** `NodeTracerProvider` does not read
  `OTEL_SERVICE_NAME`, so `telemetry.ts` reads it and sets the
  resource. Without that, every trace lands under
  `unknown_service:node`.
- **`provider.register()` is for your own spans.** Flue parents its
  spans from the tracer it is given. A span that your tool code
  starts (an HTTP call, a database query) is sent only when the
  provider is global, and it then joins the agent trace under that
  tool.
- **Flush when each submission settles, not on SIGTERM.** The Flue
  server calls `process.exit` as soon as it has stopped, so a flush
  started from a signal listener never ends. A three-turn run lost its
  last two turns that way. `telemetry.ts` flushes on
  `submission_settled`, so each turn is sent when it ends. A turn that
  a restart interrupts sends no spans.
- **Content is on by default.** Prompts, replies, tool arguments and
  results are sent. Set `FLUE_TRACE_CONTENT=false` to send spans with
  the model, tokens and tool names only.
- **Pin the OpenTelemetry packages.** The newest OTLP trace exporter
  asks for `@opentelemetry/api` 1.10 or later, and
  `@opentelemetry/sdk-trace-node` 2.x for an earlier one, so npm
  cannot install both unpinned (ERESOLVE).
- **Pin `@earendil-works/pi-ai` to 1.4.0.** `@flue/runtime` 2.3.0
  imports `Type` from it, and pi-ai 1.5.0 removed that export. With
  the newest pi-ai, `vite build` fails with "does not provide an
  export named 'Type'". `package.json` pins it with `overrides`.

## Prerequisites

- Docker & Docker Compose
- An [Oodle](https://oodle.ai) account (instance ID and API key)
- An [OpenAI](https://platform.openai.com/api-keys) API key

## Quick Start

```bash
make help        # view available commands
```

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your credentials:
   ```bash
   OODLE_INSTANCE=your-instance-id
   OODLE_API_KEY=your-api-key
   OPENAI_API_KEY=your-openai-api-key
   ```

3. Build and start all services:
   ```bash
   make up
   ```

4. Talk to the agent:
   ```bash
   make test-chat      # one turn: two tools and the packing subagent
   make test-followup  # a second turn on the same conversation
   make test-unknown   # a mythical city: the model answers without the tools
   make test-all       # all three, in order
   ```

5. Open **Agent Observability** in Oodle and filter on the service
   `flue-trip-planner`. Click a trace for the Transcript, the
   waterfall and the cost, or open **Sessions** to see the turns of
   `demo-trip` together.

Use `THREAD=<id>` to start a new conversation, for example
`make test-all THREAD=trip-2`.

## Send straight to Oodle

The exporter reads the standard OTLP variables, so skipping the
collector is an environment change and nothing in code:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=https://<OODLE_INSTANCE>-otlp.collector.oodle.ai
export OTEL_EXPORTER_OTLP_HEADERS="X-API-KEY=<OODLE_API_KEY>,X-OODLE-INSTANCE=<OODLE_INSTANCE>"
# GenAI spans carry whole prompts: without gzip a batch can be refused.
export OTEL_EXPORTER_OTLP_COMPRESSION=gzip
```

## Agent Layout

```
agent/
├── src/app.ts                  routes; imports telemetry first
├── src/telemetry.ts            OTel SDK and Flue's instrumentation
├── src/agents/trip-planner.ts  agent, tools, packing subagent
├── scripts/chat.mjs            sends a message, prints the reply
├── flue.config.ts              Node target
└── vite.config.ts              Flue's Vite plugin
```

## Other models

Set `MODEL` in `.env` to any Flue model specifier, for example
`anthropic/claude-haiku-4-5` with `ANTHROPIC_API_KEY`. To send OpenAI
requests through an OpenAI-compatible gateway, set `OPENAI_BASE_URL`;
`app.ts` then registers the OpenAI provider with that endpoint and the
same model catalog, so prices and the cost in Oodle stay correct.

## Cleanup

```bash
make clean
```
