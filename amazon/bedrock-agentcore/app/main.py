"""AgentCore Runtime entrypoint; also serves /ping and /invocations locally."""

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from opentelemetry import baggage, context as otel_context

from telemetry import setup_telemetry

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
provider = setup_telemetry("amazon-bedrock-agentcore-demo")

from bedrock_agentcore.runtime import BedrockAgentCoreApp  # noqa: E402
from support_agent import DEFAULT_PROMPT, run_agent  # noqa: E402
from check_tools import run_tool_checks  # noqa: E402


@asynccontextmanager
async def lifespan(app):
    try:
        yield
    finally:
        provider.shutdown()


app = BedrockAgentCoreApp(lifespan=lifespan)


@app.entrypoint
def invoke(payload, context):
    session_id = context.session_id or str(uuid.uuid4())
    # Set session.id as baggage so the BaggageSpanProcessor copies it to every
    # child span in this turn, matching the guide's trace-context pattern.
    ctx = baggage.set_baggage("session.id", session_id)
    token = otel_context.attach(ctx)
    try:
        if payload.get("mode") == "tool-check":
            return run_tool_checks(session_id)
        return run_agent(payload.get("prompt", DEFAULT_PROMPT), session_id)
    finally:
        otel_context.detach(token)
        # Runtime can suspend the process after responding. Export before return.
        provider.force_flush(timeout_millis=10000)


if __name__ == "__main__":
    app.run()
