#!/usr/bin/env python3
"""Benchmark awss3receiver CPU/memory/throughput while replaying MinIO datasets.

Matrix: metric_count in {1,10} x rate/min/metric in {100,1000,2000,3000,4000}.
For each (metric_count,rate) a single 20-minute dataset is generated once; the
1/5/10/20-minute durations are measured by pointing the receiver at sub-windows.
File model: min(600, metric_count*rate) files per minute (10 files/sec cap).

Instrument: collector internal Prometheus telemetry on :8888 (host :18888).
  - otelcol_receiver_accepted_metric_points  -> samples processed (== emitted, nop sink)
  - otelcol_process_cpu_seconds              -> cumulative process CPU
  - otelcol_process_memory_rss               -> RSS (sampled -> peak/avg)
Read wall time is taken from the receiver's own "Start/Finished reading telemetry" logs.

Outputs (bench/results/):
  results.csv                 one row per (metric_count,rate,duration)
  timeseries/<case>.csv       0.3s-sampled cpu/rss/accepted during each run
  logs/<case>.log             full receiver log for that run
"""
import subprocess, time, os, re, csv, sys, urllib.request
from datetime import datetime

NET = "otel-s3-receiver-demo_default"
IMG = "otel/opentelemetry-collector-contrib:latest"
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "bench-receiver-config.yaml")
RESULTS = os.path.join(HERE, "results")
TSDIR = os.path.join(RESULTS, "timeseries")
LOGDIR = os.path.join(RESULTS, "logs")
SCRAPE_URL = "http://localhost:18888/metrics"

METRIC_COUNTS = [1, 10]
RATES = [100, 1000, 2000, 3000, 4000]
DURATIONS = [1, 5, 10, 20]
CAP = 600
GEN_MINUTES = 20
POLL_S = 0.3
RUN_TIMEOUT_S = 900

for d in (RESULTS, TSDIR, LOGDIR):
    os.makedirs(d, exist_ok=True)


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def mc_clear():
    sh(["docker", "run", "--rm", "--network", NET, "--entrypoint", "/bin/sh",
        "minio/mc:latest", "-c",
        "mc alias set local http://minio:9000 minioadmin minioadmin >/dev/null 2>&1 && "
        "mc rm --recursive --force local/otel >/dev/null 2>&1; true"])


def generate(mc, rate):
    r = sh(["docker", "run", "--rm", "--network", NET, "benchgen",
            str(mc), str(rate), str(GEN_MINUTES), str(CAP)])
    print("   " + r.stdout.strip().replace("\n", " | "))


FAMILIES = {
    "cpu": "otelcol_process_cpu_seconds",
    "rss": "otelcol_process_memory_rss",
    "accepted": "otelcol_receiver_accepted_metric_points",
}


def scrape():
    """Return dict cpu/rss/accepted from /metrics, or None if not up yet."""
    try:
        text = urllib.request.urlopen(SCRAPE_URL, timeout=2).read().decode()
    except Exception:
        return None
    out = {"cpu": 0.0, "rss": 0.0, "accepted": 0.0}
    for line in text.splitlines():
        if line.startswith("#") or " " not in line:
            continue
        name, _, val = line.partition(" ")
        base = name.split("{", 1)[0]
        try:
            v = float(val)
        except ValueError:
            continue
        for key, fam in FAMILIES.items():
            if base == fam or base == fam + "_total" or base == fam + "_bytes":
                if key == "accepted":
                    out[key] += v      # sum across label sets
                else:
                    out[key] = v
    return out


def parse_wall(log):
    start = finish = None
    for line in log.splitlines():
        tok = line.split("\t", 1)[0]
        if "Start reading telemetry" in line and start is None:
            start = tok
        if "Finished reading telemetry" in line:
            finish = tok
    if not (start and finish):
        return None
    fmt = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (fmt(finish) - fmt(start)).total_seconds()


def expected(mc, rate, dur):
    files = min(CAP, mc * rate) * dur
    samples = mc * rate * dur
    return files, samples


def measure(mc, rate, dur):
    name = f"m{mc}_r{rate}_d{dur}"
    start_t = "2026-08-01 00:00"
    end_t = f"2026-08-01 00:{dur:02d}"
    sh(["docker", "rm", "-f", "bench-receiver"])
    sh(["docker", "run", "-d", "--name", "bench-receiver", "--network", NET,
        "-e", "AWS_ACCESS_KEY_ID=minioadmin", "-e", "AWS_SECRET_ACCESS_KEY=minioadmin",
        "-e", "AWS_REGION=us-east-1",
        "-e", f"START_TIME={start_t}", "-e", f"END_TIME={end_t}",
        "-p", "18888:8888",
        "-v", f"{CFG}:/etc/otel/config.yaml:ro",
        IMG, "--config=/etc/otel/config.yaml"])

    ts_path = os.path.join(TSDIR, name + ".csv")
    tsf = open(ts_path, "w", newline="")
    tw = csv.writer(tsf)
    tw.writerow(["epoch", "cpu_seconds", "rss_bytes", "accepted"])
    rss_series, last = [], None
    t0 = time.time()
    while time.time() - t0 < RUN_TIMEOUT_S:
        s = scrape()
        if s:
            tw.writerow([f"{time.time():.3f}", s["cpu"], s["rss"], s["accepted"]])
            rss_series.append(s["rss"])
            last = s
        lg = sh(["docker", "logs", "bench-receiver"])
        log = lg.stdout + lg.stderr
        if "Finished reading telemetry" in log:
            # Fast local reads can finish before :8888 is even serving; retry the
            # final scrape until the endpoint responds so we don't record zeros.
            for _ in range(20):
                s = scrape()
                if s and s["accepted"] > 0:
                    tw.writerow([f"{time.time():.3f}", s["cpu"], s["rss"], s["accepted"]])
                    rss_series.append(s["rss"])
                    last = s
                    break
                time.sleep(0.3)
            break
        time.sleep(POLL_S)
    tsf.close()

    lg = sh(["docker", "logs", "bench-receiver"])
    log = lg.stdout + lg.stderr
    open(os.path.join(LOGDIR, name + ".log"), "w").write(log)
    sh(["docker", "rm", "-f", "bench-receiver"])

    wall = parse_wall(log)
    exp_files, exp_samples = expected(mc, rate, dur)
    samples = int(last["accepted"]) if last else 0
    cpu = last["cpu"] if last else 0.0
    peak_rss = max(rss_series) if rss_series else 0.0
    avg_rss = sum(rss_series) / len(rss_series) if rss_series else 0.0
    thr = samples / (wall / 60.0) if wall and wall > 0 else 0.0
    cores = cpu / wall if wall and wall > 0 else 0.0
    row = {
        "metric_count": mc, "rate_per_metric": rate,
        "total_rate_per_min": mc * rate, "duration_min": dur,
        "expected_files": exp_files, "expected_samples": exp_samples,
        "samples_read": samples,
        "read_wall_s": round(wall, 3) if wall else "",
        "throughput_samples_per_min": round(thr, 1),
        "cpu_seconds": round(cpu, 3),
        "avg_cores": round(cores, 3),
        "peak_rss_mb": round(peak_rss / 1e6, 1),
        "avg_rss_mb": round(avg_rss / 1e6, 1),
    }
    print(f"   {name:>14}  files={exp_files:<6} samples={samples:<7} "
          f"wall={row['read_wall_s']}s thr={row['throughput_samples_per_min']}/min "
          f"cpu={row['cpu_seconds']}s peakRSS={row['peak_rss_mb']}MB")
    return row


def main():
    fields = ["metric_count", "rate_per_metric", "total_rate_per_min", "duration_min",
              "expected_files", "expected_samples", "samples_read", "read_wall_s",
              "throughput_samples_per_min", "cpu_seconds", "avg_cores",
              "peak_rss_mb", "avg_rss_mb"]
    rows = []
    csv_path = os.path.join(RESULTS, "results.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for mc in METRIC_COUNTS:
            for rate in RATES:
                print(f"[dataset] metric_count={mc} rate={rate}/min "
                      f"(files/min={min(CAP, mc*rate)})")
                mc_clear()
                generate(mc, rate)
                for dur in DURATIONS:
                    r = measure(mc, rate, dur)
                    rows.append(r)
                    w.writerow(r)
                    f.flush()
                mc_clear()
    print(f"\nDONE. {len(rows)} rows -> {csv_path}")


if __name__ == "__main__":
    main()
