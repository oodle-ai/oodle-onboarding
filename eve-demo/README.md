# eve Demo

Agent observability demo using [eve](https://eve.dev), Vercel's
filesystem-first agent framework, exporting traces to Oodle via an
OTel Collector.

eve runs on the AI SDK, so it emits spans that already follow the
[OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).
Oodle ingests them with no vendor mapping.

## Architecture

```
POST /chat/:threadId
     |
     v
eve agent (:8098) — tools, durable session, OTel instrumentation
     |
     +---> OpenAI API (chat completions)
     |
     v
OTel Collector (OTLP :4318) --> Oodle (traces)
```

## What Gets Traced

| Span | `gen_ai.operation.name` | Key Attributes |
|------|------------------------|----------------|
| Agent run | `invoke_agent` | `gen_ai.agent.name`, `gen_ai.conversation.id`, `gen_ai.usage.*` |
| Model request | `chat` | `gen_ai.request.model`, `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |
| Tool execution | `execute_tool` | `gen_ai.tool.name`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result` |

eve puts its session id on each span as `gen_ai.conversation.id`, so
every turn of one thread groups together in Oodle.

## Two settings decide whether this works

Both fail silently, so they are worth reading before you copy this
demo into your own agent.

### 1. `experimental.instrumentationProviders`

`agent/instrumentation/` is read only behind this flag in
`agent/agent.ts`. Without it both instrumentation files compile,
`eve build` succeeds, and no span is ever exported.

The flag also selects the layout that matters. eve's other layout
(a single `agent/instrumentation.ts` that calls `registerOTel`
itself) registers the global tracer provider, so Vercel Workflow
internals export beside the agent spans: a two-turn conversation
arrives as roughly 60 spans instead of 9.

### 2. The channel audience

eve withholds model messages for every conversation its channel does
not classify as `public`. Without that classification the spans still
arrive carrying the model, token counts, cost and tool names, so
every number in Oodle is correct and the transcript is empty.

`agent/channels/support.ts` sets it:

```ts
export default defineChannel({
  metadata: () => ({ audience: 'public' as const }),
  routes: [ /* ... */ ],
});
```

Slack public channels and Chat SDK workspace threads already classify
themselves this way. Set it only where the conversation really is
visible to a group, and only when the exporter is approved to receive
its content. `agent/instrumentation/otel.ts` then authorizes both
content directions with a `tracePolicy`; that policy narrows the
audience ceiling and never widens it.

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

4. Send test requests:
   ```bash
   make test-chat      # one turn, calls both tools
   make test-followup  # second turn on the same thread
   make test-all       # both, in order
   ```

## API Endpoints

### POST /chat/:threadId
Sends a message. Reusing a `threadId` continues the same durable eve
session, so the turns group under one conversation in Oodle.

### GET /eve/v1/health
Health check served by eve's built-in channel.

## Agent Layout

```
agent/
├── agent.ts                    model and the experimental flag
├── instructions.md             system prompt
├── channels/support.ts         HTTP entry point, public audience
├── instrumentation/otel.ts     process-wide OTel settings
├── instrumentation/oodle.ts    Oodle as a trace destination
└── tools/
    ├── get_weather.ts
    └── search_attractions.ts
```

## Viewing Traces in Oodle

1. Log in to your Oodle instance
2. Navigate to **Agent Observability > Traces** (`/genai/traces`)
3. Filter by service name `eve-demo`
4. Click a trace to see:
   - **Agent run spans** (`invoke_agent`) with the session id
   - **Model request spans** (`chat`) with prompt and response content
   - **Tool execution spans** (`execute_tool`) with arguments and results
   - **Token usage and cost** per model call
   - **Latency breakdown** across steps, tools and model calls

## Using a Different Model

`MODEL` takes an OpenAI model id:

```bash
MODEL=gpt-4o-mini
MODEL=gpt-4o
```

The agent calls the Chat Completions API rather than the provider's
default Responses API, so it also runs against an OpenAI-compatible
gateway. Set `OPENAI_GATEWAY_URL` to use one.

## Cleanup

```bash
make clean
```
