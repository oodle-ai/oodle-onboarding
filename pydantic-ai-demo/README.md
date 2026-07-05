# Pydantic AI Demo

Agent observability demo using [Pydantic AI](https://pydantic.dev/pydantic-ai) with built-in OpenTelemetry instrumentation, exporting traces to Oodle via an OTel Collector.

Pydantic AI automatically emits spans following the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — no manual instrumentation required. One call to `Agent.instrument_all()` enables tracing for all agents.

## Architecture

```
User Request
     |
     v
FastAPI App (:8091) — Pydantic AI agents with OTel instrumentation
     |
     +---> LLM API (OpenAI, Google, etc.)
     |
     v
OTel Collector (OTLP :4318) --> Oodle (traces)
```

## What Gets Traced

Pydantic AI v5 instrumentation emits spans for:

| Span | `gen_ai.operation.name` | Key Attributes |
|------|------------------------|----------------|
| Agent run | `invoke_agent` | `gen_ai.agent.name`, `gen_ai.usage.*` |
| Model request | `chat` | `gen_ai.request.model`, `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |
| Tool execution | `execute_tool` | `gen_ai.tool.name`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result` |

## Prerequisites

- Docker & Docker Compose
- An [Oodle](https://oodle.ai) account (instance ID and API key)
- An [OpenAI](https://platform.openai.com/api-keys) API key (or another supported provider)

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
   make test-chat      # simple chat with tool use
   make test-city      # structured output (CityInfo)
   make test-trip      # tool use + structured output
   make test-review    # code review (structured output)
   make test-multi     # multi-agent workflow
   ```

## API Endpoints

### POST /chat
General chat with tool access (weather, time).

### POST /city-info?city=Tokyo
Returns structured `CityInfo` with weather lookup.

### POST /plan-trip?city=Paris&days=3
Plans a trip using attraction search and weather tools.

### POST /review-code
Reviews a code snippet, returns structured `CodeReview`.

### POST /multi-agent?city=Tokyo
Runs two agents sequentially: city info feeds into trip planning.

### GET /health
Health check.

## Viewing Traces in Oodle

1. Log in to your Oodle instance
2. Navigate to **GenAI > Traces** (`/genai/traces`)
3. Filter by service name `pydantic-ai-demo`
4. Click on a trace to see:
   - **Agent run spans** (`invoke_agent`) showing the full agent workflow
   - **Model request spans** (`chat`) with prompt/response content
   - **Tool execution spans** (`execute_tool`) with arguments and results
   - **Token usage** on each model call
   - **Structured outputs** validated by Pydantic
   - **Latency breakdown** across agents, tools, and model calls

## Using a Different Model

Pydantic AI supports multiple providers. Set the `MODEL` env var:

```bash
# OpenAI
MODEL=openai:gpt-4o-mini

# Google Gemini (requires GOOGLE_API_KEY in .env)
MODEL=google:gemini-3.5-flash

# Anthropic (requires ANTHROPIC_API_KEY in .env)
MODEL=anthropic:claude-sonnet-4-20250514
```

## Cleanup

```bash
make clean
```
