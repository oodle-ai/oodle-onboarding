# Langfuse Demo — Dual Trace Export to Langfuse + Oodle

Demonstrates the Langfuse Python SDK v4 sending traces to **both** Langfuse and Oodle simultaneously. Every LLM span appears in both backends — Langfuse for LLM-specific observability (generations, token counts, cost tracking) and Oodle for full-stack distributed tracing.

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                        FastAPI App (:8093)                        │
│                                                                   │
│  TracerProvider                                                   │
│  ├── LangfuseSpanProcessor ──► Langfuse (Cloud or :3000)         │
│  └── BatchSpanProcessor    ──► OTel Collector (:4318) ──► Oodle  │
│                                                                   │
│  google-genai (Gemini) — auto-instrumented with gen_ai.* attrs   │
└───────────────────────────────────────────────────────────────────┘
```

A single `TracerProvider` holds two span processors:

| Processor | Destination | What it sends |
|-----------|-------------|---------------|
| `LangfuseSpanProcessor` | Langfuse (cloud or self-hosted) | `gen_ai.*` spans (LLM generations, agent steps) |
| `BatchSpanProcessor(OTLP)` | OTel Collector → Oodle | All spans (HTTP, LLM, custom) |

## Prerequisites

- Docker and Docker Compose
- [Oodle](https://oodle.ai) account (instance ID + API key)
- [Google Gemini](https://aistudio.google.com/apikey) API key
- Langfuse account: either [Langfuse Cloud](https://cloud.langfuse.com) **or** use the self-hosted option below

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 2a. With Langfuse Cloud (simpler — 2 containers)

Set your Langfuse Cloud API keys in `.env`:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com  # or https://us.cloud.langfuse.com
```

```bash
make up
```

### 2b. With Self-Hosted Langfuse (fully self-contained — 8 containers)

For the self-hosted option, the Langfuse init env vars auto-create the org, project, and API keys. Set these in `.env`:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-demo-public-key
LANGFUSE_SECRET_KEY=sk-lf-demo-secret-key
LANGFUSE_BASE_URL=http://langfuse-web:3000
```

```bash
make up-full
```

Langfuse UI is available at http://localhost:3060 (takes ~2-3 minutes to initialize).  
Login: `demo@langfuse.local` / `demo-password`

### 3. Run test requests

```bash
make test-all
```

## API Endpoints

| Endpoint | Method | Description | Trace Shape |
|----------|--------|-------------|-------------|
| `/health` | GET | Health check | — |
| `/chat` | POST | Simple Gemini chat | Single LLM generation |
| `/summarize` | POST | Text summarization | Single LLM generation |
| `/multi-step` | POST | Multi-step agent: classify → research → synthesize | 3 nested agent spans, each with an LLM call |
| `/safe-chat` | POST | Validated chat: input_validator → response_generator | 2-agent pipeline with guardrail |

### Example requests

```bash
# Chat
curl -s -X POST http://localhost:8093/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is OpenTelemetry?"}' | python3 -m json.tool

# Multi-step workflow
curl -s -X POST http://localhost:8093/multi-step \
  -H 'Content-Type: application/json' \
  -d '{"message": "Compare Redis vs Memcached for caching"}' | python3 -m json.tool

# Safe chat (with validation)
curl -s -X POST http://localhost:8093/safe-chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "What are REST API security best practices?"}' | python3 -m json.tool
```

## Viewing Traces

### In Langfuse

- **Cloud**: Go to https://cloud.langfuse.com → your project → Traces
- **Self-hosted**: Go to http://localhost:3060 → Traces

Langfuse shows LLM-specific details: model, token usage, cost, input/output messages, and latency for each generation.

### In Oodle

Go to your Oodle instance → GenAI → Traces. Filter by `service.name = langfuse-demo`.

Oodle shows the full distributed trace with `gen_ai.*` span attributes: `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.agent.name`, etc.

## How the Dual Export Works

The Langfuse Python SDK v4 is built on OpenTelemetry. When initialized, it registers a `LangfuseSpanProcessor` that captures spans with `gen_ai.*` attributes and sends them to the Langfuse backend.

This demo creates a shared `TracerProvider` **before** initializing Langfuse, adding both the Langfuse processor and a standard OTLP exporter:

```python
provider = TracerProvider(resource=Resource.create({"service.name": "langfuse-demo"}))
provider.add_span_processor(LangfuseSpanProcessor())      # → Langfuse
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))  # → Collector → Oodle
trace.set_tracer_provider(provider)
```

Every span is processed by both. The `LangfuseSpanProcessor` applies a smart filter (only `gen_ai.*` and Langfuse SDK spans), while the OTLP exporter sends everything.

## Makefile Reference

| Target | Description |
|--------|-------------|
| `make up` | Start app + collector (Langfuse Cloud mode) |
| `make up-full` | Start all services including self-hosted Langfuse |
| `make down` | Stop all services |
| `make clean` | Stop and remove volumes |
| `make logs` | View all logs |
| `make logs-app` | View app logs |
| `make logs-collector` | View collector logs |
| `make logs-langfuse` | View Langfuse logs |
| `make test-chat` | Chat with Gemini |
| `make test-summarize` | Summarize text |
| `make test-multi-step` | Multi-step agent workflow |
| `make test-safe-chat` | Chat with input validation |
| `make test-all` | Run all test targets |
| `make status` | Show service status |

## Troubleshooting

**Traces not appearing in Langfuse?**
- Verify `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` are correct
- For self-hosted: ensure Langfuse is healthy (`make logs-langfuse`)
- Check app logs: `make logs-app`

**Traces not appearing in Oodle?**
- Verify `OODLE_INSTANCE` and `OODLE_API_KEY` in `.env`
- Check collector logs: `make logs-collector`
- Ensure the collector health endpoint responds: `curl http://localhost:13137/`

**Self-hosted Langfuse slow to start?**
- First startup takes 2-3 minutes for database migrations
- Wait for "Ready" in `make logs-langfuse` before testing
