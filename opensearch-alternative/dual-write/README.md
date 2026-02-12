# OpenSearch Dual Write Setup

A complete logging stack with a Go application emitting structured logs to OpenSearch using different log collection agents.

**NEW**: Now supports dual-write to Oodle! See [OODLE_ONBOARDING.md](./OODLE_ONBOARDING.md) for setup instructions.

## Components

- **demo-app**: Go application that emits structured JSON logs
- **opensearch**: Search and analytics engine for storing logs
- **opensearch-dashboards**: Web UI for visualizing logs
- **Agent** (choose one):
  - **fluent-bit**: Lightweight log forwarder and processor
  - **vector**: High-performance observability data pipeline
  - **otel-collector**: OpenTelemetry Collector for logs, metrics, and traces

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

- **OpenSearch API**: http://localhost:9200
- **OpenSearch Dashboards**: http://localhost:5601

## Agent Comparison

### Fluent Bit
- **Approach**: Docker fluentd logging driver
- **Use case**: Lightweight, low memory footprint
- **Config**: `agents/fluent-bit/fluent-bit.conf`
- **Best for**: Simple log forwarding with minimal overhead

### Vector
- **Approach**: Reads Docker container logs via socket
- **Use case**: High-performance data transformation
- **Config**: `agents/vector/vector.yaml`
- **Best for**: Complex log transformations and routing

### OpenTelemetry Collector
- **Approach**: TCP receiver for direct log shipping
- **Use case**: Unified observability (logs, metrics, traces)
- **Config**: `agents/otel/otel-collector-config.yaml`
- **Best for**: Full observability stack with OTel ecosystem

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

## Viewing Logs in OpenSearch Dashboards

1. Open http://localhost:5601
2. Go to "Management" → "Index Patterns"
3. Create an index pattern with `logs*`
4. Go to "Discover" to view and search logs

## Architecture

### Fluent Bit Flow
```
demo-app → fluentd driver → fluent-bit → opensearch → dashboards
```

### Vector Flow
```
demo-app → docker logs → vector → opensearch → dashboards
```

### OpenTelemetry Flow
```
demo-app → TCP → otel-collector → opensearch → dashboards
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
