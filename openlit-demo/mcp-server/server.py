"""Simple MCP server exposing tools for the OpenLit demo.

Instrumented with OpenLit so server-side spans are also exported to Oodle.
"""

import logging
import os
from datetime import datetime, timezone

import openlit
from ddgs import DDGS
from mcp.server.fastmcp import FastMCP
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

openlit.init(
    service_name="openlit-mcp-server",
    environment=os.environ.get("OTEL_DEPLOYMENT_ENVIRONMENT", "production"),
    otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"),
    capture_message_content=True,
)

_otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
_logger_provider = LoggerProvider(
    resource=Resource.create({"service.name": "openlit-mcp-server"}),
)
_logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter(endpoint=_otlp_endpoint))
)
set_logger_provider(_logger_provider)
logger = logging.getLogger("openlit-mcp-server")
logger.setLevel(logging.INFO)
logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=_logger_provider))

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
        logger.error("Web search failed for query=%s: %s", query, exc)
        return f"Web search failed: {exc}"

    if not results:
        return "No results found."

    formatted = []
    for r in results:
        title = r.get("title", "")
        body = r.get("body", "")
        href = r.get("href", "")
        formatted.append(f"**{title}**\n{body}\nSource: {href}")

    logger.info("Web search completed for query=%s, results=%d", query, len(formatted))
    return "\n\n---\n\n".join(formatted)


@mcp.tool()
def get_current_time() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    mcp.run(transport="sse")
