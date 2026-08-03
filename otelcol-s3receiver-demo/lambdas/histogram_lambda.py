"""Local stand-in for an AWS Lambda that emits a **delta histogram**.

Each invocation writes ONE delta histogram sample to S3 as an
awss3exporter-format OTLP-JSON object. ``deltatocumulative`` merges the
per-invocation bucket counts of the same series bucket-wise downstream.

Invoke it locally like AWS would::

    handler({"invocation": 3, "bucketCounts": [3, 4, 5, 6], "bounds": [1.0, 5.0, 10.0]})
"""
from lambdas.otlp import delta_histogram, put_metric

METRIC = "demo_request_latency"


def handler(event, context=None):
    k = event["invocation"]
    key = put_metric(
        METRIC,
        delta_histogram(METRIC, event["bucketCounts"], event["bounds"], k),
        k,
    )
    return {"key": key, "metric": METRIC, "bucketCounts": event["bucketCounts"]}
