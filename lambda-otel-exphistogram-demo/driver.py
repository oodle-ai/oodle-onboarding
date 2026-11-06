"""Invoke the Lambda execution environments with known latencies.

Every invocation carries the latency the handler reports, so the driver knows
the exact value behind every gauge point. The latencies follow a lognormal
body (median 120 ms) with a 5% slow tail (median 900 ms), which is the shape
where quantile error matters.

The invocations are spread evenly over DURATION_S seconds so the gateway's
15s interval processor emits several times during the run.

Writes /out/truth.json with every value sent.

Env: RUN_ID, LAMBDA_ENVS (4), INVOCATIONS (2000), DURATION_S (120), SEED (42),
LAMBDA_HOST_PREFIX (lambda-exphist-demo-lambda-).
"""

import json
import os
import random
import sys
import threading
import time
import urllib.request

RUN_ID = os.environ["RUN_ID"]
ENVS = int(os.environ.get("LAMBDA_ENVS", "4"))
N = int(os.environ.get("INVOCATIONS", "2000"))
DURATION_S = float(os.environ.get("DURATION_S", "120"))
SEED = int(os.environ.get("SEED", "42"))
PREFIX = os.environ.get("LAMBDA_HOST_PREFIX", "lambda-exphist-demo-lambda-")
PATH = "/2015-03-31/functions/function/invocations"


def latencies(n, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        if rng.random() < 0.05:
            v = rng.lognormvariate(6.8, 0.4)  # slow tail, median ~900 ms
        else:
            v = rng.lognormvariate(4.79, 0.45)  # body, median ~120 ms
        out.append(round(v, 3))
    return out


def invoke(env, payload):
    url = f"http://{PREFIX}{env}:8080{PATH}"
    body = json.dumps(payload).encode()
    for attempt in range(30):
        try:
            req = urllib.request.Request(url, data=body, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                r.read()
                return
        except OSError as e:  # environment still starting
            if attempt == 29:
                raise
            time.sleep(1)


def main():
    values = latencies(N, SEED)
    per_env = [values[i::ENVS] for i in range(ENVS)]
    errors = []
    start = time.time()

    def worker(env_idx):
        vals = per_env[env_idx]
        gap = DURATION_S / max(len(vals), 1)
        for j, v in enumerate(vals):
            target = start + j * gap + env_idx * gap / ENVS
            delay = target - time.time()
            if delay > 0:
                time.sleep(delay)
            try:
                invoke(env_idx + 1, {"latency_ms": v, "run_id": RUN_ID})
            except Exception as e:  # noqa: BLE001
                errors.append(f"env {env_idx + 1}: {e}")
                return

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(ENVS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        print("invocation errors:", *errors, sep="\n  ", file=sys.stderr)
        sys.exit(1)

    with open("/out/truth.json", "w") as f:
        json.dump({"run_id": RUN_ID, "envs": ENVS, "values": values}, f)
    print(
        f"invoked {N} times across {ENVS} environments in "
        f"{time.time() - start:.0f}s, run_id={RUN_ID}",
        flush=True,
    )


if __name__ == "__main__":
    main()
