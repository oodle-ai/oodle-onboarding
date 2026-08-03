#!/usr/bin/env python3
"""Write 5 delta-histogram objects to MinIO, one per 'lambda', sharing one series
identity (attribute crawler=msg) but with distinct bucket counts so a correct
merge can only be the bucket-wise SUM.

lambda k (k=1..5): bucketCounts = [k, k+1, k+2, k+3]
  k=1 [1,2,3,4]  k=2 [2,3,4,5]  k=3 [3,4,5,6]  k=4 [4,5,6,7]  k=5 [5,6,7,8]
expected aggregate bucketCounts = [15, 20, 25, 30], total count = 90
"""
import io, json
from datetime import datetime, timezone
from minio import Minio

client = Minio("minio:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)
BUCKET = "otel"
base = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
base_ns = int(base.timestamp()) * 1_000_000_000
bounds = [1.0, 5.0, 10.0]           # -> 4 buckets: (-inf,1] (1,5] (5,10] (10,+inf)
N = 5

for k in range(1, N + 1):
    counts = [k, k + 1, k + 2, k + 3]
    total = sum(counts)
    dp = {
        "startTimeUnixNano": str(base_ns + (k - 1) * 1_000_000_000),
        "timeUnixNano": str(base_ns + k * 1_000_000_000),
        "count": str(total),
        "sum": float(total),
        "bucketCounts": [str(c) for c in counts],
        "explicitBounds": bounds,
        "attributes": [{"key": "crawler", "value": {"stringValue": "msg"}}],
    }
    metric = {"name": "crawler_msg_file_count",
              "histogram": {"aggregationTemporality": 1,   # 1 = DELTA
                            "dataPoints": [dp]}}
    doc = {"resourceMetrics": [{
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": "crawler"}}]},
        "scopeMetrics": [{"scope": {"name": "lambda"}, "metrics": [metric]}],
        "schemaUrl": "https://opentelemetry.io/schemas/1.40.0"}]}
    b = json.dumps(doc, separators=(",", ":")).encode()
    key = f"telemetry/year=2026/month=08/day=01/hour=00/minute=00/metrics_lambda_{k:02d}.json"
    client.put_object(BUCKET, key, io.BytesIO(b), length=len(b),
                      content_type="application/json")
    print(f"lambda {k}: bucketCounts={counts} count={total}")

print("EXPECTED merged: bucketCounts=[15,20,25,30] count=90")
