# Jaeger Demo — Send Traces to Oodle

This demo shows how to send traces from a **Jaeger-instrumented Go service** to Oodle using an OpenTelemetry Collector with the Jaeger receiver.

## Architecture

```
Go Service (Jaeger Thrift exporter) → OTel Collector (jaeger receiver) → Oodle
```

The Go service exports traces in Jaeger Thrift format to the OTel Collector's Jaeger receiver (port 14268). The collector then forwards traces to Oodle via OTLP.

## Prerequisites

- Docker and Docker Compose
- An Oodle account with API key

## Quick Start

1. Copy the environment file and fill in your Oodle credentials:

```bash
cp .env.example .env
# Edit .env with your OODLE_INSTANCE and OODLE_API_KEY
```

2. Start the services:

```bash
make up
```

3. Send a test request:

```bash
make test
```

4. Check the collector logs to verify traces are being exported:

```bash
make logs-collector
```

5. View your traces in the Oodle UI.

## Services

| Service | Port | Description |
|---------|------|-------------|
| app | 8080 | Go HTTP service with Jaeger exporter |
| otel-collector | 14268 | OTel Collector with Jaeger receiver |

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

1. Replacing your Jaeger collector with the OTel Collector (using the `jaeger` receiver)
2. Configuring the OTel Collector to export to Oodle (using the `otlphttp` exporter)
3. No changes needed in your application code
