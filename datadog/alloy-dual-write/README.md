# Grafana Alloy → Datadog + Oodle (dual-write)

Run **Grafana Alloy** and fan the same telemetry out to **both** Datadog and Oodle using
two `otelcol.exporter.datadog` components:

- `datadog` → the normal Datadog intake (site-derived endpoints, Datadog API key)
- `oodle` → Oodle's Datadog single-write endpoints (Oodle API key)

## Architecture

```
┌──────────────┐   OTLP    ┌───────────────────────────┐   ┌──→ Datadog (api.<site>)
│  demo-app    │──gRPC────→│  Grafana Alloy            │───┤
│  (Go, OTLP)  │           │  receiver → batch → 2x    │   └──→ Oodle (/v1/datadog…)
└──────────────┘           │  otelcol.exporter.datadog │
                           └───────────────────────────┘
```

The `oodle` exporter overrides `traces.endpoint` / `metrics.endpoint` to Oodle's Datadog
intake paths; the `datadog` exporter uses the default endpoints derived from `DD_SITE`.

> `otelcol.exporter.datadog` is a **community component**, so Alloy runs with
> `--feature.community-components.enabled=true` (see `docker-compose.yml`).

## Quick Start

```bash
cp .env.example .env      # set DD_API_KEY / DD_SITE and the Oodle values
make up
make test
```

Alloy UI/debug: http://localhost:12346 (host ports 4319/4320/8081 avoid clashing with
the `alloy-single-write` demo).

## Verifying

Oodle side (read back with the CLI):

```bash
oodle metrics query \
  --query 'sum by (resource) (dd_trace_stats_hits{service="alloy-dual-demo"})' \
  --time now -o table
```

Datadog side: check the Alloy logs show the `datadog` exporter validating its key and
starting a forwarder to `https://api.<site>`, with no send errors, then look for
`service:alloy-dual-demo` in Datadog APM.

## Related Demos

| Demo | Agent | Sends to |
|------|-------|----------|
| [datadog/single-write](../single-write) | Datadog Agent | Datadog only |
| [datadog/dual-write](../dual-write) | Datadog Agent | Datadog + Oodle |
| [datadog/oodle-single-write](../oodle-single-write) | Datadog Agent | Oodle only |
| [datadog/otel-dual-write](../otel-dual-write) | OTel Collector | Datadog + Oodle |
| [datadog/alloy-single-write](../alloy-single-write) | Grafana Alloy | Oodle only (Datadog intake) |
| **datadog/alloy-dual-write** | **Grafana Alloy** | **Datadog + Oodle** |

## Cleanup

```bash
make clean
```
