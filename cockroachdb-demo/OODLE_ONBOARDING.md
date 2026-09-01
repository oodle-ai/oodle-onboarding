# Oodle Onboarding: CockroachDB Metrics

## What This Demonstrates

Shipping a CockroachDB cluster's metrics to Oodle with no changes to CockroachDB itself. Every node already exposes a Prometheus endpoint at `/_status/vars` on its HTTP port; an OpenTelemetry Collector scrapes it and forwards to Oodle over OTLP/HTTP.

## How It Works

1. Each CockroachDB node serves Prometheus-format metrics at `http://<node>:8080/_status/vars`. This is on by default and needs no flags or cluster settings.

2. The collector's **`prometheus` receiver** scrapes all three nodes every 15 seconds, with one `static_configs` entry per node so each target can carry a `crdb_node` label.

3. A **`relabel_configs`** rule stamps `crdb_cluster` on every series from the `CRDB_CLUSTER_NAME` environment variable, so several clusters can share one Oodle instance without their series colliding.

4. The **`resource` and `transform` processors** drop scrape-target metadata that Oodle would otherwise turn into labels on all ~2,400 series (see "Label Hygiene" below).

5. The **`otlphttp/oodle` exporter** forwards everything to the `-otlp` subdomain endpoint.

## Oodle Configuration

```yaml
exporters:
  otlphttp/oodle:
    endpoint: "https://${env:OODLE_INSTANCE}-otlp.collector.oodle.ai"
    headers:
      "X-OODLE-INSTANCE": "${env:OODLE_INSTANCE}"
      "X-API-KEY": "${env:OODLE_API_KEY}"
```

The scrape side:

```yaml
receivers:
  prometheus:
    config:
      scrape_configs:
        - job_name: "cockroachdb"
          scrape_interval: ${env:CRDB_SCRAPE_INTERVAL}
          metrics_path: "/_status/vars"
          static_configs:
            - targets: ["roach1:8080"]
              labels:
                crdb_node: "roach1"
            # ...one entry per node
          relabel_configs:
            - target_label: "crdb_cluster"
              replacement: "${env:CRDB_CLUSTER_NAME}"
```

One pipeline: `prometheus` receiver → `memory_limiter`, `resource`, `transform`, `batch` → `otlphttp/oodle`.

## Label Hygiene

Oodle turns every OTLP **resource attribute** into a metric label. The Prometheus receiver attaches scrape-target metadata as resource attributes, so without intervention each of the ~2,400 CockroachDB series carries six redundant labels: `net_host_name`, `net_host_port`, `server_address`, `server_port`, `http_scheme`, `url_scheme`, all of which restate `instance`. The instrumentation scope adds a seventh, `otel_scope_name`, holding the receiver's Go package path.

The `resource` processor deletes the six, and a `transform` processor blanks the scope name:

```yaml
processors:
  resource:
    attributes:
      - key: net.host.name
        action: delete
      # ...and the rest
  transform/drop_scope:
    metric_statements:
      - context: scope
        statements:
          - set(name, "")
          - set(version, "")
```

Resulting label set on every series:

```
crdb_cluster, crdb_node, db_system, instance, job, node_id
```

plus whatever CockroachDB itself attaches (`store`, `le` on histograms, and so on).

Note that changing these processors mid-flight creates new series rather than modifying existing ones, so the old label sets stay queryable until they age out.

## Dashboard

`dashboards/cockroachdb.json` holds "CockroachDB / Cluster Overview", 22 panels:

- **Cluster Health**: live nodes, under-replicated and unavailable ranges, statement throughput, p99 latency, open connections
- **SQL**: statements by type, service latency quantiles, per-node throughput, errors and full scans
- **Transactions and Ranges**: KV commits/aborts, ranges and replicas per node
- **Storage and Resources**: disk capacity, CPU, RSS, read amplification, live data size, clock offset

Template variables `$cluster` and `$node` filter every panel.

```bash
oodle dashboards create -f dashboards/cockroachdb.json
```

## Verifying with Oodle CLI

```bash
# Metric families arriving
oodle metrics names -o csv | grep -E '^(sql_|txn_|ranges|replicas|liveness_|capacity)'

# Cluster is whole
oodle metrics query --query 'max(liveness_livenodes{crdb_cluster="crdb-demo"})' -o table

# Throughput per gateway node
oodle metrics query --query 'sum by (crdb_node) (rate(sql_query_count{crdb_cluster="crdb-demo"}[5m]))' -o table

# p99 statement latency (nanoseconds)
oodle metrics query --query 'histogram_quantile(0.99, sum by (le) (rate(sql_service_latency_bucket{crdb_cluster="crdb-demo"}[5m])))' -o table

# Replication health
oodle metrics query --query 'sum(ranges_underreplicated{crdb_cluster="crdb-demo"})' -o table
```

`make verify` runs the same checks, plus the collector's own export counters.

## Suggested Monitors

| Condition | Expression |
|-----------|------------|
| Node down | `max(liveness_livenodes{crdb_cluster="..."}) < 3` |
| Ranges lost quorum | `sum(ranges_unavailable{crdb_cluster="..."}) > 0` |
| Under-replication persists | `sum(ranges_underreplicated{crdb_cluster="..."}) > 0` for 15m |
| Statement latency regression | `histogram_quantile(0.99, sum by (le) (rate(sql_service_latency_bucket{...}[5m]))) > 1e9` (1s, in ns) |
| Disk filling | `max by (crdb_node) (capacity_used{...} / capacity{...}) > 0.8` |
| Compaction falling behind | `max by (crdb_node) (rocksdb_read_amplification{...}) > 20` |
