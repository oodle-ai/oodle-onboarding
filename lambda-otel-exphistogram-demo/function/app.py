"""Lambda handler that reports its request latency as a gauge.

Each invocation handles one request and sets the gauge once. The SDK runs
with delta temporality, and the Python layer's wrapper (/opt/otel-instrument)
flushes the meter provider when the invocation ends. So every invocation
sends exactly one gauge data point to the collector extension.

The latency comes from the event so the test driver knows the true value of
every data point.
"""

from opentelemetry import metrics

meter = metrics.get_meter("lambda-exphist-demo")
latency = meter.create_gauge(
    "lambda.request.latency",
    unit="ms",
    description="Latency of the request that this invocation handled.",
)


def handler(event, context):
    latency.set(
        float(event["latency_ms"]),
        {"http.route": event.get("route", "/checkout"), "run_id": event["run_id"]},
    )
    return {"statusCode": 200}
