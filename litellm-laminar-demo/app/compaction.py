"""Context compaction policy and the telemetry that makes it a session timeline.

Long agent sessions outgrow the model's context window, so the agent
periodically replaces its history with a summary. This module decides when
that happens and describes each compaction as span attributes, so a backend
can draw one strip per session: round, trigger, tokens before and after, and
the time between compactions.

OpenTelemetry GenAI semantic conventions cover only part of this:

- ``gen_ai.conversation.id`` groups every span of a session, across traces.
- ``gen_ai.conversation.compacted=true`` marks an inference span whose input
  is a compacted view of the conversation. The convention says to leave it
  unset, never ``false``, when no compaction happened.

They define no span or attributes for the compaction step itself (the
upstream proposal deferred orchestrator-side compaction to a follow-up), so
the details of each compaction are written under ``COMPACTION_ATTRIBUTE_PREFIX``:

    summarizing_compact [<agent>]
        gen_ai.conversation.id, gen_ai.agent.name
        agent.compaction.round                 1, 2, ... per agent, across traces
        agent.compaction.trigger               soft_threshold | hard_threshold
        agent.compaction.strategy              summarizing
        agent.compaction.context_window_tokens
        agent.compaction.threshold             fraction of the window that fired
        agent.compaction.tokens_before / tokens_after
        agent.compaction.messages_before / messages_after
        agent.compaction.summary_id            digest of the summary text
        agent.compaction.previous_summary_id   round 2 onwards
        agent.compaction.seconds_since_previous round 2 onwards

    every later inference span of that agent
        gen_ai.conversation.compacted=true, agent.compaction.round

Token counts are estimates of the context the agent holds, not provider
usage, so they are comparable before and after a compaction.
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import litellm

logger = logging.getLogger(__name__)

COMPACTION_ATTRIBUTE_PREFIX = "agent.compaction."
CONTEXT_WINDOW_TOKENS = int(os.environ.get("CONTEXT_WINDOW_TOKENS", "200000"))
# A soft trigger compacts when convenient; a hard trigger means the next call
# would come close to the window and the agent had to stop and compact first.
SOFT_THRESHOLD = 0.8
HARD_THRESHOLD = 0.875
STRATEGY = "summarizing"


class CompactionTrigger(str, Enum):
    SOFT_THRESHOLD = "soft_threshold"
    HARD_THRESHOLD = "hard_threshold"


@dataclass
class CompactionState:
    """One agent's compaction history. It outlives a trace, as a session does."""

    agent_key: str
    agent_name: str
    round: int = 0
    summary_id: str = ""
    compacted_at: float | None = None


@dataclass(frozen=True)
class CompactionRecord:
    """One row of the session timeline, written onto the compaction span."""

    round: int
    trigger: CompactionTrigger
    context_window_tokens: int
    threshold: float
    tokens_before: int
    tokens_after: int
    messages_before: int
    messages_after: int
    summary_id: str
    previous_summary_id: str
    seconds_since_previous: float | None

    def attributes(self, session_id: str, state: CompactionState) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "gen_ai.conversation.id": session_id,
            "gen_ai.agent.name": state.agent_name,
            "agent_key": state.agent_key,
            "round": self.round,
            "trigger": self.trigger.value,
            "strategy": STRATEGY,
            "context_window_tokens": self.context_window_tokens,
            "threshold": self.threshold,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "messages_before": self.messages_before,
            "messages_after": self.messages_after,
            "summary_id": self.summary_id,
        }
        # Absent on round 1, so a missing value means "first compaction", not zero.
        if self.previous_summary_id:
            attrs["previous_summary_id"] = self.previous_summary_id
        if self.seconds_since_previous is not None:
            attrs["seconds_since_previous"] = round(self.seconds_since_previous, 3)
        return {
            key if key.startswith("gen_ai.") else COMPACTION_ATTRIBUTE_PREFIX + key: value
            for key, value in attrs.items()
        }


def estimate_tokens(model: str, messages: list[dict]) -> int:
    """Estimate the context size. Falls back to ~4 characters per token offline."""
    try:
        return int(litellm.token_counter(model=model, messages=messages))
    except Exception:
        logger.debug("token_counter failed; using a character estimate", exc_info=True)
        return len(json.dumps(messages, default=str)) // 4


def pick_trigger(tokens: int, window: int = CONTEXT_WINDOW_TOKENS) -> CompactionTrigger | None:
    if tokens >= window * HARD_THRESHOLD:
        return CompactionTrigger.HARD_THRESHOLD
    if tokens >= window * SOFT_THRESHOLD:
        return CompactionTrigger.SOFT_THRESHOLD
    return None


def summary_digest(summary: str) -> str:
    """A stable id for a summary, so rounds can reference their predecessor without its text."""
    return hashlib.sha256(summary.encode()).hexdigest()[:16]


def record(
    state: CompactionState,
    trigger: CompactionTrigger,
    before: tuple[int, int],
    after: tuple[int, int],
    summary: str,
) -> CompactionRecord:
    """Advance the agent's state by one compaction and describe it.

    ``before`` and ``after`` are (tokens, messages) of the agent's context.
    """
    now = time.monotonic()
    row = CompactionRecord(
        round=state.round + 1,
        trigger=trigger,
        context_window_tokens=CONTEXT_WINDOW_TOKENS,
        threshold=HARD_THRESHOLD if trigger is CompactionTrigger.HARD_THRESHOLD else SOFT_THRESHOLD,
        tokens_before=before[0],
        tokens_after=after[0],
        messages_before=before[1],
        messages_after=after[1],
        summary_id=summary_digest(summary),
        previous_summary_id=state.summary_id,
        seconds_since_previous=None if state.compacted_at is None else now - state.compacted_at,
    )
    state.round, state.summary_id, state.compacted_at = row.round, row.summary_id, now
    return row


def inference_attributes(session_id: str, state: CompactionState | None) -> dict[str, Any]:
    """Attributes for an inference span: the session, and the compaction epoch it runs in."""
    attrs: dict[str, Any] = {"gen_ai.conversation.id": session_id}
    if state is not None and state.round:
        attrs["gen_ai.conversation.compacted"] = True
        attrs[COMPACTION_ATTRIBUTE_PREFIX + "round"] = state.round
    return attrs


def compacted_history(system: dict, summary: str, recent_user_messages: list[dict]) -> list[dict]:
    """What the agent keeps: its system prompt, the summary, and the latest user requests."""
    recent = "\n".join(f"- {m['content']}" for m in recent_user_messages if isinstance(m.get("content"), str))
    body = f"Summary of the conversation so far:\n\n{summary}"
    if recent:
        body += f"\n\nMost recent user requests:\n{recent}"
    return [system, {"role": "user", "content": body}]
