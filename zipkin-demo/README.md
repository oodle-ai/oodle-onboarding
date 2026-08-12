# Zipkin Demo — Send Traces to Oodle

This demo shows how to send traces from a **Zipkin-instrumented Go service** to Oodle. Two paths are provided:

| Path | Description |
|------|-------------|
| **Via OTel Collector** | App → OTel Collector (Zipkin receiver) → Oodle (OTLP) |
| **Direct Ingestion** | App → Oodle (native Zipkin protocol, no collector needed) |

## Prerequisites

- Docker and Docker Compose
- An Oodle account with API key

## Quick Start

1. Copy the environment file and fill in your Oodle credentials:

```bash
cp .env.example .env
# Edit .env with your OODLE_INSTANCE and OODLE_API_KEY
```

### Path 1: Via OTel Collector (recommended)

```
Go Service (Zipkin JSON exporter) → OTel Collector (zipkin receiver) → Oodle
```

The Go service exports traces in Zipkin JSON format to the OTel Collector's Zipkin receiver (port 9411). The collector then forwards traces to Oodle via OTLP.

```bash
make up       # start all services
make test     # send a test request
make logs-collector  # verify traces are being exported
```

### Path 2: Direct Ingestion (no collector)

```
Go Service (Zipkin JSON exporter) → Oodle (native Zipkin endpoint)
```

The Go service sends Zipkin JSON traces directly to Oodle's Zipkin-compatible endpoint. No OTel Collector is needed.

```bash
make up-direct   # start app only (sends directly to Oodle)
make test        # send a test request
make logs-direct # view app logs
```

## Services

### Via OTel Collector

| Service | Port | Description |
|---------|------|-------------|
| app | 8080 | Go HTTP service with Zipkin exporter |
| otel-collector | 9411 | OTel Collector with Zipkin receiver |

### Direct Ingestion

| Service | Port | Description |
|---------|------|-------------|
| app | 8080 | Go HTTP service sending directly to Oodle |

## API

- `GET /health` — Health check
- `POST /order` — Create an order (generates trace with child spans)

Example:

```bash
curl -X POST http://localhost:8080/order \
  -H 'Content-Type: application/json' \
  -d '{"item":"gadget","quantity":2}'
```

## Migrating Existing Zipkin Services

If you already have services sending traces to a Zipkin collector, you can migrate to Oodle by:

**Option A — Via OTel Collector:**
1. Replace your Zipkin server with the OTel Collector (using the `zipkin` receiver)
2. Configure the OTel Collector to export to Oodle (using the `otlphttp` exporter)
3. No changes needed in your application code

**Option B — Direct Ingestion:**
1. Point your Zipkin reporter endpoint directly at Oodle's Zipkin-compatible endpoint
2. Add Oodle authentication headers (`X-API-KEY`, `X-OODLE-INSTANCE`) to the reporter's HTTP client
3. No OTel Collector deployment needed
