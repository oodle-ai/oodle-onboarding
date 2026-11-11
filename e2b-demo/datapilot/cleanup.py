# /// script
# requires-python = ">=3.10"
# dependencies = ["e2b>=2.4", "python-dotenv"]
# ///
"""Kill every running DataPilot sandbox, including the ones the agent leaked."""

from pathlib import Path

from dotenv import load_dotenv
from e2b import Sandbox, SandboxQuery

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

killed = 0
paginator = Sandbox.list(query=SandboxQuery(metadata={"app": "datapilot"}))
while paginator.has_next:
    for info in paginator.next_items():
        Sandbox.kill(info.sandbox_id)
        killed += 1
        print(f"killed {info.sandbox_id} tenant={info.metadata.get('tenant')}")
print(f"{killed} sandboxes killed")
