# Traceloop (OpenLLMetry) Demo

LLM observability demo using [Traceloop's OpenLLMetry](https://github.com/traceloop/openllmetry) SDK to automatically instrument Google Gemini calls and export traces to Oodle.

See [OODLE_ONBOARDING.md](./OODLE_ONBOARDING.md) for Oodle-specific integration details.

## Architecture

```
User Request
     |
     v
Flask App (:8090) — instrumented with Traceloop SDK
     |
     +---> Google Gemini API (chat completions)
     |
     v
OTel Collector (OTLP :4318) --> Oodle (traces)
```

## Components

| Service | Description | Port |
|---------|-------------|------|
| app | Flask app with Traceloop SDK + Gemini | 8090 |
| otel-collector | OpenTelemetry Collector | 4319 (host) -> 4318 (container) |

## Prerequisites

- Docker & Docker Compose
- An [Oodle](https://oodle.ai) account (instance ID and API key)
- A [Google Gemini](https://aistudio.google.com/apikey) API key

## Quick Start

View available options:
```bash
make help
```

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your credentials:
   ```bash
   OODLE_INSTANCE=your-instance-id
   OODLE_API_KEY=your-api-key
   GEMINI_API_KEY=your-gemini-api-key
   ```

3. Build and start all services:
   ```bash
   make up
   ```

4. Send a test request:
   ```bash
   make test-chat
   ```

## API Endpoints

### POST /chat
Send a chat message to Gemini.

```bash
curl -s -X POST http://localhost:8090/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "What is OpenTelemetry?", "model": "gemini-flash-latest"}' | python3 -m json.tool
```

### POST /summarize
Summarize a block of text.

```bash
curl -s -X POST http://localhost:8090/summarize \
  -H 'Content-Type: application/json' \
  -d '{"text": "Long text to summarize..."}' | python3 -m json.tool
```

### GET /health
Health check.

```bash
curl -s http://localhost:8090/health
```

## Viewing Traces in Oodle

1. Log in to your Oodle instance
2. Navigate to the **Traces** section
3. Filter by service name `traceloop-demo`
4. Click on a trace to see the full span waterfall including Gemini call details

You should see:
- **Workflow spans** (`chat`, `summarize`) grouping related operations
- **Gemini call spans** with model, token usage, and latency
- **Request/response content** captured by the Traceloop SDK

## Troubleshooting

### Traces not appearing in Oodle

1. **Check OTel Collector logs for export errors:**
   ```bash
   make logs-collector
   ```

2. **Verify environment variables are set:**
   ```bash
   docker-compose config | grep OODLE
   ```

3. **Verify the Oodle endpoint is reachable:**
   ```bash
   curl -v "https://${OODLE_INSTANCE}-otlp.collector.oodle.ai/v1/traces"
   ```

### Gemini errors

- Verify your `GEMINI_API_KEY` is valid
- Check app logs: `make logs-app`

## Cleanup

Stop all services and remove volumes:
```bash
make clean
```
