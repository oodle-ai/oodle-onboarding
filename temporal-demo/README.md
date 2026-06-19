# Temporal Demo

Self-hosted [Temporal](https://temporal.io) with an order processing workflow in Python, fully instrumented with OpenTelemetry. Exports metrics, traces, and logs to Oodle via an OTel Collector.

See [OODLE_ONBOARDING.md](./OODLE_ONBOARDING.md) for Oodle-specific integration details.

## Architecture

```
Starter (load gen)
     |
     | start workflows (gRPC :7233)
     v
Temporal Server (:7233) <---> PostgreSQL (:5432)
     |  :8080 Web UI
     |  :8000 Prometheus metrics
     v
Worker (Python) — OTel TracingInterceptor + structured logs
     |
     +---> validate_order
     +---> process_payment
     +---> ship_order
     +---> send_notification
     |
     v
OTel Collector (:4317 gRPC, :4318 HTTP)
     |
     +--- prometheus receiver (scrapes Temporal server :8000)
     +--- otlp receiver (SDK traces + metrics + logs)
     |
     v
Oodle (metrics + traces + logs)
```

## Components

| Service | Description | Port |
|---------|-------------|------|
| temporal | Temporal server (auto-setup with PostgreSQL) | 7233 (gRPC), 8000 (metrics) |
| temporal-ui | Temporal Web UI | 8080 |
| postgresql | PostgreSQL database for Temporal | 5432 |
| otel-collector | OpenTelemetry Collector | 4317 (gRPC), 4318 (HTTP) |
| worker | Python worker running OrderProcessingWorkflow | — |
| starter | Load generator that continuously starts workflows | — |

## Prerequisites

- Docker & Docker Compose
- An [Oodle](https://oodle.ai) account (instance ID and API key)
- [Oodle CLI](https://docs.oodle.ai) (`oodle`) — for importing dashboards and verifying data flow

## Quick Start

View available options:
```bash
make help
```

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your credentials:
   ```bash
   OODLE_INSTANCE=your-instance-id
   OODLE_API_KEY=your-api-key
   ```

3. Build and start all services:
   ```bash
   make up
   ```

4. Import Temporal dashboards to Oodle:
   ```bash
   make import-dashboards
   ```

5. The load generator starts automatically, producing workflows every ~5 seconds. To start a single test workflow manually:
   ```bash
   make test
   ```

## Observability Signals

### Traces
The `TracingInterceptor` from `temporalio.contrib.opentelemetry` creates spans for:
- Client workflow start calls
- Workflow executions
- Activity executions (validate, payment, ship, notify)

Traces propagate through the Temporal server, giving one unified trace per workflow execution.

### Metrics
Two sources of metrics flow to Oodle:

**Temporal Server metrics** (scraped via Prometheus receiver):
- `service_requests` — service request counts by operation
- `service_latency` — request latency histograms
- `persistence_requests` / `persistence_latency` — database operation metrics
- `workflow_success` / `workflow_failed` — workflow outcome counters

**SDK metrics** (sent via OTLP from worker/starter):
- `temporal_workflow_completed` / `temporal_workflow_failed` — workflow outcomes
- `temporal_workflow_endtoend_latency` — end-to-end workflow duration
- `temporal_activity_execution_latency` — activity execution time
- `temporal_activity_schedule_to_start_latency` — queue wait time
- `temporal_worker_task_slots_available` / `_used` — worker capacity

### Logs
Structured JSON logs from the worker with trace correlation (`trace_id`, `span_id`). Exported via OTLP to the collector and forwarded to Oodle.

## Dashboards

Two official Temporal Grafana dashboards are included in `dashboards/`:

- **temporal-server.json** — Server metrics: actions, availability, persistence, workflow/activity task rates
- **temporal-sdk.json** — SDK metrics: RPC latencies, workflow/activity throughput, worker slots, sticky cache

Import them:
```bash
make import-dashboards
```

## Verifying Data Flow

### Using Oodle CLI

Check metrics are flowing:
```bash
# Temporal server metrics
oodle metrics names --start -30m --end now | grep -E 'service_requests|persistence'

# SDK metrics
oodle metrics names --start -30m --end now | grep temporal_

# Query a specific metric
oodle metrics query --query 'temporal_workflow_completed' --time now
```

Check traces are flowing:
```bash
oodle traces list --service temporal-worker --start -30m --end now --limit 5
```

Check logs are flowing:
```bash
oodle logs index-patterns
```

### Using Docker logs

```bash
# Check OTel Collector for export activity
make logs-collector

# Check worker logs for workflow processing
make logs-worker

# Check starter logs for workflow submissions
make logs-starter
```

### Using Temporal Web UI

Open http://localhost:8080 to see workflows, their status, and execution history.

## Viewing in Oodle

1. Log in to your Oodle instance
2. **Traces**: Navigate to Traces, filter by service `temporal-worker`
3. **Metrics**: Navigate to Metrics Explorer, search for `temporal_` or `service_requests`
4. **Logs**: Navigate to Logs, filter by `service: temporal-worker`
5. **Dashboards**: Open the imported Temporal Server or SDK dashboards

## Configuration

### Workflow interval

Control how often the load generator starts new workflows:
```bash
# In .env
WORKFLOW_INTERVAL_SECONDS=10
```

### Temporal server

The server runs with `temporalio/auto-setup` which automatically creates the database schema. For production, use the standard `temporalio/server` image with a migration tool.

## Troubleshooting

### Data not appearing in Oodle

1. **Check OTel Collector logs for export errors:**
   ```bash
   make logs-collector
   ```

2. **Verify environment variables are set:**
   ```bash
   docker-compose config | grep OODLE
   ```

3. **Verify the Oodle endpoint is reachable:**
   ```bash
   curl -v "https://${OODLE_INSTANCE}-otlp.collector.oodle.ai/v1/traces"
   ```

### Worker not connecting to Temporal

The worker retries connecting to the Temporal server. If it fails persistently:
```bash
make logs-temporal   # Check server health
make logs-worker     # Check connection errors
```

### Temporal server not starting

Check PostgreSQL is healthy:
```bash
docker-compose logs postgresql
```

## Cleanup

Stop all services and remove volumes:
```bash
make clean
```
