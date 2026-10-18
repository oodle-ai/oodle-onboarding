"""A Claude Managed Agents session, traced from both ends.

SDK tracing (this process): an anthropic.sessions.* CLIENT span for each
Sessions API request the SDK sends, under this app's own span.

API tracing (Anthropic's side, needs scripts/create-destination.sh): the
SERVER span of each of those requests, and under the one that started the
work, an anthropic.session.turn span with the turn's model requests and the
tools the agent ran in its sandbox. Turns and sandbox tools are visible only
through API tracing; the SDK sees requests, not what the agent does.

Custom tool (this process, plus the warehouse service): the agent's
query_warehouse tool runs here, not in the sandbox. Each call gets an
anthropic.custom_tool_use span, and the warehouse request made inside it
carries traceparent, so the auto-instrumented warehouse's spans join the
same trace under it.

Usage: python main.py ["task for the agent"]
"""

import json
import os
import sys

import httpx
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

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
    "Using the sales warehouse, find each region's 2025 revenue by month and "
    "which region grew the most from Q1 to Q4. Then fit a linear trend to that "
    "region's monthly revenue in Python and project January 2026."
)

# A CLIENT span for each warehouse request, and traceparent on it. The Claude
# SDK sends its requests over httpx2, which this leaves alone.
HTTPXClientInstrumentor().instrument()
warehouse = httpx.Client(base_url=os.environ.get("WAREHOUSE_URL", "http://warehouse:8080"), timeout=30)
RECORD_CONTENT = os.environ.get("ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE") == "content"


def workspace_headers() -> dict[str, str]:
    """An API key not scoped to a workspace must name one on every request."""
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    return {"anthropic-workspace-id": workspace_id} if workspace_id else {}


def query_warehouse(sql: str) -> tuple[str, bool]:
    """POST the SQL to the warehouse. Returns the tool result's text and whether it's an error."""
    try:
        response = warehouse.post("/query", json={"sql": sql})
    except httpx.HTTPError as e:
        return f"warehouse unreachable: {e}", True
    if response.is_success:
        return response.text, False
    try:
        return response.json()["detail"], True
    except (ValueError, KeyError):
        return f"warehouse answered {response.status_code}", True


def call_custom_tool(session_id: str, thread_id: str | None, event) -> dict:
    """Run one agent.custom_tool_use and return the user.custom_tool_result to send.

    The span has the name and attributes the SDK's own tool runners give a
    custom tool, so it reads like theirs in Oodle. Being current while the
    warehouse request runs is what puts the warehouse's spans under it.

    It can't be a child of the anthropic.session.turn that asked for the tool:
    no event carries that span's context, and the turn has already ended
    (stop_reason requires_action) when the tool runs. The tool runs between
    two turns. gen_ai.conversation.id, the session thread id that Anthropic's
    turn and model_request spans carry too, is what ties it to them.
    """
    with tracer.start_as_current_span(
        f"anthropic.custom_tool_use {event.name}",
        attributes={
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.provider.name": "anthropic",
            "gen_ai.tool.name": event.name,
            "gen_ai.tool.call.id": event.id,
            "gen_ai.tool.type": "function",
            "anthropic.session.id": session_id,
            # Set on the event only when a subagent's call is cross-posted to the primary thread.
            "gen_ai.conversation.id": event.session_thread_id or thread_id,
        },
    ) as span:
        if event.name == "query_warehouse":
            text, is_error = query_warehouse(str(event.input.get("sql", "")))
        else:
            text, is_error = f"unknown tool: {event.name}", True
        content = [{"type": "text", "text": text}]
        if RECORD_CONTENT:
            span.set_attribute("gen_ai.tool.call.arguments", json.dumps(event.input))
            span.set_attribute("anthropic.tool_result.content", json.dumps(content))
        if is_error:
            span.set_status(Status(StatusCode.ERROR))
            span.set_attribute("error.type", "tool_error")
        else:
            span.set_status(Status(StatusCode.OK))
    return {"type": "user.custom_tool_result", "custom_tool_use_id": event.id, "content": content, "is_error": is_error}


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
    thread_id = None  # the primary thread, from its first session.thread_status_running
    # Open the stream first: it only delivers events that happen after it opens.
    with client.beta.sessions.events.stream(session_id=session_id) as stream:
        client.beta.sessions.events.send(
            session_id=session_id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": task}]}],
        )
        for event in stream:
            if event.type == "session.thread_status_running":
                thread_id = thread_id or event.session_thread_id
            elif event.type == "agent.message":
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
            elif event.type == "agent.custom_tool_use":
                # The session waits (idle, requires_action) until this result arrives.
                print(f"\n[custom tool] {event.name} {json.dumps(event.input)}", flush=True)
                span.add_event("agent.custom_tool_use", {"tool.name": event.name})
                result = call_custom_tool(session_id, thread_id, event)
                client.beta.sessions.events.send(session_id=session_id, events=[result])
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
