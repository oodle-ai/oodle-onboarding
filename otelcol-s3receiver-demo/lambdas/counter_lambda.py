"""Local stand-in for an AWS Lambda that emits a **delta counter**.

Each invocation writes ONE delta monotonic-sum sample to S3 as an
awss3exporter-format OTLP-JSON object. Fanning many invocations of the same
series into S3 is exactly what ``deltatocumulative`` merges back into a running
total downstream.

Invoke it locally like AWS would::

    handler({"invocation": 3, "delta": 3})
"""
from lambdas.otlp import delta_sum, put_metric

METRIC = "demo_requests_total"


def handler(event, context=None):
    k = event["invocation"]
    delta = event["delta"]
    key = put_metric(METRIC, delta_sum(METRIC, delta, k), k)
    return {"key": key, "metric": METRIC, "delta": delta}
