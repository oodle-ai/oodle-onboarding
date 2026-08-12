# Jaeger Demo — Send Traces to Oodle

This demo shows how to send traces from a **Jaeger-instrumented Go service** to Oodle. Two paths are provided:

| Path | Description |
|------|-------------|
| **Via OTel Collector** | App → OTel Collector (Jaeger receiver) → Oodle (OTLP) |
| **Direct Ingestion** | App → Oodle (native Jaeger protocol, no collector needed) |

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
Go Service (Jaeger Thrift exporter) → OTel Collector (jaeger receiver) → Oodle
```

The Go service exports traces in Jaeger Thrift format to the OTel Collector's Jaeger receiver (port 14268). The collector then forwards traces to Oodle via OTLP.

```bash
make up       # start all services
make test     # send a test request
make logs-collector  # verify traces are being exported
```

### Path 2: Direct Ingestion (no collector)

```
Go Service (Jaeger Thrift exporter) → Oodle (native Jaeger endpoint)
```

The Go service sends Jaeger Thrift traces directly to Oodle's Jaeger-compatible endpoint. No OTel Collector is needed.

```bash
make up-direct   # start app only (sends directly to Oodle)
make test        # send a test request
make logs-direct # view app logs
```

## Services

### Via OTel Collector

| Service | Port | Description |
|---------|------|-------------|
| app | 8080 | Go HTTP service with Jaeger exporter |
| otel-collector | 14268 | OTel Collector with Jaeger receiver |

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
  -d '{"item":"widget","quantity":3}'
```

## Migrating Existing Jaeger Services

If you already have services sending traces to a Jaeger collector, you can migrate to Oodle by:

**Option A — Via OTel Collector:**
1. Replace your Jaeger collector with the OTel Collector (using the `jaeger` receiver)
2. Configure the OTel Collector to export to Oodle (using the `otlphttp` exporter)
3. No changes needed in your application code

**Option B — Direct Ingestion:**
1. Point your Jaeger client endpoint directly at Oodle's Jaeger-compatible endpoint
2. Add Oodle authentication headers (`X-API-KEY`, `X-OODLE-INSTANCE`) to the exporter's HTTP client
3. No OTel Collector deployment needed
