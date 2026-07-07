# Datadog Database Monitoring Demo (Oodle Only)

Three local PostgreSQL instances monitored by the Datadog Agent with Database Monitoring (DBM) enabled, shipping all data exclusively to Oodle.

## Architecture

```
┌──────────────┐       ┌──────────────────┐
│  workload    │       │  orders-db       │
│  (psql)      │──SQL─→│  :5432 (orders)  │──┐
│              │       └──────────────────┘  │
│  inserts,    │       ┌──────────────────┐  │  ┌──────────────────┐
│  selects,    │──SQL─→│  analytics-db    │──┼─→│  Datadog Agent   │──→ Oodle
│  updates,    │       │  :5433 (analytics)│  │  │  (DBM enabled)   │
│  joins,      │       └──────────────────┘  │  │  query samples   │
│  CTEs        │       ┌──────────────────┐  │  │  explain plans   │
│              │──SQL─→│  inventory-db    │──┘  │  schema info     │
│              │       │  :5434 (inventory)│     └──────────────────┘
└──────────────┘       └──────────────────┘
```

Data is sent **only to Oodle** — no data goes to Datadog. The agent uses `DD_DD_URL` and `DD_DATABASE_MONITORING_*` environment variables to redirect all DBM telemetry to Oodle's collectors.

## What Gets Monitored

| Signal | Description |
|--------|-------------|
| **Query Samples** | Normalized queries with execution stats from `pg_stat_statements` |
| **Explain Plans** | JSON execution plans via `datadog.explain_statement()` |
| **Query Activity** | Active queries and wait events from `pg_stat_activity` |
| **Schema Info** | Table definitions, indexes, foreign keys |
| **Relation Metrics** | Per-table row counts, dead tuples, sequential scans |
| **PostgreSQL Metrics** | Connections, locks, replication lag, buffer cache hit ratio |

## Databases

| Host | Database | Tables | Workload |
|------|----------|--------|----------|
| `orders-db` | orders | users, orders | Order inserts, top-spender aggregations, status updates |
| `analytics-db` | analytics | page_views, events | Page view tracking, event analytics, moving averages |
| `inventory-db` | inventory | products, stock | Stock updates, low-stock alerts, warehouse summaries |

## Prerequisites

- Docker and Docker Compose
- [Oodle account](https://app.oodle.ai) with a configured Datadog DBM integration

## Quick Start

1. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and fill in your Oodle values
   ```

2. **Start services**
   ```bash
   make up
   ```

3. **Verify the agent is collecting**
   ```bash
   make logs-agent
   # Look for: "check:postgres | Running check..." for all three hosts
   ```

4. **View in Oodle**
   - Database Monitoring — three hosts (orders-db, analytics-db, inventory-db) with query samples, explain plans, and activity

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OODLE_API_KEY` | Oodle API key (passed to the Datadog Agent as `DD_API_KEY`) |
| `DD_DD_URL` | Oodle collector URL for metrics |
| `DD_DATABASE_MONITORING_SAMPLES_LOGS_DD_URL` | Oodle logs collector URL for query samples |
| `DD_DATABASE_MONITORING_ACTIVITY_LOGS_DD_URL` | Oodle logs collector URL for query activity |
| `DD_DATABASE_MONITORING_METRICS_LOGS_DD_URL` | Oodle collector URL for DBM metrics |
| `POSTGRES_PASSWORD` | PostgreSQL admin password (default: `postgres`) |
| `DBM_MONITORING_PASSWORD` | Password for the `datadog` monitoring user (default: `datadog`) |

## Exploring

Open a psql shell to any database:
```bash
make psql                                          # orders-db (default)
docker compose exec analytics-db psql -U postgres -d analytics
docker compose exec inventory-db psql -U postgres -d inventory
```

View pg_stat_statements:
```sql
SELECT query, calls, mean_exec_time, rows
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

## Cleanup

```bash
make clean
```
