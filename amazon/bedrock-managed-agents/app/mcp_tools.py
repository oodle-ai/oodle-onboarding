"""One allowlisted read-only tool on AWS's managed Knowledge MCP server."""

import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from opentelemetry import trace

ENDPOINT = "https://knowledge-mcp.global.api.aws"
REMOTE_TOOL = "aws___search_documentation"


async def _search(search_phrase):
    # MCP 2.x emits native CLIENT spans and propagates trace context itself.
    # Enrich the enclosing tool span instead of duplicating its RPC spans.
    span = trace.get_current_span()
    span.set_attribute("mcp.server.name", "aws-knowledge")
    span.set_attribute("server.address", "knowledge-mcp.global.api.aws")
    span.set_attribute("mcp.tool.name", REMOTE_TOOL)
    async with asyncio.timeout(45):
        async with streamable_http_client(ENDPOINT) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=30) as session:
                await session.initialize()
                available = await session.list_tools()
                if REMOTE_TOOL not in {tool.name for tool in available.tools}:
                    raise RuntimeError(f"AWS Knowledge MCP does not advertise {REMOTE_TOOL}")
                arguments = {"search_phrase": search_phrase, "limit": 3, "topics": ["reference_documentation"]}
                result = await session.call_tool(REMOTE_TOOL, arguments)
                if result.is_error:
                    raise RuntimeError("AWS Knowledge MCP returned a tool error")
                texts = [block.text for block in result.content if block.type == "text"]
                return {"source": "AWS Knowledge MCP", "results": "\n".join(texts)[:12000]}


def search_aws_docs(search_phrase):
    if not isinstance(search_phrase, str) or not search_phrase.strip() or len(search_phrase) > 1000:
        raise ValueError("search_phrase must contain 1 to 1000 characters")
    try:
        return asyncio.run(_search(search_phrase))
    except Exception as exc:
        # Keep one stable tool error for both Strands and managed-agent return control.
        raise RuntimeError(f"AWS Knowledge MCP search failed: {exc}") from exc
