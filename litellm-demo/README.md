# LiteLLM Demo

LLM observability demo using [LiteLLM](https://litellm.ai), which
routes one call to whichever provider the model names and emits
GenAI spans for all of them, exporting traces to Oodle via an OTel
Collector.

Turning it on is one line: `litellm.callbacks = ["otel"]`. LiteLLM
builds its own tracer provider from the `OTEL_EXPORTER_OTLP_*`
environment, so there is no OpenTelemetry SDK setup in the app.

## Architecture

```
POST /chat | POST /tool-call
     |
     v
FastAPI app (:8096) — LiteLLM with the otel callback
     |
     +---> OpenAI, Anthropic, Gemini, ... (whichever MODEL names)
     |
     v
OTel Collector (OTLP :4318) --> Oodle (traces + logs)
```

## What Gets Traced

| Span | `gen_ai.operation.name` | Key Attributes |
|------|------------------------|----------------|
| Model request | `chat` | `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.provider.name`, `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.usage.*` |

## Four environment settings carry this integration

LiteLLM has no code hook for any of them, and each fails quietly.
They are set in `docker-compose.yml`:

| Variable | Why |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Where spans go. LiteLLM infers the OTLP HTTP exporter from it, so no protocol variable is needed. |
| `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` | Without it the span is named `litellm_request` and carries no `gen_ai.operation.name`, which is the attribute the Agent Observability traces list filters on. The run arrives and is never listed. |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_and_event` | `true` means events only to LiteLLM, which leaves the span attributes empty. |
| `OTEL_SERVICE_NAME=litellm-demo` | LiteLLM takes no resource in code, so this is the only way to name the service. It defaults to `litellm`. |

`requirements.txt` also names `opentelemetry-sdk` and the OTLP
exporter: `pip install litellm` brings neither, the callback then
fails to start, and LiteLLM logs one **non-blocking** error and
keeps serving traffic. The app looks healthy and sends nothing.

## Prerequisites

- Docker & Docker Compose
- An [Oodle](https://oodle.ai) account (instance ID and API key)
- An API key for the provider your `MODEL` names

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
One completion, no tools.

### POST /tool-call
Two completions around one local tool execution.

### GET /health
Health check.

## Viewing Traces in Oodle

1. Log in to your Oodle instance
2. Navigate to **Agent Observability > Traces** (`/genai/traces`)
3. Filter by service name `litellm-demo`
4. Click a trace to see the provider, model, token usage, cost, and
   the prompt and response content

## Using a Different Provider

`MODEL` takes a LiteLLM model string, and the matching provider key
must be in `.env`:

```bash
MODEL=gpt-4o-mini                            # OPENAI_API_KEY
MODEL=anthropic/claude-sonnet-4-20250514     # ANTHROPIC_API_KEY
MODEL=gemini/gemini-2.0-flash                # GOOGLE_API_KEY
```

Switching providers changes `gen_ai.provider.name` on the span and
nothing else about the setup, which is the point of routing through
LiteLLM.

The LiteLLM Proxy takes the same callback in `config.yaml`:

```yaml
litellm_settings:
  callbacks: ["otel"]
```

## Cleanup

```bash
make clean
```
