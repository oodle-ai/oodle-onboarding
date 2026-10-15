"""A Claude Managed Agents session, traced from both ends.

SDK tracing (this process): an anthropic.sessions.* CLIENT span for each
Sessions API request the SDK sends, under this app's own span.

API tracing (Anthropic's side, needs scripts/create-destination.sh): the
SERVER span of each of those requests, and under the one that started the
work, an anthropic.session.turn span with the turn's model requests and the
tools the agent ran in its sandbox. Turns and sandbox tools are visible only
through API tracing; the SDK sees requests, not what the agent does.

Usage: python main.py ["task for the agent"]
"""

import os
import sys

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Register the tracer provider before the first Claude call.
provider = TracerProvider(
    resource=Resource.create(
        {"service.name": os.environ.get("OTEL_SERVICE_NAME", "claude-otel-managed-agents")}
    )
)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("claude-otel-managed-agents")

import anthropic  # noqa: E402

TASK = (
    "Generate 1,000 samples from a normal distribution with mean 50 and "
    "standard deviation 10 using a fixed seed of 7, then report the sample "
    "mean, standard deviation, and how many samples fall above 70."
)


def run(client: anthropic.Anthropic, session_id: str, task: str) -> None:
    """Send the task and print events until the agent is done."""
    # Open the stream first: it only delivers events that happen after it opens.
    with client.beta.sessions.events.stream(session_id=session_id) as stream:
        client.beta.sessions.events.send(
            session_id=session_id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": task}]}],
        )
        for event in stream:
            if event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(block.text, end="", flush=True)
            elif event.type in ("agent.tool_use", "agent.mcp_tool_use"):
                print(f"\n[tool] {event.name}", flush=True)
                if event.evaluated_permission == "ask":
                    # Nobody is watching this run, so a call that needs approval is denied.
                    client.beta.sessions.events.send(
                        session_id=session_id,
                        events=[{"type": "user.tool_confirmation", "tool_use_id": event.id, "result": "deny"}],
                    )
            elif event.type == "session.status_idle":
                if event.stop_reason.type != "requires_action":
                    break
            elif event.type == "session.status_terminated":
                break
    print()


def main() -> None:
    agent_id = os.environ.get("MANAGED_AGENT_ID")
    environment_id = os.environ.get("MANAGED_ENVIRONMENT_ID")
    if not agent_id or not environment_id:
        sys.exit("Set MANAGED_AGENT_ID and MANAGED_ENVIRONMENT_ID in .env (run `make managed-agents-setup`).")
    task = " ".join(sys.argv[1:]) or TASK

    client = anthropic.Anthropic()
    with tracer.start_as_current_span("demo.managed_agent_task") as span:
        session = client.beta.sessions.create(
            agent=agent_id,
            environment_id=environment_id,
            title="claude-opentelemetry-demo",
        )
        span.set_attribute("anthropic.session.id", session.id)
        print(f"session={session.id}")
        run(client, session.id, task)
        print(f"trace_id={span.get_span_context().trace_id:032x}")
        print(f"Console: https://platform.claude.com/workspaces/default/sessions/{session.id}")
    provider.shutdown()


if __name__ == "__main__":
    main()
