# CockroachDB Demo

A three-node [CockroachDB](https://www.cockroachlabs.com) cluster under continuous load, with every node's Prometheus endpoint scraped by an OpenTelemetry Collector and shipped to Oodle over OTLP.

No CockroachDB configuration changes are needed: the `/_status/vars` endpoint is on by default. The only moving part you add is the collector.

See [OODLE_ONBOARDING.md](./OODLE_ONBOARDING.md) for the Oodle-specific integration details.

## Architecture

```
movr workload (cockroach workload run movr)
     |
     | SQL :26257, spread across all three gateways
     v
roach1        roach2        roach3          <- 3-node CockroachDB cluster
  :8080         :8080         :8080         <- DB Console + /_status/vars
     \            |            /
      \           |           /
       scrape /_status/vars every 15s
                  |
                  v
        OTel Collector
          prometheus receiver
          resource + transform processors (label hygiene)
          batch processor
                  |
                  v OTLP/HTTP
               Oodle (metrics)
```

## Components

| Service | Description | Port |
|---------|-------------|------|
| roach1 / roach2 / roach3 | CockroachDB nodes, insecure mode | 26257 (SQL), 8080 (HTTP); only roach1 is published to the host |
| crdb-init | One-shot `cockroach init` that forms the cluster, then exits | none |
| workload | `cockroach workload run movr`, load spread across all three nodes | none |
| otel-collector | Scrapes all three nodes and exports to Oodle | 13133 (health), 8888 (self-metrics) |

## Prerequisites

- Docker & Docker Compose (~3 GB of memory available to Docker)
- An [Oodle](https://oodle.ai) account (instance ID and API key)
- [Oodle CLI](https://docs.oodle.ai) (`oodle`), for `make verify` and `make import-dashboards`

## Quick Start

```bash
cp .env.example .env
# edit .env: OODLE_INSTANCE and OODLE_API_KEY
make up
```

The cluster takes about a minute to form and seed the `movr` dataset. Then:

```bash
make verify              # confirm metrics reached Oodle
make import-dashboards   # add the CockroachDB dashboard
```

The CockroachDB DB Console is at http://localhost:8080, useful for cross-checking what Oodle is showing.

Run `make help` for the full target list.

## What Gets Collected

CockroachDB exposes roughly 2,400 distinct metric families per node covering SQL, KV, storage, replication, admission control, and process health. This demo ships all of them, which works out to ~2,000 OTLP data points per node per scrape.

Metrics worth knowing:

| Metric | What it tells you |
|--------|-------------------|
| `liveness_livenodes` | Nodes the cluster considers live. Alert if it drops below your node count. |
| `ranges_underreplicated` | Ranges below the configured replication factor. Sustained non-zero means rebalancing is stuck. |
| `ranges_unavailable` | Ranges that lost quorum. Any non-zero value means part of the keyspace is unreadable. |
| `sql_query_count` | Total SQL statements. Split by `crdb_node` to check gateway balance. |
| `sql_select_count` / `sql_insert_count` / `sql_update_count` / `sql_delete_count` | Statement mix. |
| `sql_service_latency_bucket` | Full server-side statement latency histogram, in **nanoseconds**. |
| `sql_exec_latency_bucket` | Execution-only latency. The gap versus service latency is planning and parsing. |
| `sql_failure_count` | Statements that returned an error. |
| `sql_full_scan_count` | Full table scans, the usual first suspect when p99 climbs without a traffic change. |
| `txn_commits` / `txn_aborts` | KV-layer transaction outcomes. |
| `capacity_used` / `capacity` | Per-store disk usage. |
| `rocksdb_read_amplification` | SSTs read per lookup. Above ~20 means compaction is falling behind. |
| `sys_cpu_combined_percent_normalized` | CPU, already normalized to core count (1.0 = saturated). |
| `clock_offset_meannanos` | Clock skew against peers. A node self-terminates as this approaches half of `--max-offset`. |

Inspect the raw exposition directly:

```bash
make scrape
```

## Labels

Each series arrives in Oodle with:

| Label | Example | Source |
|-------|---------|--------|
| `crdb_cluster` | `crdb-demo` | `relabel_configs` in the collector, from `CRDB_CLUSTER_NAME` |
| `crdb_node` | `roach1` | per-target label in the scrape config |
| `node_id` | `1` | CockroachDB itself |
| `store` | `1` | CockroachDB, on store-scoped metrics |
| `instance` | `roach1:8080` | Prometheus receiver |
| `job` | `cockroachdb` | Prometheus receiver |

Prefer `crdb_node` over `node_id` for grouping. CockroachDB assigns node IDs in the order nodes join, so `roach3` can end up as node 2. `crdb_node` stays stable across restarts.

## Why Transactions Look Idle

`sql_txn_commit_count` counts explicit `COMMIT` statements only. The `movr` workload uses implicit transactions, so that metric sits at zero while the cluster is clearly busy. Use the KV-layer counters `txn_commits` and `txn_aborts` for real transaction throughput.

## Trimming Ingest Volume

Three nodes at a 15s scrape interval is roughly 400 data points per second. `otel-collector-config.yaml` defines a `filter/crdb` processor that keeps only the families this dashboard uses. Add it to the metrics pipeline to drop from ~2,000 data points per node per scrape to 28:

```yaml
processors: [memory_limiter, resource, filter/crdb, transform/drop_scope, batch]
```

Raising `CRDB_SCRAPE_INTERVAL` in `.env` is the other lever.

## Applying This to a Real Cluster

Two changes:

1. **Point the scrape config at your nodes.** Replace the `static_configs` targets in `otel-collector-config.yaml`. On Kubernetes, swap in `kubernetes_sd_configs` against the CockroachDB pods instead.

2. **Handle TLS on secure clusters.** `/_status/vars` requires an authenticated HTTPS request when the cluster runs with certificates. Add to the scrape config:

   ```yaml
   scheme: https
   tls_config:
     ca_file: /certs/ca.crt
     cert_file: /certs/client.root.crt
     key_file: /certs/client.root.key
   ```

   Mount the client certificates into the collector container. This demo runs `--insecure` so it can skip all of that.

## Troubleshooting

**No metrics in Oodle.** Check the collector's own counters first:

```bash
curl -s localhost:8888/metrics | grep otelcol_exporter_.*oodle
```

A rising `sent_metric_points` with zero `send_failed_metric_points` means the collector is fine and the problem is on the query side. A rising failure count means credentials or endpoint; check `make logs-collector`.

**Cluster never becomes ready.** `docker compose ps` should show all three nodes healthy and `crdb-init` exited 0. If `crdb-init` keeps restarting, the nodes cannot reach each other; check `make logs-crdb`.

**`workload init` fails with "memory budget exceeded".** Give Docker more memory, or raise `--max-sql-memory` in `docker-compose.yml`. It backs the bulk-ingest monitor the seed import uses, not just query execution.
