# Migrating from Elasticsearch

This setup demonstrates how to migrate away from Elasticsearch to Oodle. It spins up a local Elasticsearch stack with a demo application, so you can see how existing log pipelines can be redirected to Oodle with minimal configuration changes.

See [OODLE_ONBOARDING.md](./OODLE_ONBOARDING.md) for dual-write setup instructions.

## Components

- **demo-app**: Go application that emits structured JSON logs
- **elasticsearch**: Local Elasticsearch instance (the system you're migrating away from)
- **kibana**: Web UI for verifying logs land correctly
- **Agent** (choose one):
  - **fluent-bit**: Lightweight log forwarder and processor
  - **vector**: High-performance observability data pipeline
  - **otel-collector**: OpenTelemetry Collector with direct Elasticsearch export
  - **logstash**: Classic ELK stack log processing pipeline

## Quick Start

View available options:
```bash
make help
```

Start with Fluent Bit (default):
```bash
make up
# or explicitly
make up AGENT=fluent-bit
```

Start with Vector:
```bash
make up AGENT=vector
```

Start with OpenTelemetry Collector:
```bash
make up AGENT=otel
```

Start with Logstash:
```bash
make up AGENT=logstash
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

## Agent Comparison

Each agent shows a different migration path from Elasticsearch to Oodle. Pick the one that matches your existing pipeline.

### Fluent Bit
- **Approach**: Docker fluentd logging driver
- **Config**: `agents/fluent-bit/fluent-bit.conf`
- **Migration**: Add an Oodle HTTP output alongside the existing Elasticsearch output

### Vector
- **Approach**: Reads Docker container logs via socket
- **Config**: `agents/vector/vector.yaml`
- **Migration**: Add an Oodle HTTP sink alongside the existing Elasticsearch sink

### OpenTelemetry Collector
- **Approach**: OTel SDK instrumentation with direct Elasticsearch export
- **Config**: `agents/otel/otel-collector-config.yaml`
- **Migration**: Add an Oodle OTLP exporter alongside the existing Elasticsearch exporter

### Logstash
- **Approach**: Docker GELF logging driver with Logstash pipeline
- **Config**: `agents/logstash/pipeline.conf`
- **Migration**: Add an Oodle HTTP output alongside the existing Elasticsearch output

## Log Structure

The demo app emits JSON logs with the following structure:

```json
{
  "timestamp": "2024-02-12T10:30:45Z",
  "level": "INFO",
  "message": "Processing user request",
  "service": "demo-app",
  "log": {
    "request_id": "abc123",
    "duration_ms": 245,
    "user_id": 42
  }
}
```

## Viewing Logs in Kibana

1. Open http://localhost:5601
2. Go to "Stack Management" -> "Data Views"
3. Create a data view with pattern `logs*`
4. Go to "Discover" to view and search logs

## Architecture

### Fluent Bit Flow
```
demo-app -> fluentd driver -> fluent-bit -> elasticsearch
                                         -> oodle (dual-write)
```

### Vector Flow
```
demo-app -> docker logs -> vector -> elasticsearch
                                  -> oodle (dual-write)
```

### OpenTelemetry Flow
```
demo-app -> OTel SDK -> otel-collector -> elasticsearch
                                       -> oodle (dual-write)
```

### Logstash Flow
```
demo-app -> GELF driver -> logstash -> elasticsearch
                                    -> oodle (dual-write)
```

## Switching Agents

To switch between agents:

```bash
# Stop current setup
make down

# Start with different agent
make up AGENT=vector
```

Or use restart:
```bash
make restart AGENT=otel
```
