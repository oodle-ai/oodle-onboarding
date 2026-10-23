"""Allowlisted AWS and MCP tools for managed-agent return control."""

from aws_tools import get_return_policy, lookup_order
from mcp_tools import search_aws_docs


def execute(function: str, arguments: dict) -> dict:
    if function == "get_return_policy" and not arguments:
        return get_return_policy()
    if function == "lookup_order" and set(arguments) == {"order_id"}:
        return lookup_order(arguments["order_id"])
    if function == "search_aws_docs" and set(arguments) == {"search_phrase"}:
        return search_aws_docs(arguments["search_phrase"])
    raise ValueError("Unsupported function or invalid arguments")
