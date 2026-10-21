"""Record turn attributes on the session_workflow span.

Each demo turn processes one user message. Follow-up messages start new
traces. Tool calls, subagent work, and compaction remain inside that turn.
The demo has no billing gate or durable timestamp for the previous turn.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from opentelemetry import trace

logger = logging.getLogger(__name__)


@dataclass
class TurnState:
    stop_reason: str | None = None


def _set(span: trace.Span, key: str, value: str | int | bool) -> None:
    # A telemetry failure must not change the result or replace an exception.
    try:
        if span.is_recording():
            span.set_attribute(key, value)
    except Exception:
        logger.debug("Failed to record %s on the turn span", key, exc_info=True)


@contextmanager
def trace_turn() -> Iterator[TurnState]:
    """Keep the root handle because nested work changes the current span."""
    try:
        root = trace.get_current_span()
    except Exception:
        logger.debug("Failed to get the turn span", exc_info=True)
        root = trace.INVALID_SPAN
    state = TurnState()
    _set(root, "agent.trigger", "human")
    _set(root, "agent.batch_count", 1)
    _set(root, "agent.mid_run_human_input", False)
    try:
        yield state
    except BaseException as error:
        _set(root, "agent.outcome", "failed" if isinstance(error, Exception) else "cancelled")
        raise
    else:
        _set(root, "agent.outcome", "ended")
    finally:
        if state.stop_reason is not None:
            _set(root, "agent.stop_reason", state.stop_reason)
