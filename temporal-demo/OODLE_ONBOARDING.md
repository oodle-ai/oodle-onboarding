# Oodle Onboarding: Temporal Workflow Observability

## What This Demonstrates

This setup shows how to send **all three observability signals** (metrics, traces, and logs) from a self-hosted [Temporal](https://temporal.io) deployment to Oodle using an OpenTelemetry Collector. It covers both Temporal server-side metrics (Prometheus) and Python SDK telemetry (OTLP).

## How It Works

1. The **Temporal Python SDK** is instrumented with `TracingInterceptor` from `temporalio.contrib.opentelemetry`, which auto-creates spans for workflow executions, activity executions, and client RPC calls. Traces propagate through the Temporal server to give one unified trace per workflow.

2. **SDK metrics** (`temporal_workflow_completed`, `temporal_activity_execution_latency`, `temporal_worker_task_slots_available`, etc.) are sent via OTLP gRPC to the OTel Collector using `OpenTelemetryConfig` in the Temporal runtime.

3. **Temporal server metrics** (`service_requests`, `persistence_latency`, `workflow_success`, etc.) are exposed as a Prometheus endpoint on `:8000` and scraped by the OTel Collector's `prometheus` receiver.

4. **Structured logs** from the Python worker are exported via OTLP using OpenTelemetry's `LoggerProvider`, with trace correlation (`trace_id`, `span_id`) for linking logs to traces.

5. The OTel Collector forwards all three signals to **Oodle** using the `-otlp` subdomain endpoint.

## Oodle Configuration

The OTel Collector is configured to export all signals to Oodle in `otel-collector-config.yaml`:

```yaml
exporters:
  otlphttp/oodle:
    endpoint: "https://${OODLE_INSTANCE}-otlp.collector.oodle.ai"
    headers:
      "X-OODLE-INSTANCE": "${OODLE_INSTANCE}"
      "X-API-KEY": "${OODLE_API_KEY}"
```

The collector has three pipelines:
- **traces**: `otlp` receiver → `otlphttp/oodle` exporter
- **metrics**: `otlp` + `prometheus` receivers → `otlphttp/oodle` exporter
- **logs**: `otlp` receiver → `otlphttp/oodle` exporter

The `prometheus` receiver scrapes the Temporal server's metrics endpoint:
```yaml
receivers:
  prometheus:
    config:
      scrape_configs:
        - job_name: "temporal-server"
          scrape_interval: 15s
          static_configs:
            - targets: ["temporal:8000"]
```

## Dashboards

Two official Temporal Grafana dashboards from [temporalio/dashboards](https://github.com/temporalio/dashboards) are included:

- **temporal-server.json** — 23 panels covering server actions, service availability, persistence latency, workflow/activity task processing
- **temporal-sdk.json** — 37 panels covering RPC request rates/latencies, workflow completion/failure, activity throughput, worker slot utilization, sticky cache metrics

Import to Oodle:
```bash
oodle dashboards create -f dashboards/temporal-server.json
oodle dashboards create -f dashboards/temporal-sdk.json
```

## What You'll See in Oodle

### Traces
- **Workflow traces** spanning client → server → worker with activities as child spans
- **Activity spans**: `validate_order`, `process_payment`, `ship_order`, `send_notification`
- **Service names**: `temporal-worker`, `temporal-starter`

### Metrics
- **Server metrics**: `service_requests`, `service_latency`, `persistence_requests`, `persistence_latency`, `workflow_success`, `workflow_failed`
- **SDK metrics**: `temporal_workflow_completed`, `temporal_workflow_failed`, `temporal_workflow_endtoend_latency`, `temporal_activity_execution_latency`, `temporal_activity_schedule_to_start_latency`, `temporal_worker_task_slots_available`

### Logs
- Structured JSON logs from the worker with `trace_id` and `span_id` for trace correlation
- Activity-level logging: order validation, payment processing, shipping, notifications

## Verifying with Oodle CLI

```bash
# Check server metrics are arriving
oodle metrics names --start -30m --end now | grep -E 'service_requests|persistence'

# Check SDK metrics are arriving
oodle metrics names --start -30m --end now | grep temporal_

# Query a specific metric
oodle metrics query --query 'temporal_workflow_completed' --time now

# Check traces
oodle traces list --service temporal-worker --start -30m --end now --limit 5

# Check logs
oodle logs index-patterns

# List dashboards
oodle dashboards list
```
