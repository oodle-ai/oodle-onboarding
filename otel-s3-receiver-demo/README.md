# OpenTelemetry awss3 exporter/receiver with MinIO — demo + benchmark

Demonstrates that the opentelemetry-collector-contrib **awss3exporter** and
**awss3receiver** work against an S3-compatible backend (MinIO), and benchmarks the
receiver's CPU / memory / throughput when replaying data from object storage,
including a histogram fan-in pipeline (`deltatocumulative` + `interval`).

Collector version used: `otel/opentelemetry-collector-contrib:latest` (v0.155.0).

## What makes S3-compatible stores work

Both components use the AWS SDK, so pointing them at MinIO only needs:

- `endpoint: http://minio:9000` on both sides
- `s3_force_path_style: true` (MinIO serves `host:9000/bucket/key`, not virtual-host style)
- `disable_ssl: true` on the **exporter** for a plaintext `http://` endpoint (the receiver has no such flag; plaintext works, self-signed HTTPS needs a trusted cert)
- credentials via the standard SDK chain (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`); `region` is required even though MinIO ignores it

Defaults line up for a clean round-trip: the exporter's `otlp_json` marshaler writes
`.json`, which the receiver auto-detects, and both default to the same
`year=%Y/month=%m/day=%d/hour=%H/minute=%M` partition layout.

## Quick start (round-trip)

```bash
docker compose up -d                       # MinIO + bucket + exporter collector (OTLP -> awss3 -> MinIO)
# send some data, then replay a time window with the receiver:
docker run --rm --network otel-s3-receiver-demo_default \
  ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:latest \
  metrics --otlp-insecure --otlp-endpoint collector-exporter:4317 --metrics 300 --duration 20s
```

MinIO console: http://localhost:9001 (`minioadmin` / `minioadmin`).
`receiver-config.yaml` reads a window via `START_TIME` / `END_TIME` (UTC, `YYYY-MM-DD HH:MM`).
Tear down with `docker compose down -v`.

Files:
- `docker-compose.yml`, `exporter-config.yaml`, `receiver-config.yaml` — the round-trip stack.

## Benchmark (`bench/`)

Datasets are generated **directly into MinIO** as OTLP-JSON objects (byte format
templated from a real awss3exporter object). One 20-minute dataset is generated per
case; the 1/5/10/20-minute durations are measured as sub-windows. File model:
600 objects/min (10/s), capped at datapoints/min. Instrumented via the collector's
internal Prometheus telemetry on `:8888`.

```bash
docker build -f bench/Dockerfile.gen -t benchgen bench     # generator image
python3 bench/run_bench.py          # plain replay matrix (gauges, nop sink)
python3 bench/run_interval.py       # interval(15s) egress-reduction set
python3 bench/run_hist_bench.py     # histogram fan-in: deltatocumulative + interval
python3 bench/run_cardinality.py    # stream-cardinality memory sweep
python3 bench/analyze.py            # -> results/report.html + results_corrected.csv
```

Open `bench/results/report.html` for charts (Chart.js via CDN, needs internet).

### Key findings

**Plain replay is object-bound, memory O(1).** Read time and CPU track the number of
S3 objects; datapoint volume inside objects is nearly free; peak RSS is flat ~190–205 MB
from 100 objects to 800k datapoints. Cost model: `~158 µs/object + 0.47 µs/datapoint`.
Data is lossless (`refused=0`). Note: `otelcol_receiver_accepted_metric_points` in the
awss3receiver counts **objects**, not datapoints.

**Reducing egress with the interval processor** (`interval: 15s`) collapses output to one
sample per series per tick, at negligible CPU/RSS cost. On fast replay everything lands
in one wall-clock bucket, so a historical read collapses to one point per series total
(the processor is wall-clock based, not data-timestamp based).

**Histogram fan-in** (`awss3receiver -> deltatocumulative -> interval`) merges delta
histograms from many "lambdas" (same series) into one aggregate per stream. Lossless
(verified: 5 lambdas [1,2,3,4]…[5,6,7,8] → merged [15,20,25,30], count 90). Aggregation
shifts cost toward datapoints: `~167 µs/object + 3.07 µs/datapoint` (~7× the gauge cost
per datapoint). Memory is O(streams), not observation volume.

**Stream-cardinality sweep:** peak RSS is flat to ~10k streams (~224 MB), then climbs at
~2.4 KB/stream, reaching ~441 MB at 100k streams. Budget ~`200 MB + 2.4 KB × streams`
and cap with `deltatocumulative.max_streams`.

**Caveat — ordering:** `deltatocumulative` requires each stream's delta samples in
increasing time order. Objects written by many lambdas can arrive out of order across S3
keys and get silently dropped as `delta.ErrOutOfOrder` — watch
`otelcol_deltatocumulative_datapoints{error="delta.ErrOutOfOrder"}`.

### bench/ layout
- `gen.py`, `gen_hist.py`, `gen_hist_bench.py` + `Dockerfile.gen` — direct-to-MinIO generators
- `bench-receiver-config.yaml` (nop), `bench-receiver-interval-config.yaml`,
  `bench-receiver-histagg-config.yaml` — measured pipelines
- `run_bench.py`, `run_interval.py`, `run_hist_bench.py`, `run_cardinality.py`, `analyze.py`
- `results/` — summary CSVs, per-run timeseries, `report.html` (per-run `logs/` are gitignored)
