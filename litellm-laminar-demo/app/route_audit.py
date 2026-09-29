"""Route audit: one structured event per model-call attempt, written onto spans.

Production agent platforms route each model call through a choice of
backends (a hosted API, a subscription CLI, a fallback) and record why.
This module reproduces that pattern: every attempt emits a ``RouteEvent``
and stamps all of its fields, flattened under ``ROUTE_ATTRIBUTE_PREFIX``,
onto whichever Laminar span is current when the event fires.

The timing is what puts the attributes on two different spans:

    run_agent_with_messages            <- route_selected, then route_completed
      llm_call_stream                  <- route_started (stamped inside the span)

so the LLM span records how the call started and the enclosing span records
how it ended. Both then reach Oodle through the Laminar mirror.
"""

import hashlib
import os
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Literal
from uuid import uuid4

from lmnr import Laminar

ROUTE_ATTRIBUTE_PREFIX = os.environ.get("ROUTE_ATTRIBUTE_PREFIX", "agent.route.")


class RouteEventKind(str, Enum):
    SELECTED = "route_selected"
    STARTED = "route_started"
    COMPLETED = "route_completed"
    FAILED = "route_failed"
    CANCELLED = "route_cancelled"


class RouteReason(str, Enum):
    DEFAULT = "api_default"
    FORCED_API = "forced_api"
    UNSUPPORTED = "unsupported_capability"
    QUOTA = "quota"
    AUTH = "auth"
    TRANSIENT = "transient"
    ERROR = "error"
    CANCELLED = "cancelled"


class CallPurpose(str, Enum):
    AGENT_TURN = "agent_turn"
    CLASSIFICATION = "classification"
    COMPACTION = "compaction"
    RESPONSE_VERIFICATION = "response_verification"


@dataclass(frozen=True)
class ExecutionScope:
    """Who a model call belongs to: account, session, subagent and purpose."""

    account_id: str
    session_id: str
    subagent_id: str | None = None
    purpose: CallPurpose = CallPurpose.AGENT_TURN
    request_id: str = field(default_factory=lambda: str(uuid4()))
    api_only: bool = False


@dataclass(frozen=True)
class RouteEvent:
    event: RouteEventKind
    account_id: str
    session_id: str
    child_id: str
    purpose: str
    execution_id: str
    input_batch_id: str
    input_message_ids: str
    input_message_count: int
    logical_call_id: str
    attempt_id: str
    parent_attempt_id: str
    burst_id: str
    route: Literal["api", "claude_cli"]
    provider: str
    model: str
    provider_instance_id: str
    credential_revision: str
    reason: RouteReason
    selection_reason: RouteReason
    started: bool
    fallback: bool
    forced_api: bool
    unsupported: bool
    quota: bool
    auth: bool
    flag_disabled: bool

    def attributes(self) -> dict[str, str | bool | int]:
        return {
            ROUTE_ATTRIBUTE_PREFIX + key: value.value if isinstance(value, Enum) else value
            for key, value in asdict(self).items()
        }


def safe_identifier(value: str | None) -> str:
    """Pass short identifiers through; redact anything that could be a secret or text."""
    if value is None:
        return ""
    if value.startswith(("sk-", "Bearer", "eyJ")):
        return "redacted"
    if len(value) <= 128 and re.fullmatch(r"[a-zA-Z0-9_.:/\[\]-]+", value):
        return value
    return "redacted"


@dataclass(frozen=True)
class _InputBatch:
    batch_id: str
    message_ids: str
    message_count: int


_batch: ContextVar[_InputBatch | None] = ContextVar("route_input_batch", default=None)
_active: ContextVar["RouteAttempt | None"] = ContextVar("route_active_attempt", default=None)


@contextmanager
def input_batch(scope: ExecutionScope, message_ids: Sequence[str | int]) -> Iterator[None]:
    """Correlate every call in a turn with the user messages that triggered it.

    The batch id is a bounded digest of the ids, never of message text.
    """
    ids = tuple(str(v) for v in message_ids)
    digest = hashlib.sha256()
    for value in (scope.account_id, scope.session_id, scope.subagent_id or "", *sorted(ids)):
        encoded = value.encode()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    token = _batch.set(
        _InputBatch(digest.hexdigest() if ids else "", ",".join(ids[:32]), len(ids))
    )
    try:
        yield
    finally:
        _batch.reset(token)


@dataclass
class RouteAttempt:
    scope: ExecutionScope
    model: str
    provider: str
    route: Literal["api", "claude_cli"] = "api"
    provider_instance_id: str = ""
    credential_revision: str = ""
    reason: RouteReason = RouteReason.DEFAULT
    parent_attempt_id: str = ""
    attempt_id: str = field(default_factory=lambda: str(uuid4()))
    logical_call_id: str = field(default_factory=lambda: str(uuid4()))
    started: bool = False

    def event(self, kind: RouteEventKind) -> RouteEvent:
        batch = _batch.get()
        reason = RouteReason.FORCED_API if self.scope.api_only else self.reason
        return RouteEvent(
            event=kind,
            account_id=safe_identifier(self.scope.account_id),
            session_id=safe_identifier(self.scope.session_id),
            child_id=safe_identifier(self.scope.subagent_id),
            purpose=self.scope.purpose.value,
            execution_id=safe_identifier(self.scope.request_id),
            input_batch_id=batch.batch_id if batch else "",
            input_message_ids=batch.message_ids if batch else "",
            input_message_count=batch.message_count if batch else 0,
            logical_call_id=self.logical_call_id,
            attempt_id=self.attempt_id,
            parent_attempt_id=self.parent_attempt_id,
            burst_id="",
            route=self.route,
            provider=safe_identifier(self.provider),
            model=safe_identifier(self.model),
            provider_instance_id=safe_identifier(self.provider_instance_id),
            credential_revision=safe_identifier(self.credential_revision),
            reason=reason,
            selection_reason=reason,
            started=self.started,
            fallback=bool(self.parent_attempt_id),
            forced_api=self.scope.api_only,
            unsupported=reason is RouteReason.UNSUPPORTED,
            quota=reason is RouteReason.QUOTA,
            auth=reason is RouteReason.AUTH,
            flag_disabled=False,
        )

    def emit(self, kind: RouteEventKind) -> None:
        """Stamp the event on the current span. Telemetry never breaks the call."""
        try:
            Laminar.set_span_attributes(self.event(kind).attributes())
        except Exception:
            pass

    @contextmanager
    def observe(self) -> Iterator["RouteAttempt"]:
        """Wrap one attempt: selected before the LLM span, completed after it."""
        self.emit(RouteEventKind.SELECTED)
        token = _active.set(self)
        try:
            yield self
        except BaseException as exc:
            cancelled = type(exc).__name__ == "CancelledError"
            self.reason = RouteReason.CANCELLED if cancelled else RouteReason.ERROR
            self.emit(RouteEventKind.CANCELLED if cancelled else RouteEventKind.FAILED)
            raise
        else:
            self.emit(RouteEventKind.COMPLETED)
        finally:
            _active.reset(token)


def attribute_current_span() -> None:
    """Called inside the LLM span: mark the active attempt started on that span."""
    attempt = _active.get()
    if attempt is None:
        return
    attempt.started = True
    attempt.emit(RouteEventKind.STARTED)
