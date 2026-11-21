#!/usr/bin/env python3
"""End-to-end accuracy check:

  Lambda (delta gauge per invocation) -> collector extension -> gateway
  (signal_to_metrics -> exponential histogram, deltatocumulative, interval 15s)
  -> Oodle

Steps:
  1. start the gateway and LAMBDA_ENVS Lambda execution environments
  2. invoke them INVOCATIONS times with known latencies (driver.py)
  3. read what the gateway exported (out/exported.jsonl) and check it against
     the truth: exact count and sum, quantiles within the exponential
     histogram's error bound, and a 15s emit cadence
  4. query Oodle for the same series and run the same checks

Quantile error bound: an exponential histogram with scale s has bucket
boundaries base^i with base = 2^(2^-s). The true quantile and the estimate lie
in the same bucket, so the relative error is at most base - 1
(2.2% at scale 5, 4.4% at scale 4).

Exit code 0 == PASS. Needs Docker (Compose v2) and the `oodle` CLI, which reads
OODLE_INSTANCE / OODLE_API_KEY from the environment or ~/.oodle/config.yaml.

Env: LAMBDA_ENVS (4), INVOCATIONS (2000), DURATION_S (120), SEED (42),
SKIP_OODLE (unset), KEEP (unset: leave the stack running).
"""

import json
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
ENVS = int(os.environ.get("LAMBDA_ENVS", "4"))
N = int(os.environ.get("INVOCATIONS", "2000"))
DURATION_S = float(os.environ.get("DURATION_S", "120"))
SEED = os.environ.get("SEED", "42")
INTERVAL_S = 15
METRIC_OTLP = "lambda.request.duration"
METRIC_PROM = "lambda_request_duration"
QUANTILES = [0.5, 0.9, 0.95, 0.99, 0.999]


def run(cmd, **kw):
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=HERE, **kw)


def load_env_file():
    """docker compose reads .env itself; the oodle CLI does not."""
    path = os.path.join(HERE, ".env")
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


# ---------------------------------------------------------------- truth ----


def true_quantile(sorted_vals, q):
    """Same rank rule as histogram_quantile: the ceil(q*n)-th smallest value."""
    rank = max(1, math.ceil(q * len(sorted_vals)))
    return sorted_vals[rank - 1]


# ------------------------------------------------- exponential histogram ----


def exphist_quantile(scale, offset, counts, q):
    """histogram_quantile on an OTLP exponential histogram (positive buckets),
    with the exponential in-bucket interpolation Prometheus uses."""
    base = 2 ** (2**-scale)
    total = sum(counts)
    rank = q * total
    cum = 0
    for i, c in enumerate(counts):
        if c == 0:
            continue
        if cum + c >= rank:
            lo, hi = base ** (offset + i), base ** (offset + i + 1)
            frac = (rank - cum) / c
            return lo * (hi / lo) ** frac
        cum += c
    return base ** (offset + len(counts))


def exported_points(run_id):
    """Every data point of our run_id the gateway exported, in order."""
    pts = []
    path = os.path.join(OUT, "exported.jsonl")
    for line in open(path):
        d = json.loads(line)
        for rm in d.get("resourceMetrics", []):
            for sm in rm.get("scopeMetrics", []):
                for m in sm.get("metrics", []):
                    if m["name"] != METRIC_OTLP:
                        continue
                    for dp in m["exponentialHistogram"]["dataPoints"]:
                        attrs = {
                            a["key"]: a["value"].get("stringValue")
                            for a in dp.get("attributes", [])
                        }
                        if attrs.get("run_id") == run_id:
                            pts.append(dp)
    return pts


# ----------------------------------------------------------------- oodle ----


def oodle_query(promql):
    # Always pass an explicit evaluation time. Without --time, repeating the
    # same query text can return a cached result evaluated at an earlier
    # moment (seen while polling histogram_count during ingestion).
    r = subprocess.run(
        ["oodle", "metrics", "query", "--query", promql,
         "--time", str(int(time.time())), "-o", "json"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"oodle query failed: {r.stderr.strip()}")
    return json.loads(r.stdout)["data"]["result"]


def oodle_scalar(promql):
    res = oodle_query(promql)
    if len(res) != 1:
        return None
    return float(res[0]["value"][1])


def gateway_dropped():
    """Deltas deltatocumulative rejected (it does not log them), read from the
    gateway's own metrics endpoint from inside the compose network."""
    code = (
        "import urllib.request;"
        "print(urllib.request.urlopen('http://gateway:8888/metrics').read().decode())"
    )
    r = subprocess.run(
        ["docker", "compose", "run", "--rm", "--no-deps", "--entrypoint", "python",
         "driver", "-c", code],
        cwd=HERE, capture_output=True, text=True,
    )
    dropped = {}
    for line in r.stdout.splitlines():
        if line.startswith("otelcol_deltatocumulative_datapoints{") and "error=" in line:
            label = line.split('error="', 1)[1].split('"', 1)[0]
            dropped[label] = float(line.rsplit(" ", 1)[1])
    return dropped


# ---------------------------------------------------------------- checks ----


class Report:
    def __init__(self):
        self.failures = []

    def check(self, ok, msg):
        print(f"  [{'ok' if ok else 'FAIL'}] {msg}", flush=True)
        if not ok:
            self.failures.append(msg)


def compare(rep, where, truth, count, total, quantile_fn, bound):
    rep.check(count == len(truth), f"{where}: count {count} == {len(truth)}")
    tsum = sum(truth)
    rel = abs(total - tsum) / tsum
    rep.check(rel < 1e-9, f"{where}: sum {total:.3f} vs {tsum:.3f} (rel err {rel:.1e})")
    print(f"  {'q':>6} {'true ms':>10} {'est ms':>10} {'err':>7}  (bound {bound:.2%})")
    for q in QUANTILES:
        t = true_quantile(truth, q)
        e = quantile_fn(q)
        if e is None:
            rep.check(False, f"{where}: p{q * 100:g} missing")
            continue
        err = (e - t) / t
        ok = abs(err) <= bound + 1e-9
        print(f"  {q:>6} {t:>10.2f} {e:>10.2f} {err:>+7.2%}  {'ok' if ok else 'FAIL'}")
        if not ok:
            rep.failures.append(f"{where}: p{q * 100:g} err {err:+.2%} > {bound:.2%}")


def main():
    load_env_file()
    run_id = f"run{int(time.time())}"
    os.makedirs(OUT, exist_ok=True)
    for f in ("exported.jsonl", "truth.json"):
        p = os.path.join(OUT, f)
        if os.path.exists(p):
            os.remove(p)
    rep = Report()
    try:
        run(["docker", "compose", "up", "-d", "--build", "--scale", f"lambda={ENVS}"],
            check=True)
        run(["docker", "compose", "run", "--rm",
             "-e", f"RUN_ID={run_id}", "-e", f"LAMBDA_ENVS={ENVS}",
             "-e", f"INVOCATIONS={N}", "-e", f"DURATION_S={DURATION_S}",
             "-e", f"SEED={SEED}", "driver"], check=True)
        print(f"\n--- waiting {2 * INTERVAL_S + 5}s for the last interval flush ---",
              flush=True)
        time.sleep(2 * INTERVAL_S + 5)

        truth = sorted(json.load(open(os.path.join(OUT, "truth.json")))["values"])

        # ---- what the gateway exported ----
        print(f"\n--- gateway output (run_id={run_id}) ---")
        pts = exported_points(run_id)
        if not pts:
            rep.check(False, "gateway exported no points for this run")
            return finish(rep)
        last = pts[-1]
        scale = last["scale"]
        bound = 2 ** (2**-scale) - 1
        pos = last.get("positive", {})
        counts = [int(c) for c in pos.get("bucketCounts", [])]
        offset = pos.get("offset", 0)
        print(f"  {len(pts)} points exported, final scale={scale}, "
              f"{len(counts)} buckets, zeroCount={last.get('zeroCount', 0)}")
        compare(rep, "gateway", truth, int(last["count"]), last["sum"],
                lambda q: exphist_quantile(scale, offset, counts, q), bound)

        # A point's timestamp is that of the newest gauge merged into it, so
        # while invocations are steady the points are INTERVAL_S apart. The
        # last one only holds the tail of the run and comes sooner.
        ts = [int(p["timeUnixNano"]) / 1e9 for p in pts]
        gaps = [b - a for a, b in zip(ts, ts[1:])][:-1]
        if gaps:
            off = [g for g in gaps if abs(g - INTERVAL_S) > 1.0]
            rep.check(not off, f"gateway: one export per {INTERVAL_S}s window "
                      f"(gaps {min(gaps):.2f}s..{max(gaps):.2f}s, "
                      f"{len(pts)} exports for a {DURATION_S:.0f}s run)")
        dropped = gateway_dropped()
        rep.check(not dropped, f"gateway: deltatocumulative dropped nothing {dropped or ''}")
        counts_seq = [int(p["count"]) for p in pts]
        rep.check(counts_seq == sorted(counts_seq),
                  f"gateway: cumulative count never decreases {counts_seq}")

        if os.environ.get("SKIP_OODLE"):
            return finish(rep)

        # ---- what Oodle stored ----
        print("\n--- Oodle ---")
        sel = f'{METRIC_PROM}{{run_id="{run_id}"}}'
        got = None
        deadline = time.time() + 180
        while time.time() < deadline:
            got = oodle_scalar(f"histogram_count({sel})")
            if got == len(truth):
                break
            print(f"  waiting for ingestion: histogram_count={got}", flush=True)
            time.sleep(10)
        total = oodle_scalar(f"histogram_sum({sel})")
        compare(rep, "oodle", truth, int(got or 0), total or 0.0,
                lambda q: oodle_scalar(f"histogram_quantile({q}, {sel})"), bound)
        for q in QUANTILES:
            local = exphist_quantile(scale, offset, counts, q)
            remote = oodle_scalar(f"histogram_quantile({q}, {sel})")
            if remote is not None and abs(remote - local) / local > 1e-6:
                print(f"  note: p{q * 100:g} Oodle {remote:.3f} vs gateway {local:.3f}")
        samples = oodle_scalar(f"count_over_time({sel}[30m])")
        if samples is not None:
            rep.check(abs(samples - len(pts)) <= 1,
                      f"oodle: {samples:.0f} samples stored for {len(pts)} exported "
                      f"(one per {INTERVAL_S}s)")
        return finish(rep)
    finally:
        if not os.environ.get("KEEP"):
            run(["docker", "compose", "down"], stderr=subprocess.DEVNULL)


def finish(rep):
    if rep.failures:
        print("\nRESULT: FAIL")
        for f in rep.failures:
            print(f"  - {f}")
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
