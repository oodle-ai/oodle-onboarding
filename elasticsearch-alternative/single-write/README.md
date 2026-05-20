# Elasticsearch Single-Write Setup

This setup runs a local Elasticsearch stack with a demo application that writes logs only to Elasticsearch. Use this as the baseline before migrating to Oodle with the dual-write setup.

## Components

- **demo-app**: Go application that emits structured JSON logs (shared with dual-write)
- **elasticsearch**: Local Elasticsearch instance
- **kibana**: Web UI for verifying logs land correctly
- **Agent** (choose one):
  - **fluent-bit**: Lightweight log forwarder and processor
  - **vector**: High-performance observability data pipeline
  - **otel-collector**: OpenTelemetry Collector with direct Elasticsearch export

## Quick Start

```bash
make up                    # Start with Fluent Bit (default)
make up AGENT=vector       # Start with Vector
make up AGENT=otel         # Start with OpenTelemetry
```

View logs:
```bash
make logs           # All services
make logs-app       # Application only
make logs-agent     # Current agent only
```

Stop services:
```bash
make down           # Stop all
make clean          # Stop and remove volumes
```

## Access Points

- **Elasticsearch API**: http://localhost:9200
- **Kibana**: http://localhost:5601

## Viewing Logs in Kibana

1. Open http://localhost:5601
2. Go to "Stack Management" -> "Data Views"
3. Create a data view with pattern `logs*`
4. Go to "Discover" to view and search logs

## Architecture

### Fluent Bit Flow
```
demo-app -> fluentd driver -> fluent-bit -> elasticsearch
```

### Vector Flow
```
demo-app -> docker logs -> vector -> elasticsearch
```

### OpenTelemetry Flow
```
demo-app -> OTel SDK -> otel-collector -> elasticsearch
```
