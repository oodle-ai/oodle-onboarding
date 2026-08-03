#!/usr/bin/env python3
"""Stream-cardinality sweep: how does deltatocumulative+interval memory/CPU scale
with the number of unique streams? Fixes ~2 delta datapoints per stream (one create
+ one merge) and 600 objects, varying the stream count so RSS isolates per-stream cost.
"""
import subprocess, time, os, csv, urllib.request
from datetime import datetime

NET = "otel-s3-receiver-demo_default"
IMG = "otel/opentelemetry-collector-contrib:latest"
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "bench-receiver-histagg-config.yaml")
GEN = os.path.join(HERE, "gen_hist_bench.py")
RES = os.path.join(HERE, "results")
SCRAPE = "http://localhost:18888/metrics"
SERIES = [100, 1000, 10000, 100000]
RATE, MIN, CAP = 2, 1, 600


def sh(a): return subprocess.run(a, capture_output=True, text=True)


def mc_clear():
    sh(["docker", "run", "--rm", "--network", NET, "--entrypoint", "/bin/sh",
        "minio/mc:latest", "-c",
        "mc alias set local http://minio:9000 minioadmin minioadmin >/dev/null 2>&1 && "
        "mc rm --recursive --force local/otel >/dev/null 2>&1; true"])


def scrape():
    try:
        t = urllib.request.urlopen(SCRAPE, timeout=2).read().decode()
    except Exception:
        return None
    o = {"cpu": 0.0, "rss": 0.0, "proc": 0.0, "streams": 0.0}
    for ln in t.splitlines():
        if ln.startswith("#"):
            continue
        name = ln.split(" ")[0]; base = name.split("{")[0]
        try:
            v = float(ln.split(" ")[-1])
        except ValueError:
            continue
        if base == "otelcol_process_cpu_seconds":
            o["cpu"] = v
        elif base == "otelcol_process_memory_rss":
            o["rss"] = v
        elif base == "otelcol_deltatocumulative_datapoints" and "error=" not in name:
            o["proc"] = v
        elif base == "otelcol_deltatocumulative_streams_tracked":
            o["streams"] = v
    return o


def parse_wall(log):
    s = f = None
    for ln in log.splitlines():
        tok = ln.split("\t", 1)[0]
        if "Start reading telemetry" in ln and s is None:
            s = tok
        if "Finished reading telemetry" in ln:
            f = tok
    if not (s and f):
        return None
    p = lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))
    return (p(f) - p(s)).total_seconds()


def measure(s):
    sh(["docker", "run", "--rm", "--network", NET, "-v", f"{GEN}:/g.py:ro",
        "--entrypoint", "python", "benchgen", "/g.py", str(s), str(RATE), str(MIN), str(CAP)])
    sh(["docker", "rm", "-f", "bench-receiver"])
    sh(["docker", "run", "-d", "--name", "bench-receiver", "--network", NET,
        "-e", "AWS_ACCESS_KEY_ID=minioadmin", "-e", "AWS_SECRET_ACCESS_KEY=minioadmin",
        "-e", "AWS_REGION=us-east-1",
        "-e", "START_TIME=2026-08-01 00:00", "-e", "END_TIME=2026-08-01 00:01",
        "-p", "18888:8888", "-v", f"{CFG}:/etc/otel/config.yaml:ro",
        IMG, "--config=/etc/otel/config.yaml"])
    rss_series, last = [], None
    t0 = time.time()
    while time.time() - t0 < 300:
        sm = scrape()
        if sm:
            rss_series.append(sm["rss"]); last = sm
        log = sh(["docker", "logs", "bench-receiver"]).stdout + \
            sh(["docker", "logs", "bench-receiver"]).stderr
        if "Finished reading telemetry" in log:
            for _ in range(8):
                sm = scrape()
                if sm:
                    rss_series.append(sm["rss"]); last = sm
                time.sleep(0.3)
            break
        time.sleep(0.3)
    log = sh(["docker", "logs", "bench-receiver"]).stdout + \
        sh(["docker", "logs", "bench-receiver"]).stderr
    sh(["docker", "rm", "-f", "bench-receiver"])
    wall = parse_wall(log)
    peak = max(rss_series) if rss_series else 0.0
    row = {
        "streams": int(last["streams"]) if last else 0,
        "datapoints": int(last["proc"]) if last else 0,
        "objects": min(CAP, s * RATE),
        "read_wall_s": round(wall, 3) if wall else "",
        "cpu_seconds": round(last["cpu"], 3) if last else "",
        "peak_rss_mb": round(peak / 1e6, 1),
    }
    print(f"   requested_series={s:<7} streams_tracked={row['streams']:<7} "
          f"dp={row['datapoints']:<7} wall={row['read_wall_s']}s "
          f"cpu={row['cpu_seconds']}s peakRSS={row['peak_rss_mb']}MB")
    return row


def main():
    rows = []
    for s in SERIES:
        print(f"[sweep] target streams={s}")
        mc_clear(); rows.append(measure(s)); mc_clear()
    with open(os.path.join(RES, "results_cardinality.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\nDONE {len(rows)} rows -> results_cardinality.csv")


if __name__ == "__main__":
    main()
