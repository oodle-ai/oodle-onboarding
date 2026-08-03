# Lambda delta metrics → S3 → collector (deltatocumulative + interval) → stdout

A minimal, self-contained demo of the pattern where many short-lived **AWS
Lambda** functions emit **delta** metrics as objects into an **S3 bucket** (in
the exact format the collector's `awss3exporter` writes), and a single
**OpenTelemetry Collector** reads them back with `awss3receiver`, merges the
per-invocation deltas into cumulative series with `deltatocumulative`, thins
them with the `interval` processor, and prints the result to **stdout**.

```
 lambdas (local)            S3 (MinIO)                collector
 ┌───────────────┐  delta   ┌──────────┐  awss3       ┌──────────────────────────────┐
 │ counter_lambda│ ───────► │  otel/   │ ───receiver► │ deltatocumulative → interval │ ─► stdout
 │ histogram_… │           │ telemetry│              │        (debug exporter)      │
 └───────────────┘          └──────────┘              └──────────────────────────────┘
```

Two metrics only:
- `demo_requests_total` — a **delta monotonic counter** (a Sum).
- `demo_request_latency` — a **delta histogram**.

## Why delta → cumulative

Each Lambda invocation is stateless: it knows only *its own* contribution, so it
emits a **delta** (this invocation added N; its histogram observed these
buckets). Written to S3 they are many small delta objects for the *same* series.
`deltatocumulative` sums those deltas back into a running total, and `interval`
emits one merged sample per series per tick — which on a fast historical replay
is just the final merged value.

## Layout

| File | Role |
|------|------|
| `docker-compose.yml` | MinIO (the "S3 bucket") + one-shot bucket creation |
| `lambdas/otlp.py` | builds awss3exporter-format OTLP-JSON objects and PUTs them to S3 |
| `lambdas/counter_lambda.py` | `handler()` → 1 delta counter object per invocation |
| `lambdas/histogram_lambda.py` | `handler()` → 1 delta histogram object per invocation |
| `run_lambdas.py` | invokes both handlers K times, fanning deltas into S3 |
| `collector-config.yaml` | `awss3receiver → deltatocumulative → interval → debug` |
| `verify.py` | drives the whole thing and asserts the merged output |

## Run the end-to-end check

Requires Docker (Compose v2). No local Python deps — the lambdas run in a
container.

```bash
python3 verify.py
```

It brings up MinIO, fans `K=5` invocations of each lambda into S3, replays the
window through the collector, and asserts the merged output:

```
counter   invocation k -> delta = k          -> cumulative demo_requests_total = 15
histogram invocation k -> [k, k+1, k+2, k+3] -> merged demo_request_latency
                                                 buckets=[15, 20, 25, 30] count=90
```

Prints `RESULT: PASS` and exits 0 on success. Set `K=<n>` to change the fan-in
count (expected values are recomputed).

## Run the pieces by hand

```bash
docker compose up -d minio
docker compose run --rm createbucket

# fan delta samples into S3
docker build -f Dockerfile.lambda -t otel-demo-lambda .
docker run --rm --network otel-s3-demo -e MINIO_ENDPOINT=minio:9000 otel-demo-lambda 5

# replay the window to stdout
docker run --rm --network otel-s3-demo \
  -e "START_TIME=2026-08-01 00:00" -e "END_TIME=2026-08-01 00:02" \
  -e AWS_ACCESS_KEY_ID=minioadmin -e AWS_SECRET_ACCESS_KEY=minioadmin \
  -v "$PWD/collector-config.yaml:/etc/otelcol-contrib/config.yaml:ro" \
  otel/opentelemetry-collector-contrib:0.155.0

docker compose down -v
```

MinIO console: http://localhost:9001 (`minioadmin` / `minioadmin`).

## Notes / caveats

- **Ordering matters.** `deltatocumulative` requires each stream's delta samples
  in increasing time order and silently drops out-of-order ones as
  `delta.ErrOutOfOrder`. Object keys are zero-padded (`counter_001.json`, …) so
  lexical key order matches timestamp order.
- **`interval` is wall-clock based**, not data-timestamp based. A fast replay
  lands all samples in one tick, so output collapses to the final merged value
  per series — exactly what the assertion checks.
- This is adapted from the `awss3` exporter/receiver + MinIO benchmark in
  oodle-onboarding PR #23; the OTLP-JSON byte format is templated from a real
  `awss3exporter` object.
