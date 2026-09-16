"""Drive the agent by hand. Nothing here runs on its own.

Every model call in this demo comes from a command you type, which matters on a
free Gemini key where the daily allowance is small.

    python starter.py ticket [T-1001]   one ticket (default: the first)
    python starter.py all               each of the four tickets, once
    python starter.py improver          start the improver

This also owns the root span of each run, so the whole run - every model call and
every tool call, across every Activity - lands in ONE trace under one
`invoke_agent` span. Temporal's tracing interceptor carries the context through.
"""

import asyncio
import json
import logging
import os
import sys
import time

import otel
from opentelemetry.trace import Status, StatusCode
from temporalio.client import Client
from temporalio.contrib.opentelemetry import TracingInterceptor
from temporalio.exceptions import WorkflowAlreadyStartedError
from tools import TICKETS

SERVICE_NAME = os.environ.get("STARTER_SERVICE_NAME", "support-agent-gateway")
TASK_QUEUE = "self-improving-loop"

log = logging.getLogger("starter")


async def submit(client: Client, ticket: dict) -> None:
    span_name = f"invoke_agent {otel.AGENT_NAME}"
    with otel.tracer().start_as_current_span(span_name) as span:
        span.set_attribute("gen_ai.operation.name", "invoke_agent")
        span.set_attribute("gen_ai.agent.name", otel.AGENT_NAME)
        span.set_attribute("session.id", ticket["id"])
        span.set_attribute("gen_ai.conversation.id", ticket["id"])
        span.set_attribute(
            "gen_ai.input.messages",
            json.dumps([{"role": "user", "parts": [{"type": "text", "content": ticket["text"]}]}]),
        )
        try:
            result = await client.execute_workflow(
                "SupportAgentWorkflow",
                ticket,
                id=f"ticket-{ticket['id']}-{int(time.time())}",
                task_queue=TASK_QUEUE,
            )
        except Exception as exc:
            # Temporal wraps the real reason two or three levels down, and the
            # outermost message is always "Workflow execution failed".
            cause = exc
            while getattr(cause, "cause", None):
                cause = cause.cause
            span.set_status(Status(StatusCode.ERROR, str(cause)))
            log.warning("Ticket %s failed: %s", ticket["id"], cause)
            return

        span.set_attribute("prompt_version", str(result["prompt_version"]))
        span.set_attribute("gen_ai.output.messages", json.dumps(
            [{"role": "assistant", "parts": [{"type": "text", "content": result["reply"] or ""}]}]
        ))
        # Not an error status: the agent got there in the end, just expensively.
        # The failing tool spans are what Oodle picks up on.
        span.set_attribute("agent.tool_errors", result["tool_errors"])
        span.set_attribute("agent.turns", result["turns"])
        log.info(
            "Ticket %s on prompt v%d: %d turns, %d bad tool calls",
            ticket["id"], result["prompt_version"], result["turns"], result["tool_errors"],
        )


async def start_improver(client: Client) -> None:
    try:
        await client.start_workflow(
            "PromptImproverWorkflow", id="prompt-improver", task_queue=TASK_QUEUE
        )
        log.info("Improver started. It watches Oodle, and spends tokens once a "
                 "finding appears: one draft call, then the gate.")
    except WorkflowAlreadyStartedError:
        log.info("Improver already running")


async def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "ticket"
    runtime = otel.setup(SERVICE_NAME)
    client = await Client.connect(
        os.environ.get("TEMPORAL_HOST", "temporal:7233"),
        interceptors=[TracingInterceptor()],
        runtime=runtime,
    )

    if command == "improver":
        await start_improver(client)

    elif command == "ticket":
        wanted = sys.argv[2] if len(sys.argv) > 2 else TICKETS[0]["id"]
        ticket = next((t for t in TICKETS if t["id"] == wanted), None)
        if ticket is None:
            sys.exit(f"no ticket {wanted!r}; have {[t['id'] for t in TICKETS]}")
        await submit(client, ticket)

    elif command == "all":
        for ticket in TICKETS:
            await submit(client, ticket)

    else:
        sys.exit(f"unknown command {command!r}; use ticket, all or improver")

    # Flush, or the root span dies with the process before the batch exporter ticks.
    otel.flush()


if __name__ == "__main__":
    asyncio.run(main())
