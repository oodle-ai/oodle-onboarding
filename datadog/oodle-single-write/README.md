# Datadog Agent → Oodle Only

Send **metrics**, **APM traces**, and **logs** from a Datadog-instrumented app to Oodle only — no data sent to Datadog.

## Architecture

```
┌──────────────┐         ┌──────────────────┐
│  demo-app    │─DogStatsD→│                  │
│  (Go)        │─APM──────→│  Datadog Agent   │──→  Oodle
│  :8080       │─Logs─────→│  :8125 (StatsD)  │
└──────────────┘          │  :8126 (APM)     │
                          └──────────────────┘
```

The Datadog Agent's primary endpoints (`DD_DD_URL`, `DD_APM_DD_URL`, `DD_LOGS_CONFIG_LOGS_DD_URL`) are redirected to Oodle. The agent still requires `DD_API_KEY` to start, but no data reaches Datadog.

## What Gets Sent

| Category | Examples |
|----------|---------|
| **Host Metrics** | CPU, memory, disk, network (collected by Datadog Agent) |
| **Custom Metrics** | `demo.order.requests`, `demo.queue.depth`, `demo.cache.hit_ratio`, `demo.active_connections` |
| **APM Traces** | HTTP spans for `/api/order`, `/api/users` endpoints |
| **Logs** | JSON-structured app logs with `dd.trace_id`/`dd.span_id` correlation |

## Quick Start

1. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Oodle credentials
   ```

2. **Start services**
   ```bash
   make up
   ```

3. **Generate traffic**
   ```bash
   make test
   ```

4. **View in Oodle** — metrics, traces, and logs appear in the Oodle UI.

## How It Works

Instead of using `DD_ADDITIONAL_ENDPOINTS` (which adds Oodle as a secondary destination alongside Datadog), this setup overrides the primary endpoints:

| Signal | Environment Variable | Oodle Endpoint |
|--------|---------------------|----------------|
| Metrics | `DD_DD_URL` | `https://<collector>/v1/datadog/<instance>` |
| Traces | `DD_APM_DD_URL` | `https://<collector>/v1/datadog_traces/<instance>` |
| Logs | `DD_LOGS_CONFIG_LOGS_DD_URL` | `https://<logs-collector>` |

No application code changes needed — the same app and instrumentation from `datadog/single-write` works unchanged.

## Related Demos

| Demo | Agent | Sends to |
|------|-------|----------|
| [datadog/single-write](../single-write) | Datadog Agent | Datadog only |
| [datadog/dual-write](../dual-write) | Datadog Agent | Datadog + Oodle |
| **datadog/oodle-single-write** | **Datadog Agent** | **Oodle only** |
| [datadog/otel-dual-write](../otel-dual-write) | OTel Collector | Datadog + Oodle |

## Cleanup

```bash
make clean
```
