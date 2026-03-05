# Oodle Tracing Onboarding Guide

This guide documents how the distributed tracing demo sends traces to Oodle via the OpenTelemetry Collector.

## Overview

The tracing demo runs multi-language microservices (Go, Java, Python) that are instrumented with OpenTelemetry. All services export traces to a central OTel Collector, which forwards them to Oodle for visualization and analysis.

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ frontend-api │  │ java-service │  │python-service│  │  go-service  │
│   (Go)       │  │   (Java)     │  │  (Python)    │  │   (Go)       │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │                 │
       └────────┬────────┴────────┬────────┘                 │
                │    OTLP gRPC    │                          │
                └────────┬────────┘──────────────────────────┘
                         │
                ┌────────▼────────┐
                │  OTel Collector │
                │  (batch + export│
                └───┬─────────┬───┘
                    │         │
            ┌───────▼──┐  ┌──▼──────────┐
            │  Debug   │  │   Oodle     │
            │ (stdout) │  │  (Traces)   │
            └──────────┘  └─────────────┘
```

## Prerequisites

1. **Oodle Instance and API Key**
   - Login to Oodle UI
   - Navigate to: Settings → API Keys
   - Note your `OODLE_INSTANCE` ID
   - Create or copy an existing `OODLE_API_KEY`

## Setup Instructions

### Step 1: Configure Environment Variables

1. Create a `.env` file in the `tracing-demo` directory:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your Oodle credentials:
   ```bash
   OODLE_INSTANCE=your-instance-id
   OODLE_API_KEY=your-api-key
   ```

### Step 2: Start Services

```bash
make up
```

This builds and starts all services including the OTel Collector and load generator. Traces begin flowing to Oodle automatically.

### Step 3: Verify Traces

1. **Check the OTel Collector debug output** (traces should appear in stdout):
   ```bash
   make logs-collector
   ```

2. **Check Oodle UI**:
   - Login to your Oodle instance
   - Navigate to the Traces section
   - You should see traces with service names:
     - `frontend-api`
     - `java-service`
     - `python-service`
     - `go-service`

## Configuration Changes

### OTel Collector (`otel-collector-config.yaml`)

The collector is configured with a traces pipeline: **receivers → processors → exporters**.

**Receivers** — accepts OTLP over both gRPC and HTTP:
```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: "0.0.0.0:4318"
      grpc:
        endpoint: "0.0.0.0:4317"
```

**Processors** — batches spans before export:
```yaml
processors:
  batch:
    timeout: 5s
    send_batch_size: 512
```

**Exporters** — sends traces to Oodle and debug output:
```yaml
exporters:
  # Oodle
  otlphttp/oodle:
    traces_endpoint: "https://${OODLE_INSTANCE}.collector.oodle.ai/v1/otlp/traces"
    headers:
      "X-OODLE-INSTANCE": "${OODLE_INSTANCE}"
      "X-API-KEY": "${OODLE_API_KEY}"

  # Debug/logging for local development (prints traces to collector stdout)
  debug:
    verbosity: basic
```

**Pipeline** — wires receivers, processors, and exporters together:
```yaml
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/oodle, debug]
```

### Docker Compose (`docker-compose.yml`)

The OTel Collector service receives the Oodle credentials via environment variables:
```yaml
otel-collector:
  image: otel/opentelemetry-collector-contrib:0.114.0
  volumes:
    - ./otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml
  ports:
    - "4317:4317"
    - "4318:4318"
  environment:
    - OODLE_INSTANCE=${OODLE_INSTANCE}
    - OODLE_API_KEY=${OODLE_API_KEY}
```

Each service sends traces to the collector via the `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable pointing at `otel-collector:4317`.

## What to Expect in Oodle

Once traces are flowing, you should see:

- **Service names**: `frontend-api`, `java-service`, `python-service`, `go-service`
- **Trace topology**: Visual map showing request flow from frontend-api → java-service / go-service → python-service
- **Span details** with custom attributes:
  - `order.item`, `order.quantity` (frontend-api)
  - `order.status` (java-service)
  - `inventory.item`, `inventory.in_stock`, `inventory.quantity` (python-service)
  - `pricing.item`, `pricing.price`, `pricing.currency` (python-service)
  - `billing.total`, `billing.currency` (go-service)
- **Cross-language trace propagation**: Each trace spans Go, Java, and Python services with consistent trace IDs

## Troubleshooting

### Traces not appearing in Oodle

1. **Verify environment variables are set:**
   ```bash
   docker-compose config | grep OODLE
   ```

2. **Check collector logs for export errors:**
   ```bash
   make logs-collector
   ```
   Look for `exporter/otlphttp` error messages indicating authentication or connectivity issues.

3. **Verify the Oodle endpoint is reachable:**
   ```bash
   curl -v "https://${OODLE_INSTANCE}.collector.oodle.ai/v1/otlp/traces"
   ```

### Authentication errors

- Double-check your `OODLE_INSTANCE` and `OODLE_API_KEY` values in `.env`
- Ensure the API key has permissions for trace ingestion
- Generate a new API key from Oodle UI (Settings → API Keys) if needed

### Debug exporter shows traces but Oodle doesn't

This means the services and collector are working correctly but the Oodle export is failing:
1. Check for HTTP 401/403 errors in collector logs (authentication issue)
2. Check for HTTP 4xx/5xx errors (endpoint or payload issue)
3. Ensure your `OODLE_INSTANCE` value is correct — it forms part of the endpoint URL

## References

- [Oodle OpenTelemetry Integration](https://docs.oodle.ai/integrations/traces/otel)
- [OpenTelemetry Collector Documentation](https://opentelemetry.io/docs/collector/)
- [OpenTelemetry Instrumentation Guides](https://opentelemetry.io/docs/instrumentation/)
