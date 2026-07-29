"""Shared infrastructure for Swiggy Builders Demo.

MCP server factory, OpenTelemetry setup, and token refresh helper.
"""

import os

from agents.mcp import MCPServerStreamableHttp
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.openai_agents import (
    OpenAIAgentsInstrumentor,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SWIGGY_FOOD_URL = "https://mcp.swiggy.com/food"
SWIGGY_IM_URL = "https://mcp.swiggy.com/im"
SWIGGY_DINEOUT_URL = "https://mcp.swiggy.com/dineout"


def setup_opentelemetry():
    """Configure OTel tracing with OTLP export to Oodle."""
    resource = Resource.create(
        {"service.name": "swiggy-builders-demo"}
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter())
    )
    trace.set_tracer_provider(provider)
    OpenAIAgentsInstrumentor().instrument(tracer_provider=provider)


def get_swiggy_token() -> str:
    """Read the Swiggy access token from the environment."""
    token = os.environ.get("SWIGGY_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError(
            "SWIGGY_ACCESS_TOKEN not set. Run `make auth` first."
        )
    return token


def create_food_server(token: str) -> MCPServerStreamableHttp:
    """Create Swiggy Food MCP server connection."""
    return MCPServerStreamableHttp(
        name="SwiggyFood",
        params={
            "url": SWIGGY_FOOD_URL,
            "headers": {"Authorization": f"Bearer {token}"},
        },
        cache_tools_list=True,
        max_retry_attempts=2,
    )


def create_instamart_server(token: str) -> MCPServerStreamableHttp:
    """Create Swiggy Instamart MCP server connection."""
    return MCPServerStreamableHttp(
        name="SwiggyInstamart",
        params={
            "url": SWIGGY_IM_URL,
            "headers": {"Authorization": f"Bearer {token}"},
        },
        cache_tools_list=True,
        max_retry_attempts=2,
    )


def create_dineout_server(token: str) -> MCPServerStreamableHttp:
    """Create Swiggy Dineout MCP server connection."""
    return MCPServerStreamableHttp(
        name="SwiggyDineout",
        params={
            "url": SWIGGY_DINEOUT_URL,
            "headers": {"Authorization": f"Bearer {token}"},
        },
        cache_tools_list=True,
        max_retry_attempts=2,
    )


async def run_with_reauth(runner_fn, reauth_fn=None):
    """Execute an agent run, retrying once on 401/token expiry.

    Args:
        runner_fn: Async callable that performs the agent run.
        reauth_fn: Optional async callable that refreshes the token.
                   If None, raises on auth failure.
    """
    try:
        return await runner_fn()
    except Exception as e:
        err_str = str(e)
        is_swiggy_auth_error = (
            "-32001" in err_str
            or ("401" in err_str and "swiggy" in err_str.lower())
            or "invalid_token" in err_str
            or "Authentication required" in err_str
        )
        if is_swiggy_auth_error:
            if reauth_fn:
                await reauth_fn()
                return await runner_fn()
            raise RuntimeError(
                "Swiggy token expired. Run `make auth` to refresh."
            ) from e
        raise
