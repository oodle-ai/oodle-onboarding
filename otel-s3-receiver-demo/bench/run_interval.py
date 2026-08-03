#!/usr/bin/env python3
"""Measure awss3receiver -> interval(15s) -> debug, capturing egress reduction.

The interval processor aggregates each gauge series to its last value per 15s
wall-clock tick. Because replay is faster than real time, all data lands in one
bucket and collapses to one point per series (= metric_count here, since the
synthetic series carry no distinguishing attributes). We measure:
  datapoints_in  (generated, lossless baseline)
  datapoints_sent (summed from the debug sink's per-batch "data points")
  read CPU / peak RSS (from internal telemetry; note accepted counter reads 0
    when the interval processor is present, so we use expected object counts).
"""
import subprocess, time, os, re, csv, json, urllib.request
from datetime import datetime

NET = "otel-s3-receiver-demo_default"
IMG = "otel/opentelemetry-collector-contrib:latest"
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "bench-receiver-interval-config.yaml")
RES = os.path.join(HERE, "results")
SCRAPE = "http://localhost:18888/metrics"
CAP, GEN_MIN = 600, 20

# (metric_count, rate) -> durations to measure (sub-windows of one 20-min dataset)
PLAN = {
    (1, 100): [20],
    (1, 4000): [1, 20],
    (10, 100): [20],
    (10, 4000): [1, 20],
}


def sh(a): return subprocess.run(a, capture_output=True, text=True)


def mc_clear():
    sh(["docker", "run", "--rm", "--network", NET, "--entrypoint", "/bin/sh",
        "minio/mc:latest", "-c",
        "mc alias set local http://minio:9000 minioadmin minioadmin >/dev/null 2>&1 && "
        "mc rm --recursive --force local/otel >/dev/null 2>&1; true"])


def generate(mc, rate):
    sh(["docker", "run", "--rm", "--network", NET, "benchgen",
        str(mc), str(rate), str(GEN_MIN), str(CAP)])


def scrape():
    try:
        t = urllib.request.urlopen(SCRAPE, timeout=2).read().decode()
    except Exception:
        return None
    cpu = rss = 0.0
    for ln in t.splitlines():
        if ln.startswith("#"):
            continue
        b = ln.split("{")[0].split(" ")[0]
        try:
            v = float(ln.split(" ")[-1])
        except ValueError:
            continue
        if b == "otelcol_process_cpu_seconds":
            cpu = v
        elif b == "otelcol_process_memory_rss":
            rss = v
    return cpu, rss


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


def sent_points(log):
    return sum(int(x) for x in re.findall(r'"data points": (\d+)', log))


def measure(mc, rate, dur):
    sh(["docker", "rm", "-f", "bench-receiver"])
    sh(["docker", "run", "-d", "--name", "bench-receiver", "--network", NET,
        "-e", "AWS_ACCESS_KEY_ID=minioadmin", "-e", "AWS_SECRET_ACCESS_KEY=minioadmin",
        "-e", "AWS_REGION=us-east-1",
        "-e", "START_TIME=2026-08-01 00:00", "-e", f"END_TIME=2026-08-01 00:{dur:02d}",
        "-p", "18888:8888", "-v", f"{CFG}:/etc/otel/config.yaml:ro",
        IMG, "--config=/etc/otel/config.yaml"])

    cpu_read = rss_peak = 0.0
    t0 = time.time()
    while time.time() - t0 < 120:            # read phase
        s = scrape()
        if s:
            cpu_read, rss = s
            rss_peak = max(rss_peak, rss)
        log = sh(["docker", "logs", "bench-receiver"]).stdout + \
            sh(["docker", "logs", "bench-receiver"]).stderr
        if "Finished reading telemetry" in log:
            s = scrape()
            if s:
                cpu_read, rss = s
                rss_peak = max(rss_peak, rss)
            break
        time.sleep(0.3)

    # wait for the interval flush (non-empty emit) after the read
    t1 = time.time()
    while time.time() - t1 < 22:
        log = sh(["docker", "logs", "bench-receiver"]).stdout
        if re.search(r'"data points": [1-9]', log):
            break
        time.sleep(1)
    time.sleep(1)
    log = sh(["docker", "logs", "bench-receiver"]).stdout + \
        sh(["docker", "logs", "bench-receiver"]).stderr
    sh(["docker", "rm", "-f", "bench-receiver"])

    wall = parse_wall(log)
    objects = min(CAP, mc * rate) * dur
    dp_in = mc * rate * dur
    dp_sent = sent_points(log)
    row = {
        "metric_count": mc, "rate_per_metric": rate, "duration_min": dur,
        "objects": objects, "datapoints_in": dp_in, "datapoints_sent": dp_sent,
        "reduction_x": round(dp_in / dp_sent) if dp_sent else "inf",
        "read_wall_s": round(wall, 3) if wall else "",
        "read_cpu_seconds": round(cpu_read, 3),
        "peak_rss_mb": round(rss_peak / 1e6, 1),
    }
    print(f"   m{mc}_r{rate}_d{dur}: in={dp_in:<7} sent={dp_sent:<4} "
          f"reduction={row['reduction_x']}x  read_wall={row['read_wall_s']}s "
          f"cpu={row['read_cpu_seconds']}s peakRSS={row['peak_rss_mb']}MB")
    return row


def main():
    rows = []
    for (mc, rate), durs in PLAN.items():
        print(f"[dataset] metric_count={mc} rate={rate}")
        mc_clear(); generate(mc, rate)
        for d in durs:
            rows.append(measure(mc, rate, d))
        mc_clear()
    fields = list(rows[0].keys())
    with open(os.path.join(RES, "results_interval.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\nwrote results_interval.csv ({len(rows)} rows)")


if __name__ == "__main__":
    main()
