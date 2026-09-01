# Vercel AI SDK Demo

Agent observability demo using the [Vercel AI SDK](https://ai-sdk.dev)
with its OpenTelemetry integration, exporting traces to Oodle via an
OTel Collector.

AI SDK 7 emits spans that follow the
[OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/),
so Oodle ingests them with no vendor mapping.

## Architecture

```
POST /generate | POST /agent
     |
     v
Node app (:8097) — AI SDK with @ai-sdk/otel
     |
     +---> OpenAI API (chat completions)
     |
     v
OTel Collector (OTLP :4318) --> Oodle (traces)
```

## What Gets Traced

| Span | `gen_ai.operation.name` | Key Attributes |
|------|------------------------|----------------|
| Agent run | `invoke_agent` | `gen_ai.usage.*`, `gen_ai.input.messages`, `gen_ai.output.messages` |
| Step | `agent_step` | one per model call in a multi-step run |
| Model request | `chat` | `gen_ai.request.model`, `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |
| Tool execution | `execute_tool` | `gen_ai.tool.name`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result` |

## The version decides everything

**AI SDK 7** moved OpenTelemetry out of the `ai` package into
`@ai-sdk/otel`, and telemetry is opt-*out*: `registerTelemetry(new
OpenTelemetry())` runs once and every call emits. There is no
`experimental_telemetry` flag any more, and passing one traces
nothing. This demo pins that path.

**AI SDK 5 and 6** emit spans from `experimental_telemetry`, but put
the prompt, the system prompt and the output in the `ai.*` namespace
rather than `gen_ai.*`. Token counts and the model still arrive.

Two more details are load-bearing here:

- `src/instrumentation.ts` names the service through an explicit
  `resource`. `NodeTracerProvider` does not read
  `OTEL_SERVICE_NAME`, so without it every trace lands under
  `unknown_service:node`.
- `src/server.ts` imports the instrumentation **first**.
  `registerTelemetry` has to run before any AI SDK call, or those
  calls emit nothing.

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
   make test-generate  # one model call, no tools
   make test-agent     # multi-step run with tool calls
   make test-all       # both
   ```

## API Endpoints

### POST /generate
One `generateText` call with no tools. The smallest traced unit.

### POST /agent
A multi-step `Agent` run with two tools, so the trace carries
`invoke_agent`, `agent_step`, `chat` and `execute_tool` spans.

### GET /health
Health check.

## Viewing Traces in Oodle

1. Log in to your Oodle instance
2. Navigate to **Agent Observability > Traces** (`/genai/traces`)
3. Filter by service name `vercel-ai-sdk-demo`
4. Click a trace to see the agent run, each step, the model calls
   with prompt and response content, tool arguments and results,
   token usage and the cost breakdown.

## Using a Different Model

`MODEL` takes an OpenAI model id:

```bash
MODEL=gpt-4o-mini
MODEL=gpt-4o
```

The app calls the Chat Completions API rather than the provider's
default Responses API, so it also runs against an OpenAI-compatible
gateway. Set `OPENAI_GATEWAY_URL` to use one.

## Cleanup

```bash
make clean
```
