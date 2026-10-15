"""Drive the backend like its web UI does: start a go/no-go session, wait
for the agent, then ask the in-house chat a question.

This script is not traced, like the browser that calls the reference backend.
The trace of each step starts at mcp-app, and the app returns its trace id.

Usage: python run.py [chat question]
"""

import os
import sys
import time

import httpx

APP = os.environ.get("APP_URL", "http://mcp-app:8001")
QUESTION = "Which of our past projects are most like a wastewater plant upgrade, and who led them?"


def wait_ready(http: httpx.Client) -> None:
    for _ in range(60):
        try:
            if http.get(f"{APP}/healthz").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    sys.exit("mcp-app did not come up")


def start_session(http: httpx.Client) -> dict:
    # The quick tunnel takes a few seconds to get a hostname.
    for _ in range(15):
        resp = http.post(f"{APP}/api/managedagents/rfpgonogo/create", json={})
        if resp.status_code != 503:
            break
        time.sleep(4)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    question = " ".join(sys.argv[1:]) or QUESTION
    with httpx.Client(timeout=120) as http:
        wait_ready(http)

        created = start_session(http)
        print(f"agent      {created['agentName']}")
        print(f"session    {created['sessionId']}")
        print(f"mcp url    {created['mcpUrl']}")
        print(f"trace_id   {created['traceId']}  (go/no-go session)")

        status = "running"
        while status == "running":
            time.sleep(10)
            row = http.get(
                f"{APP}/api/managedagents/sessions/read", params={"sessionId": created["sessionId"]}
            ).json()
            status = row["status"]
            print(f"  {row['updated_at']}  {status}  events={row['events']}", flush=True)

        asked = http.post(f"{APP}/api/chatsession/ask", json={"question": question})
        asked.raise_for_status()
        body = asked.json()
        print(f"\n{body['answer']}\n")
        print(f"trace_id   {body['traceId']}  (in-house chat)")


if __name__ == "__main__":
    main()
