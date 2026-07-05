# Datadog OTel Dual-Write Demo (OTel Collector → Datadog + Oodle)

A demo that uses an **OpenTelemetry Collector** to dual-write traces, metrics, and logs to both Datadog and Oodle. This mirrors a production pattern where the app sends OTLP to a local collector sidecar, and the collector fans out to multiple backends.

## Architecture

```
┌──────────────┐       OTLP/gRPC       ┌───────────────────────┐
│  demo-app    │──────────────────────→ │  OTel Collector       │
│  (Go)        │       :4317            │                       │
│  :8080       │                        │  datadog/connector    │──→  Datadog
└──────────────┘                        │  datadog/exporter     │     (traces, metrics, logs)
                                        │  otlphttp/oodle       │──→  Oodle
                                        │  :4317, :4318, :13133 │     (traces, metrics, logs)
                                        └───────────────────────┘
```

The OTel Collector uses:
- **`datadog/connector`** — computes trace metrics (top-level span stats) and feeds them into the metrics pipeline
- **`datadog/exporter`** — sends traces, metrics, and logs to Datadog in native format
- **`otlphttp/oodle`** — sends traces, metrics, and logs to Oodle via OTLP/HTTP

## What Gets Sent (to both Datadog and Oodle)

| Signal | Description |
|--------|-------------|
| **Traces** | APM spans for `/api/order`, `/api/users` endpoints |
| **Metrics** | Trace-derived metrics via `datadog/connector` + any OTLP metrics |
| **Logs** | OTLP logs from the application |

## Prerequisites

- Docker and Docker Compose
- [Datadog account](https://www.datadoghq.com/) with an API key
- [Oodle account](https://app.oodle.ai) with API credentials

## Quick Start

1. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Datadog and Oodle credentials
   ```

2. **Start services**
   ```bash
   make up
   ```

3. **Generate traffic**
   ```bash
   make test
   ```

4. **View in Datadog**
   - [APM Traces](https://app.datadoghq.com/apm/traces) — search for `service:datadog-demo`

5. **View in Oodle**
   - Traces, metrics, and logs appear in the Oodle UI

## How It Works

The app sends OTLP telemetry to the OTel Collector over gRPC (port 4317). The collector processes all signals through `memory_limiter` and `batch` processors, then exports to both backends:

| Pipeline | Receivers | Exporters |
|----------|-----------|-----------|
| **Traces** | `otlp` | `datadog/connector`, `datadog/exporter`, `otlphttp/oodle` |
| **Metrics** | `otlp`, `datadog/connector` | `datadog/exporter`, `otlphttp/oodle` |
| **Logs** | `otlp` | `datadog/exporter`, `otlphttp/oodle` |

The `datadog/connector` bridges the traces and metrics pipelines — it receives trace data, computes top-level span statistics, and emits them as metrics consumed by the metrics pipeline.

## Endpoints

| Path | Method | Description |
|------|--------|-------------|
| `/health` | GET | Health check |
| `/api/order` | POST | Create order (simulated, ~10% error rate) |
| `/api/users` | GET | List users |

## Cleanup

```bash
make clean
```
