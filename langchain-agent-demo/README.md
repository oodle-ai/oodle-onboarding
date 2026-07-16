# LangChain Agent Demo

Agent observability demo using [LangChain](https://python.langchain.com/) and [LangGraph](https://langchain-ai.github.io/langgraph/) with OpenTelemetry instrumentation, exporting traces to Oodle via an OTel Collector.

Uses [opentelemetry-instrumentation-langchain](https://github.com/traceloop/openllmetry/tree/main/packages/opentelemetry-instrumentation-langchain) (from OpenLLMetry) to auto-instrument all LangChain and LangGraph operations — one call to `LangchainInstrumentor().instrument()` traces chains, LLM calls, tools, and retrievers.

## Architecture

```
User Request
     |
     v
FastAPI App (:8092) — LangGraph ReAct agents with OTel instrumentation
     |
     +---> LLM API (OpenAI)
     |
     v
OTel Collector (OTLP :4318) --> Oodle (traces)
```

## What Gets Traced

The OpenLLMetry instrumentation emits spans for:

| Span | Key Attributes |
|------|----------------|
| LangChain task | `traceloop.entity.name`, workflow context |
| Chat model call | `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |
| Tool execution | tool name, arguments, result |
| LangGraph agent step | agent state transitions, tool calls |

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
   make test-chat      # simple chat with tool use
   make test-trip      # ReAct agent: plan trip with tools
   make test-research  # multi-tool research agent
   make test-multi     # multi-agent workflow
   ```

## API Endpoints

### POST /chat
General chat with tool access (weather, time). The ReAct agent decides when to call tools.

### POST /plan-trip?city=Paris&days=3&style=moderate
Plans a trip using a ReAct agent that searches attractions, checks weather, and estimates budget.

### POST /research?city=Tokyo
Researches a city using multiple tools (attractions by category, weather, time).

### POST /multi-agent?city=Tokyo
Runs two agents sequentially: a research agent gathers information, then a travel agent plans the trip based on those findings.

### GET /health
Health check.

## Viewing Traces in Oodle

1. Log in to your Oodle instance
2. Navigate to **GenAI > Traces** (`/genai/traces`)
3. Filter by service name `langchain-agent-demo`
4. Click on a trace to see:
   - **Agent workflow spans** showing the full ReAct loop
   - **LLM call spans** with prompt/response content and token usage
   - **Tool execution spans** with arguments and results
   - **Multi-agent handoffs** in the multi-agent endpoint
   - **Latency breakdown** across reasoning steps, tool calls, and LLM requests

## Using a Different Model

Set the `MODEL` env var in `.env`:

```bash
# Google Gemini (default)
MODEL=gemini-2.5-flash

# OpenAI GPT-4o
MODEL=gpt-4o
```

## Cleanup

```bash
make clean
```
