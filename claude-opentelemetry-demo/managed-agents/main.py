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


def workspace_headers() -> dict[str, str]:
    """An API key not scoped to a workspace must name one on every request."""
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    return {"anthropic-workspace-id": workspace_id} if workspace_id else {}


def run(client: anthropic.Anthropic, session_id: str, task: str, span: trace.Span) -> None:
    """Send the task and print events until the agent is done.

    The event stream reports what the agent does, so the app span records a
    summary of it: one span event per tool call and the session's token
    totals. That much is visible without API tracing. The model requests and
    tool runs as spans of their own come only from API tracing, and the
    totals are deliberately not gen_ai.usage.*, so they aren't counted twice.
    """
    usage = {
        "model_requests": 0,
        "input_tokens": 0,  # uncached input only; cache reads and writes are counted apart
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "output_tokens": 0,
    }
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
                span.add_event("agent.tool_use", {"tool.name": event.name})
                if event.evaluated_permission == "ask":
                    # Nobody is watching this run, so a call that needs approval is denied.
                    client.beta.sessions.events.send(
                        session_id=session_id,
                        events=[{"type": "user.tool_confirmation", "tool_use_id": event.id, "result": "deny"}],
                    )
            elif event.type == "span.model_request_end":
                usage["model_requests"] += 1
                usage["input_tokens"] += event.model_usage.input_tokens
                usage["output_tokens"] += event.model_usage.output_tokens
                usage["cache_read_input_tokens"] += event.model_usage.cache_read_input_tokens
                usage["cache_creation_input_tokens"] += event.model_usage.cache_creation_input_tokens
            elif event.type == "session.status_idle":
                if event.stop_reason.type != "requires_action":
                    span.set_attribute("demo.session.stop_reason", event.stop_reason.type)
                    break
            elif event.type == "session.status_terminated":
                span.set_attribute("demo.session.stop_reason", "terminated")
                break
    for key, value in usage.items():
        span.set_attribute(f"demo.session.{key}", value)
    print()


def main() -> None:
    agent_id = os.environ.get("MANAGED_AGENT_ID")
    environment_id = os.environ.get("MANAGED_ENVIRONMENT_ID")
    if not agent_id or not environment_id:
        sys.exit("Set MANAGED_AGENT_ID and MANAGED_ENVIRONMENT_ID in .env (run `make managed-agents-setup`).")
    task = " ".join(sys.argv[1:]) or TASK

    client = anthropic.Anthropic(default_headers=workspace_headers())
    with tracer.start_as_current_span("demo.managed_agent_task") as span:
        session = client.beta.sessions.create(
            agent=agent_id,
            environment_id=environment_id,
            title="claude-opentelemetry-demo",
        )
        span.set_attribute("anthropic.session.id", session.id)
        print(f"session={session.id}")
        run(client, session.id, task, span)
        print(f"trace_id={span.get_span_context().trace_id:032x}")
        workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID") or "default"
        print(f"Console: https://platform.claude.com/workspaces/{workspace}/sessions/{session.id}")
    provider.shutdown()


if __name__ == "__main__":
    main()
