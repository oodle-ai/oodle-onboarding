"""Simple MCP server exposing tools for the OpenLit demo.

Instrumented with OpenLit so server-side spans are also exported to Oodle.
"""

import os
from datetime import datetime, timezone

import openlit
from ddgs import DDGS
from mcp.server.fastmcp import FastMCP

openlit.init(
    otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"),
    application_name="openlit-mcp-server",
)

mcp = FastMCP("openlit-demo-tools", host="0.0.0.0", port=8080)


def _web_search(query: str, max_results: int = 5) -> list[dict]:
    """Run a DuckDuckGo web search and return results."""
    return DDGS().text(query, max_results=max_results)


@mcp.tool()
def duckduckgo_web_search(query: str) -> str:
    """Search the web for information matching the query.

    Performs a live DuckDuckGo search and returns the top results
    with titles, snippets, and source URLs.
    """
    try:
        results = _web_search(query)
    except Exception as exc:
        return f"Web search failed: {exc}"

    if not results:
        return "No results found."

    formatted = []
    for r in results:
        title = r.get("title", "")
        body = r.get("body", "")
        href = r.get("href", "")
        formatted.append(f"**{title}**\n{body}\nSource: {href}")

    return "\n\n---\n\n".join(formatted)


@mcp.tool()
def get_current_time() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    mcp.run(transport="sse")
