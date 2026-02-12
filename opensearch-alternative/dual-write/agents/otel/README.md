# OpenTelemetry Collector with Data Prepper

Vendor-agnostic telemetry collection and processing using OpenTelemetry Collector and OpenSearch Data Prepper.

## Architecture

```
demo-app → OTel Collector (TCP:54525) → Data Prepper (OTLP:21892) → OpenSearch
```

## Configuration Files

**otel-collector-config.yaml**:
- **Receiver**: tcplog receiver (port 54525) with JSON parser
- **Processor**: Batch processor for efficiency
- **Exporter**: OTLP exporter sending to Data Prepper

**pipelines.yaml** (Data Prepper):
- **Source**: otel_logs_source (receives OTLP logs on port 21892)
- **Sink**: OpenSearch sink (writes to `logs` index)

**data-prepper.yaml**:
- Basic Data Prepper configuration with SSL disabled

## How It Works

1. Demo app sends JSON logs via TCP to OTel Collector (port 54525)
2. OTel Collector parses JSON and batches logs
3. OTel Collector exports via OTLP to Data Prepper (port 21892)
4. Data Prepper receives OTLP logs and writes to OpenSearch

## Why Data Prepper?

Data Prepper acts as an intermediary because:
- OTel's native Elasticsearch exporter doesn't support OpenSearch
- Data Prepper has native OpenSearch support and optimizations
- Provides additional transformation capabilities if needed

## Features

- Part of OpenTelemetry standard
- Supports logs, metrics, and traces
- Extensive ecosystem of receivers and exporters
- Vendor-neutral collection with OpenSearch-optimized ingestion

## Resource Usage

- OTel Collector Memory: ~100-200 MB
- Data Prepper Memory: ~512 MB
- CPU: Moderate
- Best for: Full observability stack with OpenTelemetry instrumentation

## Known Limitations

The demo-app uses a persistent TCP connection which can occasionally break, causing log flow to stop until the app restarts. In production:
- Use proper OTLP instrumentation libraries instead of raw TCP
- Enable TLS for secure transmission
- Add additional processors for enrichment and filtering
- Configure retry and backoff strategies
