#!/usr/bin/env python3
"""Generate delta-histogram datasets into MinIO for the deltatocumulative+interval
benchmark. Models many 'lambda' emissions of crawler_msg_file_count.

Usage: gen_hist_bench.py <series_count> <rate_per_min_per_series> <minutes> <files_per_min_cap>

series_count = number of distinct streams (attribute crawler=s0..s{S-1}); this is
what deltatocumulative/interval hold state for. rate = delta datapoints per series
per minute. Datapoints are 11-bucket delta histograms sharing per-series identity.
"""
import sys, io, json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from minio import Minio

S = int(sys.argv[1]); RATE = int(sys.argv[2]); MINUTES = int(sys.argv[3]); CAP = int(sys.argv[4])
client = Minio("minio:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)
BUCKET = "otel"
base = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
base_ns = int(base.timestamp()) * 1_000_000_000
BOUNDS = [1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1000.0]  # 10 bounds -> 11 buckets
NB = len(BOUNDS) + 1


def dp(series, ts):
    counts = [(series + j + (ts // 1000)) % 5 for j in range(NB)]
    total = sum(counts)
    return {
        "startTimeUnixNano": str(ts),
        "timeUnixNano": str(ts + 1000),   # 1us contiguous window
        "count": str(total),
        "sum": float(total),
        "bucketCounts": [str(c) for c in counts],
        "explicitBounds": BOUNDS,
        "attributes": [{"key": "crawler", "value": {"stringValue": f"s{series}"}}],
    }


def build_file(minute, fileidx, items):
    # items: list of (series, ts); all share metric name crawler_msg_file_count
    points = [dp(s, ts) for (s, ts) in items]
    doc = {"resourceMetrics": [{
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": "crawler"}}]},
        "scopeMetrics": [{"scope": {"name": "lambda"}, "metrics": [
            {"name": "crawler_msg_file_count",
             "histogram": {"aggregationTemporality": 1, "dataPoints": points}}]}],
        "schemaUrl": "https://opentelemetry.io/schemas/1.40.0"}]}
    b = json.dumps(doc, separators=(",", ":")).encode()
    key = (f"telemetry/year=2026/month=08/day=01/hour=00/"
           f"minute={minute:02d}/metrics_{minute:02d}_{fileidx:05d}.json")
    return key, b


def put(args):
    key, b = args
    client.put_object(BUCKET, key, io.BytesIO(b), length=len(b), content_type="application/json")


tasks = []
for m in range(MINUTES):
    total = S * RATE
    files = min(CAP, total)
    if files <= 0:
        continue
    slots = [[] for _ in range(files)]
    for i in range(total):
        slots[i % files].append(i % S)          # series id, round-robin across files
    # assign timestamps in read order (minute, fileidx, in-file position) so each
    # stream's delta samples are monotonically increasing when read back from S3
    counter = 0
    for fidx in range(files):
        items = []
        for series in slots[fidx]:
            ts = base_ns + m * 60_000_000_000 + counter * 1000
            counter += 1
            items.append((series, ts))
        if items:
            tasks.append(build_file(m, fidx, items))

print(f"gen S={S} RATE={RATE} MIN={MINUTES} cap={CAP} files={len(tasks)} "
      f"datapoints={S*RATE*MINUTES} streams={S}", flush=True)
with ThreadPoolExecutor(max_workers=32) as ex:
    for _ in ex.map(put, tasks):
        pass
print("upload done", flush=True)
