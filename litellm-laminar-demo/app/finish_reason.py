"""Record why a streamed model call stopped.

Ported from ``FinishReasonTracker`` in Cosmos ``common_py/llm/stream_accumulator.py``.
The demo has no discarded-partial-response path, so ``reset`` is not ported.
"""

from collections.abc import Mapping
from typing import Any, Optional

FINISH_REASONS_ATTRIBUTE = "gen_ai.response.finish_reasons"


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


class FinishReasonTracker:
    """Remember the last finish reason a model stream reported.

    Providers send it on the last content chunk and often follow it with a
    usage-only chunk that has none, so the last non-empty value is kept. It is
    recorded as the OTel ``gen_ai.response.finish_reasons`` string array, with
    one entry because these streams request a single choice.

    Neither method raises: a telemetry fault must not break the stream.
    """

    def __init__(self) -> None:
        self.reason: Optional[str] = None

    def observe(self, chunk: Any) -> None:
        try:
            for choice in _field(chunk, "choices", None) or ():
                reason = _field(choice, "finish_reason")
                if isinstance(reason, str) and reason:
                    self.reason = reason
        except Exception:
            return

    def record_on(self, span: Any) -> None:
        if span is None or self.reason is None:
            return
        try:
            span.set_attribute(FINISH_REASONS_ATTRIBUTE, [self.reason])
        except Exception:
            return
