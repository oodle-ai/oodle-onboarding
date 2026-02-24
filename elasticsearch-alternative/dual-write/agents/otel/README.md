# OpenTelemetry Collector with Elasticsearch

Production-grade telemetry collection using OpenTelemetry SDK instrumentation and OTel Collector with direct Elasticsearch export.

## Architecture

```
demo-app (OTel SDK) -> OTel Collector (OTLP:4318) -> Elasticsearch
```

## Configuration Files

**otel-collector-config.yaml**:
- **Receiver**: OTLP receiver (HTTP: 4318, gRPC: 4317)
- **Processor**: Batch processor for efficiency
- **Exporter**: Elasticsearch exporter (direct to Elasticsearch, no intermediary needed)

## How It Works

1. Demo app uses OpenTelemetry Go SDK to emit structured logs
2. SDK exports logs via OTLP HTTP to OTel Collector (port 4318)
3. OTel Collector batches logs and exports directly to Elasticsearch via the `elasticsearch` exporter

## Why This Approach?

**OpenTelemetry SDK**:
- Industry-standard instrumentation
- Automatic context propagation (traces, spans)
- Rich metadata (SDK version, language, etc.)
- Reliable connection handling with retries

**Direct Elasticsearch Export**:
- The `elasticsearchexporter` in otel-collector-contrib writes directly to Elasticsearch
- No intermediary (like Data Prepper) needed
- Simpler architecture with fewer moving parts

## Log Structure

Logs in Elasticsearch include:
- `@timestamp`: Timestamp for Kibana time queries
- `body`: The log message
- `severityText`: Log level (INFO, DEBUG, WARN, ERROR)
- `log.attributes.*`: Custom attributes (service, request_id, duration_ms, user_id)
- `resource.attributes.*`: SDK metadata (language, SDK version)
- `instrumentationScope.name`: Logger name

## Resource Usage

- OTel Collector Memory: ~100-200 MB
- CPU: Moderate
- Best for: Full observability stack with OpenTelemetry instrumentation

## Production Recommendations

- Enable TLS for all connections
- Configure resource attributes (service.name, deployment.environment)
- Add processors for sensitive data filtering
- Use sampling strategies for high-volume applications
- Configure proper retry and backoff policies
- Set up health checks and monitoring for the pipeline
