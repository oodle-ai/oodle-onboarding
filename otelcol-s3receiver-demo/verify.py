#!/usr/bin/env python3
"""End-to-end correctness check for the lambda -> S3 -> collector -> stdout demo.

Steps:
  1. bring up MinIO and create the bucket
  2. build + run the lambda image, fanning K delta samples of each metric into S3
  3. replay the window through the collector
     (awss3receiver -> deltatocumulative -> interval -> debug/stdout), capturing output
  4. parse the debug output and assert the merged cumulative values match expectation

Exit code 0 == PASS.

Env overrides: COLLECTOR_IMAGE, K.
"""
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
NET = "otel-s3-demo"
K = int(os.environ.get("K", "5"))
COLLECTOR_IMAGE = os.environ.get(
    "COLLECTOR_IMAGE", "otel/opentelemetry-collector-contrib:0.155.0"
)
COLLECTOR_NAME = "otel-demo-collector"

# Expected merged results for K (must match run_lambdas.py's inputs).
EXP_SUM = sum(range(1, K + 1))
EXP_BUCKETS = [sum(j + i for j in range(1, K + 1)) for i in range(4)]
EXP_COUNT = sum(EXP_BUCKETS)


# Publish MinIO on non-default host ports so the demo never collides with another
# local S3/MinIO stack. Correctness does not depend on these — the collector and
# lambdas reach MinIO over the internal Docker network at minio:9000.
COMPOSE_ENV = {
    **os.environ,
    "MINIO_API_PORT": os.environ.get("MINIO_API_PORT", "19000"),
    "MINIO_CONSOLE_PORT": os.environ.get("MINIO_CONSOLE_PORT", "19001"),
}


def run(cmd, **kw):
    print(f"$ {' '.join(cmd)}", flush=True)
    kw.setdefault("env", COMPOSE_ENV)
    return subprocess.run(cmd, cwd=HERE, **kw)


def block_after_last(text, marker):
    """Return the text block starting at the LAST occurrence of ``marker`` up to
    the next metric boundary (so we read the final emitted cumulative value)."""
    idxs = [m.start() for m in re.finditer(re.escape(marker), text)]
    if not idxs:
        return None
    start = idxs[-1]
    nxt = text.find("Metric #", start + len(marker))
    return text[start : nxt if nxt != -1 else len(text)]


def assert_results(output):
    failures = []

    cblock = block_after_last(output, "Name: demo_requests_total")
    if not cblock:
        failures.append("counter demo_requests_total not found in output")
    else:
        m = re.search(r"Value:\s*([0-9.]+)", cblock)
        got = int(float(m.group(1))) if m else None
        if got != EXP_SUM:
            failures.append(f"counter total: got {got}, expected {EXP_SUM}")
        else:
            print(f"  [ok] counter demo_requests_total = {got}")

    hblock = block_after_last(output, "Name: demo_request_latency")
    if not hblock:
        failures.append("histogram demo_request_latency not found in output")
    else:
        cm = re.search(r"Count:\s*(\d+)", hblock)
        count = int(cm.group(1)) if cm else None
        buckets = [
            int(m.group(1))
            for m in re.finditer(r"Buckets #\d+, Count:\s*(\d+)", hblock)
        ]
        if count != EXP_COUNT:
            failures.append(f"histogram count: got {count}, expected {EXP_COUNT}")
        if buckets != EXP_BUCKETS:
            failures.append(f"histogram buckets: got {buckets}, expected {EXP_BUCKETS}")
        if count == EXP_COUNT and buckets == EXP_BUCKETS:
            print(f"  [ok] histogram demo_request_latency count={count} buckets={buckets}")

    return failures


def main():
    try:
        run(["docker", "compose", "up", "-d", "minio"], check=True)
        run(["docker", "compose", "run", "--rm", "createbucket"], check=True)

        run(
            ["docker", "build", "-f", "Dockerfile.lambda", "-t", "otel-demo-lambda", "."],
            check=True,
        )
        run(
            [
                "docker", "run", "--rm", "--network", NET,
                "-e", "MINIO_ENDPOINT=minio:9000",
                "otel-demo-lambda", str(K),
            ],
            check=True,
        )

        print("\n--- replaying window through collector (capturing ~30s) ---\n", flush=True)
        run(["docker", "rm", "-f", COLLECTOR_NAME], stderr=subprocess.DEVNULL)
        proc = subprocess.Popen(
            [
                "docker", "run", "--rm", "--name", COLLECTOR_NAME, "--network", NET,
                "-e", "START_TIME=2026-08-01 00:00",
                "-e", "END_TIME=2026-08-01 00:02",
                "-e", "AWS_ACCESS_KEY_ID=minioadmin",
                "-e", "AWS_SECRET_ACCESS_KEY=minioadmin",
                "-v", f"{HERE}/collector-config.yaml:/etc/otelcol-contrib/config.yaml:ro",
                COLLECTOR_IMAGE,
            ],
            cwd=HERE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        lines = []

        def reader():
            for line in proc.stdout:
                lines.append(line)
                sys.stdout.write(line)
                sys.stdout.flush()

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        time.sleep(30)  # >= 2 interval(15s) ticks so a merged sample is flushed
        run(["docker", "stop", COLLECTOR_NAME], stderr=subprocess.DEVNULL)
        t.join(timeout=5)
        output = "".join(lines)

        print("\n--- assertions ---", flush=True)
        failures = assert_results(output)
        if failures:
            print("\nRESULT: FAIL")
            for f in failures:
                print(f"  [fail] {f}")
            return 1
        print("\nRESULT: PASS  (delta fan-in merged correctly end-to-end)")
        return 0
    finally:
        run(["docker", "rm", "-f", COLLECTOR_NAME], stderr=subprocess.DEVNULL)
        run(["docker", "compose", "down", "-v"], stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    sys.exit(main())
