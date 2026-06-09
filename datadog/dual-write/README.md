# Datadog Dual-Write Demo (Datadog + Oodle)

A minimal Go application that sends **host metrics**, **custom metrics**, **APM traces**, and **logs** to both Datadog and Oodle simultaneously using Datadog's built-in dual-shipping support.

## Architecture

```
┌──────────────┐         ┌──────────────────┐
│  demo-app    │─DogStatsD→│                  │──→  Datadog Cloud
│  (Go)        │─APM──────→│  Datadog Agent   │
│  :8080       │─Logs─────→│  :8125 (StatsD)  │──→  Oodle
└──────────────┘          │  :8126 (APM)     │     (metrics, logs, traces)
                          └──────────────────┘
```

The Datadog Agent uses `DD_ADDITIONAL_ENDPOINTS`, `DD_LOGS_CONFIG_ADDITIONAL_ENDPOINTS`, and `DD_APM_ADDITIONAL_ENDPOINTS` to forward all signals to Oodle alongside Datadog — no code changes required.

## What Gets Sent (to both Datadog and Oodle)

| Category | Examples |
|----------|---------|
| **Host Metrics** | CPU, memory, disk, network (collected by Datadog Agent) |
| **Custom Metrics** | `demo.order.requests`, `demo.queue.depth`, `demo.cache.hit_ratio`, `demo.active_connections` |
| **APM Traces** | HTTP spans for `/api/order`, `/api/users` endpoints |
| **Logs** | JSON-structured app logs with `dd.trace_id`/`dd.span_id` for APM correlation |

## Prerequisites

- Docker and Docker Compose
- [Datadog account](https://www.datadoghq.com/) with an API key
- [Oodle account](https://app.oodle.ai) with a configured Datadog integration

## Quick Start

1. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and set DD_API_KEY and OODLE_* values
   ```

2. **Start services**
   ```bash
   make up
   ```

3. **Generate traffic**
   ```bash
   make test
   ```

4. **View in Datadog**
   - [APM Traces](https://app.datadoghq.com/apm/traces) - search for `service:datadog-demo`
   - [Metrics Explorer](https://app.datadoghq.com/metric/explorer) - search for `demo.*`
   - [Logs](https://app.datadoghq.com/logs) - search for `service:datadog-demo`

5. **View in Oodle**
   - Metrics, logs, and traces appear in the Oodle UI
   - Check integration status: `oodle integrations list`

## How Dual-Write Works

The Datadog Agent natively supports sending data to additional endpoints. No application code changes are needed — the agent handles forwarding:

| Signal | Environment Variable | Oodle Endpoint |
|--------|---------------------|----------------|
| Metrics | `DD_ADDITIONAL_ENDPOINTS` | `https://<collector>/v1/datadog/<instance>` |
| Logs | `DD_LOGS_CONFIG_ADDITIONAL_ENDPOINTS` | `https://<logs-collector>` |
| Traces | `DD_APM_ADDITIONAL_ENDPOINTS` | `https://<collector>/v1/datadog_traces/<instance>` |

See [Datadog dual-shipping docs](https://docs.datadoghq.com/agent/configuration/dual-shipping/) for details.

## Endpoints

| Path | Method | Description |
|------|--------|-------------|
| `/health` | GET | Health check |
| `/api/order` | POST | Create order (simulated, ~10% error rate) |
| `/api/users` | GET | List users |

## Cleanup

```bash
make clean
```
