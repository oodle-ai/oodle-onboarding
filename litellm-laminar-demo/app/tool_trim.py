"""Tool-output trimming, and the span that puts it on the session timeline.

Before an agent compacts its history, it can make room a cheaper way: it
replaces large, old tool outputs with a pointer to a file that holds them.
The message structure stays, so this is not a compaction, but the model no
longer sees those outputs. A trace that does not show the trim cannot explain
why the agent later runs the same tool call again.

The policy matches a production agent platform:

- It fires once the context passes ``TRIM_THRESHOLD`` of the window, at most
  once per compaction cycle. A compaction re-arms it.
- It needs more than ``MIN_MESSAGES`` messages, and it leaves the newest
  ``PRESERVE_RATIO`` of them alone, so the model keeps its recent context.
- It replaces only tool outputs longer than ``CHAR_THRESHOLD`` characters.

Each attempt is one span, ``tool_trim [<agent>]``:

    tool_trim.outcome                trimmed | no_op
    tool_trim.messages_trimmed
    tool_trim.tokens_before / tokens_after
    tool_trim.threshold_tokens
    tool_trim.trimmed_tool_call_ids  the tool calls whose output was replaced

The ids are the ``tool_call_id`` of the replaced messages, which is also the
``tool_id`` in the input of each ``tool_call [*]`` span. They let a backend
tie a later repeat of a call to the trim that removed its output. Nothing
here is message content, so it reaches Oodle with content capture off.

The demo does not write the files the placeholders name. Only the history
and the trace matter here.
"""

import os
from dataclasses import dataclass
from typing import Any

import compaction

TOOL_TRIM_ATTRIBUTE_PREFIX = "tool_trim."
TRIM_THRESHOLD = 0.5
PRESERVE_RATIO = 0.25
CHAR_THRESHOLD = int(os.environ.get("TOOL_TRIM_CHAR_THRESHOLD", "2000"))
MIN_MESSAGES = int(os.environ.get("TOOL_TRIM_MIN_MESSAGES", "50"))
OUTPUT_DIR = "/code/.trimmed-tool-output"


@dataclass
class TrimState:
    """One agent's trimmer. ``fired`` stays set until a compaction re-arms it."""

    agent_key: str
    fired: bool = False


@dataclass(frozen=True)
class TrimRecord:
    """What one trim attempt did, written onto its span."""

    tokens_before: int
    tokens_after: int
    threshold_tokens: int
    trimmed_tool_call_ids: list[str]

    def attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "outcome": "trimmed" if self.trimmed_tool_call_ids else "no_op",
            "messages_trimmed": len(self.trimmed_tool_call_ids),
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "threshold_tokens": self.threshold_tokens,
            "trimmed_tool_call_ids": list(self.trimmed_tool_call_ids),
        }
        return {TOOL_TRIM_ATTRIBUTE_PREFIX + key: value for key, value in attrs.items()}


def threshold_tokens(window: int = compaction.CONTEXT_WINDOW_TOKENS) -> int:
    return int(window * TRIM_THRESHOLD)


def should_trim(state: TrimState, tokens: int) -> bool:
    return not state.fired and tokens > threshold_tokens()


def trim_messages(messages: list[dict], agent_key: str) -> tuple[list[dict], list[str]]:
    """Replace large, old tool outputs with file pointers.

    Returns the new history and the ``tool_call_id`` of each replaced message.
    """
    if len(messages) <= MIN_MESSAGES:
        return messages, []
    boundary = int(len(messages) * (1 - PRESERVE_RATIO))
    trimmed = list(messages)
    ids: list[str] = []
    for i, message in enumerate(messages[:boundary]):
        content = message.get("content")
        if message.get("role") != "tool" or not isinstance(content, str) or len(content) <= CHAR_THRESHOLD:
            continue
        trimmed[i] = {**message, "content": f"[Tool output saved to {OUTPUT_DIR}/{agent_key}/msg_{i:04d}.txt]"}
        ids.append(message["tool_call_id"])
    return trimmed, ids
