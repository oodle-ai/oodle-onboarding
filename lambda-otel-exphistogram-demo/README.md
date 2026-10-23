# Lambda latency gauges → exponential histograms → Oodle

This demo checks that request latency from AWS Lambda can reach Oodle as an
accurate histogram, when each invocation reports only a **gauge** and the
histogram is built in an OpenTelemetry Collector:

1. Each Lambda invocation sets a `lambda.request.latency` gauge once. The SDK
   uses delta temporality, and the OpenTelemetry Lambda layers flush it at the
   end of every invocation.
2. A gateway collector turns every gauge point into one observation of an
   **exponential histogram** (`batch` then the `signal_to_metrics`
   connector), and merges the
   per-batch deltas from all execution environments into one cumulative
   series (`deltatocumulative`).
3. The `interval` processor sends that series to Oodle once every **15s**.

`verify.py` runs it end to end with known latencies and compares Oodle's
`histogram_count`, `histogram_sum` and `histogram_quantile` against the
exact values.

```
 Lambda execution environment (x4)                 gateway collector
 ┌──────────────────────────────────────┐          ┌─────────────────────────────┐
 │ app.py: gauge.set(latency)           │          │ batch -> signal_to_metrics  │
 │   Python layer (delta, flush/invoke) │  OTLP    │   gauge -> exp. histogram   │
 │   collector layer (extension) ───────┼────────► │ deltatocumulative           │ ─► Oodle
 └──────────────────────────────────────┘          │ interval 15s                │
                                                   └─────────────────────────────┘
```

## Result

2000 invocations over 4 execution environments in 2 minutes. Latencies are
lognormal around 120 ms with a 5% slow tail around 900 ms. The histogram
settled at scale 4, so a quantile can be off by at most `2^(1/16) - 1 = 4.43%`.

| | true | Oodle | error |
|---|---|---|---|
| count | 2000 | 2000 | exact |
| sum (ms) | 359585.392 | 359585.392 | exact |
| p50 (ms) | 126.37 | 125.94 | -0.34% |
| p90 (ms) | 255.94 | 256.00 | +0.02% |
| p95 (ms) | 485.13 | 490.29 | +1.07% |
| p99 (ms) | 1285.77 | 1313.89 | +2.19% |
| p99.9 (ms) | 1999.80 | 2048.00 | +2.41% |

The gateway sent one point every 15s (9 points for the 2-minute run), and
Oodle stored all 9. Quantiles that Oodle computes agree with the ones computed
from the gateway's own buckets to within 0.02%.

A stress run with 8 environments and 6000 invocations in 30s
(`LAMBDA_ENVS=8 INVOCATIONS=6000 DURATION_S=30 SKIP_OODLE=1`) lost 2 to 5
points per run until the `batch` processor was added in front of
`signal_to_metrics`. With it, the count is exact. See "Ordering" below.

## Run it

Requires Docker with Compose v2, Python 3, and the
[`oodle` CLI](https://docs.oodle.ai), which `verify.py` uses to query.

```bash
cp .env.example .env   # set OODLE_INSTANCE and OODLE_API_KEY
python3 verify.py
```

It prints the gateway check, the Oodle check, and `RESULT: PASS` (exit 0).
Knobs: `LAMBDA_ENVS` (4), `INVOCATIONS` (2000), `DURATION_S` (120), `SEED`
(42), `SKIP_OODLE=1` to check only the collector, `KEEP=1` to leave the
stack running.

Each run tags its series with a fresh `run_id` label. In Oodle:

```promql
histogram_quantile(0.99, lambda_request_duration{run_id="run..."})        # whole run
histogram_quantile(0.99, sum(rate(lambda_request_duration[5m])))          # dashboards
```

## How the Lambda part runs locally

Each `lambda` container is a Lambda execution environment: the AWS Lambda
Python base image (with the Runtime Interface Emulator) plus the public
OpenTelemetry layers `layer-collector/0.23.0` and `layer-python/0.21.0`,
unpacked into `/opt` as Lambda does. The handler, the
`/opt/otel-instrument` wrapper that flushes the SDK, and the collector
extension are the real ones.

The emulator differs from Lambda in one way that matters. It has no
Telemetry API, and in on-demand mode the collector extension waits for the
Telemetry API's `platform.runtimeDone` before it lets an invocation finish,
so every invoke would hang. The containers therefore set
`AWS_LAMBDA_INITIALIZATION_TYPE=lambda-managed-instances`, in which the
extension does not wait, and use `function/collector.emulator.yaml`, which
leaves out the `decouple` processor (in that mode `decouple` never forwards).
On real Lambda, use `function/collector.yaml`, which keeps `decouple`.

## Files

| File | Purpose |
|---|---|
| `function/app.py` | Handler: sets the latency gauge once per invocation |
| `function/collector.yaml` | Extension config for real Lambda: `otlp → decouple → gateway` |
| `function/collector.emulator.yaml` | The same without `decouple`, for the emulator |
| `Dockerfile.lambda` | Lambda base image + the collector and Python layers |
| `gateway-config.yaml` | `batch → signal_to_metrics → deltatocumulative → interval → Oodle` (and a local file) |
| `docker-compose.yml` | Gateway, Lambda environments, driver |
| `driver.py` | Invokes the environments with known latencies, writes `out/truth.json` |
| `verify.py` | Runs everything and checks the gateway output and Oodle |

## Things to know

- **One gauge point per invocation.** The SDK keeps only the last value a
  gauge got between two exports. If one invocation sets the gauge several
  times with the same attributes, only the last value reaches the collector.
  This works because the layer flushes at the end of every invocation and each
  invocation handles one request.
- **Gauges have no temporality** in OTLP; `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta`
  matters for the function's counters and histograms. The Python SDK 1.44 in
  the layer forgets a gauge's value after each export, so a gauge is never
  sent twice.
- **Fan-in is decided by `include_resource_attributes`.** It keeps
  `service.name`, `faas.name` and `cloud.region`, and drops `faas.instance`
  (one per execution environment), so all environments merge into one series.
  Keeping `faas.instance` would give one series per environment.
- **Ordering: keep `batch` in front of `signal_to_metrics`.**
  `signal_to_metrics` stamps each delta it emits with the gateway's
  `time.Now()`, and `deltatocumulative` drops a delta that is not newer than
  the last one for the series, as `delta.ErrOutOfOrder`, without logging it.
  Concurrent OTLP requests race between the stamp and the merge, so without
  `batch` a few points per thousand were lost under load. `batch` hands
  batches to the connector one at a time, so the stamps only go forward, and
  it cuts the number of deltas to merge (31 instead of 6000 in the stress
  run). Watch `otelcol_deltatocumulative_datapoints{error!=""}` on the
  gateway's `:8888/metrics`; `verify.py` fails if it is non-zero.
- **Late data is not lost.** Because the stamp is the gateway's time, data an
  environment sends late (for example after a freeze) is merged into the
  current window instead of being dropped as out of order.
- **One series per gateway replica.** `signal_to_metrics` adds
  `signal_to_metrics.service.instance.id`. With several gateway replicas,
  aggregate with `sum(...)` in queries. A gateway restart starts a new series,
  since `deltatocumulative` keeps its state in memory.
- **`interval` only sends series that changed.** After the last invocation the
  series stops getting points.
- **Bucket resolution.** `max_size: 160` buckets cover the range of the data.
  A wider latency range lowers the scale and raises the error bound
  (scale 3 = 9.05%, scale 5 = 2.19%).
