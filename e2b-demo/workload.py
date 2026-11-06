# /// script
# requires-python = ">=3.10"
# dependencies = ["e2b>=2.0", "python-dotenv"]
# ///
"""Start E2B sandboxes and put CPU, memory and disk load on them.

E2B exports sandbox metrics (e2b.sandbox.*) and lifecycle logs over OTLP
only while sandboxes run. This script gives that export something to show:
each sandbox goes through a CPU phase, a memory phase and a disk phase, and
one sandbox is paused and resumed to add those lifecycle events.
"""

import argparse
import concurrent.futures
import time

from dotenv import load_dotenv
from e2b import Sandbox

load_dotenv()

# Each phase runs inside the sandbox as a shell command. They use only
# tools in the base template, so no custom template is necessary.
PHASES = {
    # Keep every vCPU busy.
    "cpu": "for i in $(seq $(nproc)); do timeout {secs} sh -c 'while :; do :; done' & done; wait",
    # Hold about 256 MiB of anonymous memory.
    "memory": "python3 -c \"import time; b=bytearray(256*1024*1024); time.sleep({secs})\"",
    # Write files to the sandbox disk, then hold them so disk.used stays up.
    "disk": "dd if=/dev/urandom of=/tmp/fill bs=1M count=512 status=none && sleep {secs}",
}


def run_sandbox(index: int, phase_secs: int, pause: bool) -> str:
    sbx = Sandbox.create(
        timeout=phase_secs * len(PHASES) + 300,
        metadata={"app": "oodle-e2b-demo", "worker": str(index)},
    )
    print(f"[{index}] started sandbox {sbx.sandbox_id}", flush=True)
    try:
        for name, cmd in PHASES.items():
            print(f"[{index}] phase {name} for {phase_secs}s", flush=True)
            sbx.commands.run(cmd.format(secs=phase_secs), timeout=phase_secs + 120)
            if pause and name == "cpu":
                # A pause and a resume give the lifecycle logs two more
                # event types than a plain create and kill.
                print(f"[{index}] pausing {sbx.sandbox_id}", flush=True)
                sbx.beta_pause()
                time.sleep(20)
                sbx = Sandbox.connect(sbx.sandbox_id)
                print(f"[{index}] resumed {sbx.sandbox_id}", flush=True)
    finally:
        sbx.kill()
        print(f"[{index}] killed sandbox {sbx.sandbox_id}", flush=True)
    return sbx.sandbox_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandboxes", type=int, default=3, help="sandboxes per round")
    parser.add_argument("--phase-secs", type=int, default=60, help="seconds per load phase")
    parser.add_argument("--rounds", type=int, default=1, help="rounds to run, 0 runs until stopped")
    args = parser.parse_args()

    rnd = 0
    while args.rounds == 0 or rnd < args.rounds:
        rnd += 1
        print(f"round {rnd}: {args.sandboxes} sandboxes", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.sandboxes) as pool:
            futures = [
                pool.submit(run_sandbox, i, args.phase_secs, pause=(i == 0))
                for i in range(args.sandboxes)
            ]
            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except Exception as exc:  # Keep the other workers running.
                    print(f"worker failed: {exc}", flush=True)


if __name__ == "__main__":
    main()
