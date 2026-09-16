"""The one human gate: promote the candidate prompt, or don't.

    python approve.py status
    python approve.py approve
    python approve.py reject
    python approve.py stop      terminate the improver, so nothing drafts unattended
"""

import asyncio
import json
import os
import sys

from temporalio.client import Client

IMPROVER_ID = "prompt-improver"


async def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    client = await Client.connect(os.environ.get("TEMPORAL_HOST", "temporal:7233"))
    handle = client.get_workflow_handle(IMPROVER_ID)

    if action == "status":
        try:
            print(json.dumps(await handle.query("state"), indent=2))
        except Exception as exc:
            # A query needs a live run and a worker to answer it. "Timeout expired"
            # here means the improver is not running, or was continuing-as-new faster
            # than the query could land on a run.
            print(f"Could not read the improver's state: {exc}\n"
                  f"Is it running? `make improver` starts one; the Temporal UI at "
                  f"http://localhost:8083 shows the workflow either way.")
            sys.exit(1)
        return

    if action == "stop":
        try:
            await handle.terminate("stopped by hand")
            print("Improver terminated. `make improver` starts a fresh one.")
        except Exception as exc:
            print(f"Nothing to stop: {exc}")
        return

    if action not in ("approve", "reject"):
        sys.exit(f"unknown action {action!r}; use status, approve, reject or stop")

    await handle.signal("decide", action)
    print(f"Sent {action}.")


if __name__ == "__main__":
    asyncio.run(main())
