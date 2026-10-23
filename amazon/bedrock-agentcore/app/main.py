"""AgentCore Runtime entrypoint; also serves /ping and /invocations locally."""

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

from telemetry import setup_telemetry

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
provider = setup_telemetry("amazon-bedrock-agentcore-demo")

from bedrock_agentcore.runtime import BedrockAgentCoreApp  # noqa: E402
from support_agent import DEFAULT_PROMPT, run_agent  # noqa: E402


@asynccontextmanager
async def lifespan(app):
    try:
        yield
    finally:
        provider.shutdown()


app = BedrockAgentCoreApp(lifespan=lifespan)


@app.entrypoint
def invoke(payload, context):
    # The Runtime session identifier is authoritative in the hosted version.
    session_id = context.session_id or str(uuid.uuid4())
    try:
        return run_agent(payload.get("prompt", DEFAULT_PROMPT), session_id)
    finally:
        # Runtime can suspend the process after responding. Export before return.
        provider.force_flush(timeout_millis=10000)


if __name__ == "__main__":
    app.run()
