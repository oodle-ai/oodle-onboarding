# OpenTelemetry Collector with Data Prepper

Production-grade telemetry collection using OpenTelemetry SDK instrumentation, OTel Collector, and OpenSearch Data Prepper.

## Architecture

```
demo-app (OTel SDK) → OTel Collector (OTLP:4318) → Data Prepper (OTLP:21892) → OpenSearch
```

## Configuration Files

**otel-collector-config.yaml**:
- **Receiver**: OTLP receiver (HTTP: 4318, gRPC: 4317)
- **Processor**: Batch processor for efficiency
- **Exporter**: OTLP exporter sending to Data Prepper

**pipelines.yaml** (Data Prepper):
- **Source**: otel_logs_source (receives OTLP logs on port 21892)
- **Processor**: rename_keys (copies observedTime to @timestamp for Dashboards)
- **Sink**: OpenSearch sink (writes to `logs` index)

**data-prepper.yaml**:
- Basic Data Prepper configuration with SSL disabled

## How It Works

1. Demo app uses OpenTelemetry Go SDK to emit structured logs
2. SDK exports logs via OTLP HTTP to OTel Collector (port 4318)
3. OTel Collector batches logs and forwards via OTLP to Data Prepper (port 21892)
4. Data Prepper processes logs (adds @timestamp) and writes to OpenSearch

## Why This Approach?

**OpenTelemetry SDK**:
- Industry-standard instrumentation
- Automatic context propagation (traces, spans)
- Rich metadata (SDK version, language, etc.)
- Reliable connection handling with retries

**Data Prepper**:
- Native OpenSearch support (OTel's Elasticsearch exporter doesn't work with OpenSearch)
- Optimized for OpenSearch ingestion
- Powerful data transformation capabilities

## Log Structure

Logs in OpenSearch include:
- `@timestamp`: Timestamp for Dashboards time queries
- `body`: The log message
- `severityText`: Log level (INFO, DEBUG, WARN, ERROR)
- `log.attributes.*`: Custom attributes (service, request_id, duration_ms, user_id)
- `resource.attributes.*`: SDK metadata (language, SDK version)
- `instrumentationScope.name`: Logger name

## Features

- ✅ Production-ready OpenTelemetry SDK instrumentation
- ✅ OTLP protocol (HTTP and gRPC)
- ✅ Reliable connection handling with automatic retries
- ✅ Rich structured logging with custom attributes
- ✅ Full OpenTelemetry ecosystem compatibility
- ✅ OpenSearch Dashboards compatible (@timestamp field)

## Resource Usage

- OTel Collector Memory: ~100-200 MB
- Data Prepper Memory: ~512 MB
- CPU: Moderate
- Best for: Full observability stack with OpenTelemetry instrumentation

## Production Recommendations

- Enable TLS for all connections
- Configure resource attributes (service.name, deployment.environment)
- Add processors for sensitive data filtering
- Use sampling strategies for high-volume applications
- Configure proper retry and backoff policies
- Set up health checks and monitoring for the pipeline
