"""A real Bedrock agent with two read-only tools and fictional order data."""

import os
import uuid

from botocore.config import Config
from opentelemetry import trace
from strands import Agent, tool
from strands.models import BedrockModel

DEFAULT_PROMPT = "Where is order ORD-1001, and can I return it? Check the order and return policy."

ORDERS = {
    "ORD-1001": {"item": "wireless headphones", "status": "delivered", "days_since_delivery": 7},
    "ORD-1002": {"item": "coffee grinder", "status": "in transit", "estimated_delivery": "in 2 days"},
    "ORD-1003": {"item": "desk lamp", "status": "delivered", "days_since_delivery": 45},
}


@tool
def lookup_order(order_id: str) -> dict:
    """Look up a fictional order's delivery status.

    Args:
        order_id: Order identifier, such as ORD-1001. ORD-ERROR simulates a backend outage.
    """
    if order_id == "ORD-ERROR":
        raise RuntimeError("Simulated order backend outage")
    if order_id not in ORDERS:
        raise ValueError(f"Order {order_id} was not found")
    return {"order_id": order_id, **ORDERS[order_id]}


@tool
def get_return_policy() -> dict:
    """Retrieve the fictional store's return policy."""
    return {"return_window_days": 30, "condition": "Item must be undamaged", "shipping": "Free returns"}


def run_agent(prompt: str, session_id: str | None = None, *, model=None) -> dict:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    session_id = session_id or str(uuid.uuid4())
    if not isinstance(session_id, str):
        raise ValueError("session_id must be a string")
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("support.request", attributes={
        "session.id": session_id,
        "gen_ai.conversation.id": session_id,
    }) as span:
        agent = Agent(
            name="order-support-agent",
            model=model or BedrockModel(
                model_id=os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0"),
                region_name=os.environ.get("AWS_REGION", "us-west-2"),
                streaming=False,
                max_tokens=512,
                temperature=0,
                boto_client_config=Config(connect_timeout=10, read_timeout=60, retries={"max_attempts": 2}),
            ),
            tools=[lookup_order, get_return_policy],
            system_prompt=(
                "You are a concise order-support assistant for a fictional store. "
                "Always use lookup_order for order status and get_return_policy for return questions. "
                "Never invent order facts or claim to make changes. On a tool error, explain the problem "
                "without retrying. Answer using only the supplied tool results."
            ),
            callback_handler=None,
            trace_attributes={"session.id": session_id, "gen_ai.conversation.id": session_id},
        )
        result = agent(prompt)
        return {
            "answer": str(result),
            "session_id": session_id,
            "trace_id": format(span.get_span_context().trace_id, "032x"),
        }
