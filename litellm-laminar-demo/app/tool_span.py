"""Name tool spans and record how each tool call ended.

Ported from Cosmos ``common_py/observability/tool_span.py``; only the logger differs.

Tool spans carried only a display name such as ``tool_call [bash_execute]``,
and every call looked successful, so traces could not be grouped by tool or
filtered to the calls that failed. These helpers write the OTel GenAI
``execute_tool`` attributes and mark failed calls.

A failed call gets ERROR status and an exception event. Laminar counts a span
as failed only when it has the exception event, so both are written. Neither
carries tool arguments or output: the status text and the event message are
fixed strings, because tool output can hold secrets.

Every helper swallows its own errors: telemetry must never fail a tool call.
"""

import logging
from typing import Optional

from opentelemetry.trace import Span, Status, StatusCode

logger = logging.getLogger(__name__)

OPERATION_NAME_ATTRIBUTE = "gen_ai.operation.name"
EXECUTE_TOOL_OPERATION = "execute_tool"
TOOL_NAME_ATTRIBUTE = "gen_ai.tool.name"
TOOL_CALL_ID_ATTRIBUTE = "gen_ai.tool.call.id"
# OTel process semconv: a shell tool call runs one process, so its exit code
# uses the same key a process span would.
EXIT_CODE_ATTRIBUTE = "process.exit.code"


class ToolCallFailedError(Exception):
    """Recorded as the exception event of a failed tool span; never raised."""


def name_tool_span(span: Optional[Span], tool_name: str, tool_call_id: str = "") -> None:
    """Write the GenAI ``execute_tool`` identity attributes on a tool span."""
    if span is None:
        return
    try:
        span.set_attribute(OPERATION_NAME_ATTRIBUTE, EXECUTE_TOOL_OPERATION)
        span.set_attribute(TOOL_NAME_ATTRIBUTE, tool_name)
        if tool_call_id:
            span.set_attribute(TOOL_CALL_ID_ATTRIBUTE, tool_call_id)
    except Exception:
        logger.debug("Failed to name tool span", exc_info=True)


def record_tool_outcome(
    span: Optional[Span], *, failed: bool, exit_code: Optional[int] = None
) -> None:
    """Record a tool call's exit code and mark the span failed when it failed.

    A non-zero ``exit_code`` counts as a failure even when ``failed`` is false.
    """
    if span is None:
        return
    try:
        if exit_code is not None:
            span.set_attribute(EXIT_CODE_ATTRIBUTE, exit_code)
        if exit_code:
            description = f"exited with code {exit_code}"
        elif failed:
            description = "tool returned an error"
        else:
            return
        span.set_status(Status(StatusCode.ERROR, description))
        span.record_exception(ToolCallFailedError(description))
    except Exception:
        logger.debug("Failed to record tool span outcome", exc_info=True)
