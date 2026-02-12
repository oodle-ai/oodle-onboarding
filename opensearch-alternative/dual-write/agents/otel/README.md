# OpenTelemetry Collector

Vendor-agnostic telemetry collection and processing.

## Configuration

**otel-collector-config.yaml** contains:
- **Receiver**: TCP log receiver (port 54525)
- **Processor**: Batch processor for efficiency
- **Exporter**: OpenSearch exporter

## How It Works

1. Demo app sends logs directly via TCP to OTel Collector
2. OTel batches the logs
3. Exports to OpenSearch

## Features

- Part of OpenTelemetry standard
- Supports logs, metrics, and traces
- Extensive ecosystem of receivers and exporters
- Vendor-neutral

## Resource Usage

- Memory: ~100-200 MB
- CPU: Moderate
- Best for: Full observability stack with OpenTelemetry instrumentation

## Note

This setup uses TCP receiver for simplicity. In production, consider:
- OTLP protocol for full OTel support
- TLS for secure transmission
- Additional processors for enrichment
