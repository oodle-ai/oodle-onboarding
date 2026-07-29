# Grafana Alloy → Oodle (single-write via the Datadog intake path)

Run **Grafana Alloy** (instead of an OTel Collector or the Datadog Agent) and send
telemetry to Oodle **only** — without using an OTLP exporter for Oodle. Instead, the
`otelcol.exporter.datadog` component (which normally ships to Datadog) is pointed at
Oodle's **Datadog single-write endpoints**.

## Architecture

```
┌──────────────┐   OTLP    ┌───────────────────────────┐
│  demo-app    │──gRPC────→│  Grafana Alloy            │
│  (Go, OTLP)  │  :4317    │  otelcol.receiver.otlp    │
│  :8080       │           │        │                  │
└──────────────┘           │        ▼                  │
                           │  otelcol.exporter.datadog │──→ Oodle
                           │  (Datadog intake protocol)│    (Datadog single-write)
                           └───────────────────────────┘
```

## Why the datadog exporter (not an OTLP exporter)

Oodle exposes a native **Datadog intake** on these per-instance paths, so a Datadog-format
producer can write straight to Oodle:

| Signal  | Oodle endpoint |
|---------|----------------|
| Metrics | `https://<collectorDomain>/v1/datadog/<instanceId>` |
| Traces  | `https://<collectorDomain>/v1/datadog_traces/<instanceId>` |
| Logs    | `https://<logsCollectorDomain>` |

In `config.alloy` the datadog exporter is authenticated with the **Oodle API key** and its
`traces.endpoint` / `metrics.endpoint` are overridden to the URLs above:

```alloy
otelcol.exporter.datadog "oodle" {
  api { api_key = sys.env("OODLE_API_KEY") }
  traces  { endpoint = sys.env("OODLE_DD_TRACES_ENDPOINT")  ... }
  metrics { endpoint = sys.env("OODLE_DD_METRICS_ENDPOINT") ... }
}
```

`compute_stats_by_span_kind` / `compute_top_level_by_span_kind` make the exporter compute
APM stats for every span, which Oodle surfaces as the `dd_trace_stats_*` metric family.

> `otelcol.exporter.datadog` is a **community component**, so Alloy is started with
> `--feature.community-components.enabled=true` (see `docker-compose.yml`).

## Quick Start

```bash
cp .env.example .env      # fill in OODLE_API_KEY / OODLE_COLLECTOR_DOMAIN / OODLE_INSTANCE_ID
make up                   # build + start alloy, demo-app, load-generator
make test                 # send a few requests
```

Alloy UI/debug: http://localhost:12345

## Verifying data in Oodle

The APM trace/span metrics land as the `dd_trace_stats_*` family (there is no literal
`dd_trace_span` metric name in Oodle). Verify with the Oodle CLI:

```bash
# span/trace hit counters for this demo's service
oodle metrics query \
  --query 'sum by (operation, resource) (dd_trace_stats_hits{service="alloy-oodle-demo"})' \
  --time now -o table

# p95 latency by endpoint
oodle metrics query \
  --query 'max by (resource) (dd_trace_stats_latency{service="alloy-oodle-demo", quantile="0.95"})' \
  --time now -o table
```

Available metrics from this path include: `dd_trace_stats_hits`, `dd_trace_stats_errors`,
`dd_trace_stats_latency`, `dd_trace_stats_duration`, `dd_trace_stats_error_latency`,
`dd_trace_stats_top_level_hits` (labels: `service`, `resource`, `operation`, `span_kind`,
`type`, `env`, `version`, `http_status_code`, `hostname`).

## Related Demos

| Demo | Agent | Sends to |
|------|-------|----------|
| [datadog/single-write](../single-write) | Datadog Agent | Datadog only |
| [datadog/dual-write](../dual-write) | Datadog Agent | Datadog + Oodle |
| [datadog/oodle-single-write](../oodle-single-write) | Datadog Agent | Oodle only |
| [datadog/otel-dual-write](../otel-dual-write) | OTel Collector | Datadog + Oodle |
| **datadog/alloy-single-write** | **Grafana Alloy** | **Oodle only (Datadog intake)** |

## Cleanup

```bash
make clean
```
