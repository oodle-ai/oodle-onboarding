# Datadog Single-Write Demo

A minimal Go application that sends **host metrics**, **custom metrics**, **APM traces**, and **logs** to Datadog.

## Architecture

```
┌──────────────┐         ┌──────────────────┐
│  demo-app    │─DogStatsD→│                  │
│  (Go)        │─APM──────→│  Datadog Agent   │──→  Datadog Cloud
│  :8080       │─Logs─────→│  :8125 (StatsD)  │
└──────────────┘          │  :8126 (APM)     │
                          │  + host metrics  │
                          │  + container logs│
                          └──────────────────┘
```

## What Gets Sent

| Category | Examples |
|----------|---------|
| **Host Metrics** | CPU, memory, disk, network (collected by Datadog Agent) |
| **Custom Metrics** | `demo.order.requests`, `demo.queue.depth`, `demo.cache.hit_ratio`, `demo.active_connections` |
| **APM Traces** | HTTP spans for `/api/order`, `/api/users` endpoints |
| **Logs** | JSON-structured app logs with `dd.trace_id`/`dd.span_id` for APM correlation |

## Prerequisites

- Docker and Docker Compose
- [Datadog account](https://www.datadoghq.com/) with an API key

## Quick Start

1. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and set DD_API_KEY
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
   - [Infrastructure](https://app.datadoghq.com/infrastructure) - host metrics from the agent container

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
