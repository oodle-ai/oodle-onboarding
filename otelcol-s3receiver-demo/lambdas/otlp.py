"""Build OTLP-JSON metric objects and write them to an S3 bucket in the exact
byte format produced by the opentelemetry-collector-contrib **awss3exporter**
(its ``otlp_json`` marshaler).

One object == one ``.json`` file that the awss3receiver reads back. The key
layout matches the receiver's default partition format
``year=%Y/month=%m/day=%d/hour=%H/minute=%M`` so a round-trip needs zero custom
config.

All samples land in a single fixed partition (minute=00 of 2026-08-01) so the
receiver window can target them deterministically.
"""
import io
import json
import os
from datetime import datetime, timezone

from minio import Minio

BUCKET = os.environ.get("S3_BUCKET", "otel")
PREFIX = os.environ.get("S3_PREFIX", "telemetry")
ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")

# Fixed base instant: every invocation lands in the same minute partition so the
# replay window is a known [00:00, 00:01) range.
BASE = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
BASE_NS = int(BASE.timestamp()) * 1_000_000_000


def _client():
    return Minio(
        ENDPOINT,
        access_key=os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"),
        secret_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        secure=False,
    )


def _key(name, invocation):
    # Zero-padded invocation index -> lexical key order == temporal order.
    # deltatocumulative requires each stream's delta samples in increasing time
    # order and silently drops out-of-order ones (delta.ErrOutOfOrder), so key
    # order must track timestamp order.
    # The awss3receiver lists metric objects under ".../minute=MM/metrics_", so
    # the filename MUST start with the "metrics_" signal prefix or the object is
    # invisible to the receiver.
    return (
        f"{PREFIX}/year=2026/month=08/day=01/hour=00/minute=00/"
        f"metrics_{name}_{invocation:03d}.json"
    )


def _wrap(metric, service="demo"):
    return {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service}}
                    ]
                },
                "scopeMetrics": [
                    {"scope": {"name": "lambda"}, "metrics": [metric]}
                ],
                "schemaUrl": "https://opentelemetry.io/schemas/1.40.0",
            }
        ]
    }


def put_metric(name, metric, invocation):
    """Serialize one metric as an awss3exporter-format object and PUT it to S3."""
    b = json.dumps(_wrap(metric), separators=(",", ":")).encode()
    key = _key(name, invocation)
    _client().put_object(
        BUCKET, key, io.BytesIO(b), length=len(b), content_type="application/json"
    )
    return key


def delta_sum(name, value, invocation, attrs=None):
    """One DELTA monotonic sum datapoint for invocation k over its [k-1, k] window."""
    dp = {
        "startTimeUnixNano": str(BASE_NS + (invocation - 1) * 1_000_000_000),
        "timeUnixNano": str(BASE_NS + invocation * 1_000_000_000),
        "asInt": str(int(value)),
        "attributes": attrs or [],
    }
    return {
        "name": name,
        "sum": {
            "aggregationTemporality": 1,  # 1 = DELTA
            "isMonotonic": True,
            "dataPoints": [dp],
        },
    }


def delta_histogram(name, bucket_counts, bounds, invocation, attrs=None):
    """One DELTA histogram datapoint for invocation k over its [k-1, k] window."""
    total = sum(bucket_counts)
    dp = {
        "startTimeUnixNano": str(BASE_NS + (invocation - 1) * 1_000_000_000),
        "timeUnixNano": str(BASE_NS + invocation * 1_000_000_000),
        "count": str(total),
        "sum": float(total),
        "bucketCounts": [str(c) for c in bucket_counts],
        "explicitBounds": bounds,
        "attributes": attrs or [],
    }
    return {
        "name": name,
        "histogram": {"aggregationTemporality": 1, "dataPoints": [dp]},  # 1 = DELTA
    }
