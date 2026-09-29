# AWS Lambda demo

A Python Lambda function sends metrics, logs, and traces to Oodle
through the OpenTelemetry collector Lambda layer. It deploys the default
setup of the "Push via Extension Layer" tab of the Oodle AWS Lambda
tile: the collector layer, and the Python language layer that loads only
the instrumentations the function needs.

```
Lambda execution environment
+-----------------------------------------------------------+
|  otel/app.py (handler)                                    |
|    OpenTelemetry Python layer                             |
|      traces, metrics, logs ---- OTLP ----+                |
|                                          v                |
|                            collector extension -----------+--> Oodle
|                            (collector layer)              |
+-----------------------------------------------------------+
```

## What arrives in Oodle

| Signal | Example |
|--------|---------|
| Traces | `process_order` with `STS.GetCallerIdentity`, `reserve_inventory`, and `charge_payment` child spans. About 15% of orders fail. |
| Logs | `Order received`, `Payment captured`, `Order failed`, with `order_id`, `trace_id`, and `span_id` attributes. Filter on `log.resources.service_name`. |
| Metrics | `demo_orders` (by `outcome`) and `demo_order_amount`, with `job="oodle-lambda-demo-checkout"`. |

## Requirements

- AWS SAM CLI and the AWS CLI, with credentials for the target account.
- An Oodle API key with the DataIngestion role.

## Run it

```bash
cp .env.example .env
# Set OODLE_INSTANCE, OODLE_API_KEY and OODLE_OTLP_ENDPOINT.
make deploy
make invoke
```

The stack also invokes the function every minute, so data keeps
flowing. Stop the schedule with `make pause`. Remove the stack with
`make destroy`.

To read the extension output, run `make tail`. A line that contains
`Exporting failed` names the HTTP status that Oodle returned.

## Configuration that decides whether data arrives

- `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS`. The Python layer loads every
  instrumentation it contains, and each one adds to every cold start.
  The template disables all of them except two. `aws-lambda` makes the
  invocation span and flushes the SDK. `botocore` traces the AWS calls.
  If your function uses a library on the list, remove its name.
- `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument`. The wrapper starts
  the SDK and flushes it before each invocation ends. Without it, the
  handler's data stays in the SDK buffer.
- `OTEL_LOGS_EXPORTER=otlp` and
  `OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true`. The SDK then
  sends the log records. Fields that the handler gives in `extra`
  become log attributes, and each record links to its trace.
- The `decouple` processor, last in each pipeline of `collector.yaml`.
  Without it, the collector's pipeline is synchronous, and the
  function's response waits for the export to Oodle.
- Memory and timeout. The layers add work to each cold start. With the
  Lambda defaults of 128 MB and 3 seconds, the first invocation in a new
  environment timed out. This demo uses 256 MB and 30 seconds.

## Files

| File | Purpose |
|------|---------|
| `template.yaml` | SAM stack: the function, both layers, the environment variables, and the schedule |
| `otel/app.py` | Handler that emits spans, metrics, and logs |
| `otel/collector.yaml` | Collector configuration. The Oodle tile generates the same file, with the endpoint and instance written in. |
