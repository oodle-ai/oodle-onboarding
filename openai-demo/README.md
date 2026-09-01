# OpenAI Demo

LLM observability demo that auto-instruments the
[OpenAI SDK](https://github.com/openai/openai-python) with the
official
[OpenTelemetry GenAI instrumentation](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation-genai/opentelemetry-instrumentation-openai-v2),
exporting traces and logs to Oodle via an OTel Collector.

Only first-party OpenTelemetry packages are used. There is no
change at the call site: the instrumentation patches the SDK.

## Architecture

```
POST /chat | POST /tool-call
     |
     v
FastAPI app (:8095) — OTel GenAI instrumentation
     |
     +---> OpenAI API (chat completions)
     |
     v
OTel Collector (OTLP :4318) --> Oodle (traces + logs)
```

## What Gets Traced

| Span | `gen_ai.operation.name` | Key Attributes |
|------|------------------------|----------------|
| Model request | `chat` | `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons` |

## Prompts and responses arrive as log records

This instrumentation writes the message content as **log records**,
not span attributes, through the logger provider it is registered
with. `main.py` therefore sets up a `LoggerProvider` beside the
tracer provider, and the collector runs a `logs` pipeline as well as
a `traces` one. Registered against traces alone, the spans still
arrive and carry no content at all.

Two environment settings in `docker-compose.yml` complete it:

- `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_and_event`

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
   make test-chat   # one model call
   make test-tool   # two model calls around a tool execution
   make test-all    # both
   ```

## API Endpoints

### POST /chat
One chat completion, no tools.

### POST /tool-call
Two chat completions around one local tool execution, so the trace
shows the tool-calling round trip.

### GET /health
Health check.

## Viewing Traces in Oodle

1. Log in to your Oodle instance
2. Navigate to **Agent Observability > Traces** (`/genai/traces`)
3. Filter by service name `openai-demo`
4. Click a trace to see the model, token usage, cost, and the
   prompt and response content

## Using a Different Model

`MODEL` takes an OpenAI model id:

```bash
MODEL=gpt-4o-mini
MODEL=gpt-4o
```

Set `OPENAI_GATEWAY_URL` to call an OpenAI-compatible gateway instead.

## Cleanup

```bash
make clean
```
