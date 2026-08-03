#!/usr/bin/env python3
"""Generate one benchmark dataset directly into MinIO as OTLP-JSON objects.

Byte format is templated from a real awss3exporter object (otlp_json marshaler):
  {"resourceMetrics":[{"resource":{...},"scopeMetrics":[{"scope":{},"metrics":[
     {"name":..,"gauge":{"dataPoints":[{"timeUnixNano":..,"asDouble":..}]}}]}],
   "schemaUrl":".."}]}

Layout matches the receiver's default partition format:
  telemetry/year=2026/month=08/day=01/hour=00/minute=MM/metrics_MM_FFFFF.json

Usage: gen.py <metric_count> <rate_per_min_per_metric> <minutes> <files_per_min_cap>
"""
import sys, io, json, os
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from minio import Minio

MC = int(sys.argv[1])       # metrics per dataset
RATE = int(sys.argv[2])     # samples/min PER metric
MINUTES = int(sys.argv[3])  # sustained minutes (partitions minute=00..MINUTES-1)
CAP = int(sys.argv[4])      # max files per minute

ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
BUCKET = "otel"
client = Minio(ENDPOINT, access_key="minioadmin", secret_key="minioadmin", secure=False)

base = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
base_ns = int(base.timestamp()) * 1_000_000_000
names = [f"bench_metric_{i}" for i in range(MC)]


def build_file(minute, fileidx, dps):
    by_metric = {}
    for midx, seq in dps:
        by_metric.setdefault(midx, []).append(seq)
    metrics = []
    for midx, seqs in by_metric.items():
        points = []
        for seq in seqs:
            # spread timestamps within the minute and vary values so points are distinct
            ts = base_ns + minute * 60_000_000_000 + (seq % 60000) * 1_000_000
            val = float(seq) + 0.5
            points.append({"timeUnixNano": str(ts), "asDouble": val})
        metrics.append({"name": names[midx], "gauge": {"dataPoints": points}})
    doc = {"resourceMetrics": [{
        "resource": {"attributes": [
            {"key": "service.name", "value": {"stringValue": "benchgen"}}]},
        "scopeMetrics": [{"scope": {"name": "benchgen"}, "metrics": metrics}],
        "schemaUrl": "https://opentelemetry.io/schemas/1.40.0"}]}
    b = json.dumps(doc, separators=(",", ":")).encode()
    key = (f"telemetry/year=2026/month=08/day=01/hour=00/"
           f"minute={minute:02d}/metrics_{minute:02d}_{fileidx:05d}.json")
    return key, b


def put(args):
    key, b = args
    client.put_object(BUCKET, key, io.BytesIO(b), length=len(b),
                      content_type="application/json")


tasks = []
for m in range(MINUTES):
    total = MC * RATE
    files = min(CAP, total)
    if files <= 0:
        continue
    slots = [[] for _ in range(files)]
    for i in range(total):
        midx = i % MC          # each metric gets exactly RATE points/min
        seq = i // MC          # 0..RATE-1 within the metric this minute
        slots[i % files].append((midx, seq))
    for fidx, dps in enumerate(slots):
        if dps:
            tasks.append(build_file(m, fidx, dps))

print(f"gen MC={MC} RATE={RATE} MIN={MINUTES} cap={CAP} "
      f"files={len(tasks)} samples={MC*RATE*MINUTES}", flush=True)
with ThreadPoolExecutor(max_workers=32) as ex:
    for _ in ex.map(put, tasks):
        pass
print("upload done", flush=True)
