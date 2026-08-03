#!/usr/bin/env python3
"""Benchmark CPU/memory of awss3receiver -> deltatocumulative -> interval -> nop
for the histogram fan-in scenario (crawler_msg_file_count from many 'lambdas').

Matrix: series_count in {1,10} (== streams deltatocumulative/interval hold state for)
        x rate/min/series in {100,1000,2000,3000,4000} x duration {1,5,10,20} min.
File model: 600 objects/min (capped at datapoints/min). 11-bucket delta histograms.

Measures read-phase CPU (otelcol_process_cpu_seconds) and peak RSS
(otelcol_process_memory_rss) while cumulative state + interval buffer are held.
Integrity via deltatocumulative counters (processed / out-of-order / streams).
"""
import subprocess, time, os, re, csv, urllib.request
from datetime import datetime

NET = "otel-s3-receiver-demo_default"
IMG = "otel/opentelemetry-collector-contrib:latest"
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "bench-receiver-histagg-config.yaml")
GEN = os.path.join(HERE, "gen_hist_bench.py")
RES = os.path.join(HERE, "results")
TSDIR = os.path.join(RES, "timeseries_hist")
SCRAPE = "http://localhost:18888/metrics"
SERIES = [1, 10]
RATES = [100, 1000, 2000, 3000, 4000]
DURATIONS = [1, 5, 10, 20]
CAP, GEN_MIN = 600, 20
os.makedirs(TSDIR, exist_ok=True)


def sh(a): return subprocess.run(a, capture_output=True, text=True)


def mc_clear():
    sh(["docker", "run", "--rm", "--network", NET, "--entrypoint", "/bin/sh",
        "minio/mc:latest", "-c",
        "mc alias set local http://minio:9000 minioadmin minioadmin >/dev/null 2>&1 && "
        "mc rm --recursive --force local/otel >/dev/null 2>&1; true"])


def generate(s, rate):
    r = sh(["docker", "run", "--rm", "--network", NET, "-v", f"{GEN}:/g.py:ro",
            "--entrypoint", "python", "benchgen", "/g.py",
            str(s), str(rate), str(GEN_MIN), str(CAP)])
    print("   " + r.stdout.strip().replace("\n", " | "))


def scrape():
    try:
        t = urllib.request.urlopen(SCRAPE, timeout=2).read().decode()
    except Exception:
        return None
    out = {"cpu": 0.0, "rss": 0.0, "proc": 0.0, "ooo": 0.0, "streams": 0.0}
    for ln in t.splitlines():
        if ln.startswith("#"):
            continue
        name = ln.split(" ")[0]
        base = name.split("{")[0]
        try:
            v = float(ln.split(" ")[-1])
        except ValueError:
            continue
        if base == "otelcol_process_cpu_seconds":
            out["cpu"] = v
        elif base == "otelcol_process_memory_rss":
            out["rss"] = v
        elif base == "otelcol_deltatocumulative_datapoints":
            if "error=" in name:
                if "OutOfOrder" in name:
                    out["ooo"] += v
            else:
                out["proc"] = v
        elif base == "otelcol_deltatocumulative_streams_tracked":
            out["streams"] = v
    return out


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


def measure(s, rate, dur):
    name = f"s{s}_r{rate}_d{dur}"
    sh(["docker", "rm", "-f", "bench-receiver"])
    sh(["docker", "run", "-d", "--name", "bench-receiver", "--network", NET,
        "-e", "AWS_ACCESS_KEY_ID=minioadmin", "-e", "AWS_SECRET_ACCESS_KEY=minioadmin",
        "-e", "AWS_REGION=us-east-1",
        "-e", "START_TIME=2026-08-01 00:00", "-e", f"END_TIME=2026-08-01 00:{dur:02d}",
        "-p", "18888:8888", "-v", f"{CFG}:/etc/otel/config.yaml:ro",
        IMG, "--config=/etc/otel/config.yaml"])

    ts = open(os.path.join(TSDIR, name + ".csv"), "w", newline="")
    tw = csv.writer(ts); tw.writerow(["epoch", "cpu_seconds", "rss_bytes", "processed"])
    rss_series, last = [], None
    t0 = time.time()
    finished = False
    while time.time() - t0 < 180:
        sm = scrape()
        if sm:
            tw.writerow([f"{time.time():.3f}", sm["cpu"], sm["rss"], sm["proc"]])
            rss_series.append(sm["rss"]); last = sm
        log = sh(["docker", "logs", "bench-receiver"]).stdout + \
            sh(["docker", "logs", "bench-receiver"]).stderr
        if "Finished reading telemetry" in log:
            finished = True
            # settle ~2s to capture peak RSS with cumulative+interval state held
            for _ in range(6):
                sm = scrape()
                if sm:
                    tw.writerow([f"{time.time():.3f}", sm["cpu"], sm["rss"], sm["proc"]])
                    rss_series.append(sm["rss"]); last = sm
                time.sleep(0.3)
            break
        time.sleep(0.3)
    ts.close()

    log = sh(["docker", "logs", "bench-receiver"]).stdout + \
        sh(["docker", "logs", "bench-receiver"]).stderr
    sh(["docker", "rm", "-f", "bench-receiver"])

    wall = parse_wall(log)
    objects = min(CAP, s * rate) * dur
    datapoints = s * rate * dur
    cpu = last["cpu"] if last else 0.0
    peak = max(rss_series) if rss_series else 0.0
    avg = sum(rss_series) / len(rss_series) if rss_series else 0.0
    row = {
        "series": s, "rate_per_series": rate, "duration_min": dur,
        "objects": objects, "datapoints": datapoints,
        "dtc_processed": int(last["proc"]) if last else 0,
        "dtc_out_of_order": int(last["ooo"]) if last else 0,
        "streams_tracked": int(last["streams"]) if last else 0,
        "read_wall_s": round(wall, 3) if wall else "",
        "cpu_seconds": round(cpu, 3),
        "avg_cores": round(cpu / wall, 3) if wall else "",
        "peak_rss_mb": round(peak / 1e6, 1),
        "avg_rss_mb": round(avg / 1e6, 1),
    }
    print(f"   {name:>12} obj={objects:<6} dp={datapoints:<7} "
          f"proc={row['dtc_processed']:<7} ooo={row['dtc_out_of_order']} "
          f"streams={row['streams_tracked']} wall={row['read_wall_s']}s "
          f"cpu={row['cpu_seconds']}s peakRSS={row['peak_rss_mb']}MB")
    return row


def main():
    rows = []
    fields = ["series", "rate_per_series", "duration_min", "objects", "datapoints",
              "dtc_processed", "dtc_out_of_order", "streams_tracked", "read_wall_s",
              "cpu_seconds", "avg_cores", "peak_rss_mb", "avg_rss_mb"]
    out = os.path.join(RES, "results_histagg.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for s in SERIES:
            for rate in RATES:
                print(f"[dataset] series={s} rate={rate} (files/min={min(CAP, s*rate)})")
                mc_clear(); generate(s, rate)
                for d in DURATIONS:
                    r = measure(s, rate, d); rows.append(r); w.writerow(r); f.flush()
                mc_clear()
    print(f"\nDONE {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
