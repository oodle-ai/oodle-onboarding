# OpenSearch Dual Write Setup

A complete logging stack with a Go application emitting structured logs to OpenSearch.

## Components

- **demo-app**: Go application that emits structured JSON logs
- **fluent-bit**: Log collector that forwards logs to OpenSearch
- **opensearch**: Search and analytics engine for storing logs
- **opensearch-dashboards**: Web UI for visualizing logs

## Quick Start

Using Makefile:
```bash
make up       # Start all services in background
make logs     # View all logs
make logs-app # View only app logs
make down     # Stop all services
make clean    # Stop and remove volumes
make restart  # Restart all services
```

Using docker-compose directly:
```bash
# Start all services
docker-compose up --build

# Start in detached mode
docker-compose up --build -d

# View logs
docker-compose logs -f demo-app

# Stop all services
docker-compose down

# Remove volumes (clean state)
docker-compose down -v
```

## Access Points

- **OpenSearch API**: http://localhost:9200
- **OpenSearch Dashboards**: http://localhost:5601

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

```
demo-app → stdout → fluent-bit → opensearch → opensearch-dashboards
```

- Demo app writes JSON logs to stdout
- Docker logging driver forwards to Fluent Bit
- Fluent Bit parses and sends to OpenSearch
- OpenSearch Dashboards provides visualization
