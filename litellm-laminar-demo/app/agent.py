"""A small coding agent traced like a production agent platform.

A session is one or more user messages. Each message runs as its own trace,
and the agent carries its history and compaction state from one trace to the
next, the way a long-lived session does.

Span tree for one user message:

    session_workflow
      agent_session                     session id + account metadata; route_completed
        llm_call                        title generation, first message only; route_started
        run_agent_with_messages         input: run config + messages; output: run result
          summarizing_compact [main]    only when the context nears the window
            compaction_extract_terms_from_text [main]
              llm_call
            summarizing_get_summary
              compaction_call_model_api
                llm_call
          llm_call_stream               usage, cache, content, tool definitions, route
          tool_call [bash_execute]      input: {tool_id, tool_name, args}
                                        output: {stdout, stderr, exitCode, ...}
          llm_call_stream
          tool_call [add_task]
            subagent [explore]
              run_agent_with_messages   subagent config, own route scope
                llm_call_stream
          llm_call_stream
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import litellm
from lmnr import Laminar, observe

import compaction
import gateway
from route_audit import CallPurpose, ExecutionScope, RouteAttempt, attribute_current_span, input_batch

MAX_TURNS = 6
# User requests kept verbatim after a compaction, next to the summary.
RECENT_USER_REQUESTS = 5
SELECTION = gateway.default_selection()
ROUTER = gateway.build_router([SELECTION])

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash_execute",
            "description": "Run a shell command in the repository and return its output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "description": {"type": "string"},
                    "timeout_seconds": {"type": "integer"},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Delegate a focused question to an explore subagent.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
                "additionalProperties": False,
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are a coding agent working in a small Python repository. "
    "First run `ls` with bash_execute, then delegate one question about the "
    "repo layout with add_task, then answer in one sentence."
)

TERMS_PROMPT = (
    "List the files, commands, findings and next steps in this conversation "
    "as JSON with the keys files, commands, findings and next_steps."
)
SUMMARY_PROMPT = (
    "Write a handoff summary of this conversation for an agent that will continue it, "
    "in under 150 words of markdown. Start with '# Handoff Summary', then use the "
    "sections '## User Request', '## Progress' and '## Next Steps'. "
    "Preserve these key terms:\n{terms}"
)

FAKE_REPO = {
    "ls": "README.md\napp/\ntests/\n",
    "cat README.md": "# demo-repo\nA tiny Flask service.\n",
}

# Scripted replies for MOCK_LLM=true: (text, tool call or None) per turn.
_MOCK_MAIN = [
    ("I'll list the repository first.", ("bash_execute", {"command": "ls", "description": "List files"})),
    ("Let me have a subagent look at the layout.", ("add_task", {"question": "What does app/ contain?"})),
    ("The repo is a small Flask service with app code in app/ and tests in tests/.", None),
]
_MOCK_SUBAGENT = [("app/ holds the Flask application package.", None)]
_MOCK_TERMS = json.dumps(
    {"files": ["README.md", "app/"], "commands": ["ls"], "findings": ["Flask service"], "next_steps": []}
)
_MOCK_SUMMARY = (
    "# Handoff Summary\n\n## User Request\nDescribe the repository.\n\n"
    "## Progress\nListed the files and asked a subagent about app/.\n\n"
    "## Next Steps\nAnswer the latest user request."
)


@dataclass
class RunConfig:
    """What the turn loop runs with; captured as the span input."""

    account_id: str
    session_id: str
    subagent_id: str | None = None
    subagent_type: str | None = None
    agent_type: str = "coding"
    has_verification_pipeline: bool = False


@dataclass
class RunResult:
    """How the turn loop ended; captured as the span output."""

    final_text: str | None = None
    interrupted: bool = False
    tool_call_count: int = 0
    completed_without_response: bool = False
    tool_names: list[str] = field(default_factory=list)


@dataclass
class Conversation:
    """What one agent carries between turns: its context and compaction history."""

    messages: list[dict]
    compaction: compaction.CompactionState
    user_requests: list[dict] = field(default_factory=list)


def _mock_kwargs(mock: tuple | None) -> dict[str, Any]:
    return {"mock_response": mock[0]} if mock is not None else {}


def _attach_mock_tool_call(message: dict, mock: tuple | None) -> dict:
    # LiteLLM's mock mode drops tool calls when streaming; attach the scripted one.
    if mock is not None and mock[1] is not None:
        name, args = mock[1]
        message["tool_calls"] = [
            {
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ]
    return message


async def _stream_turn(
    scope: ExecutionScope, messages: list[dict], mock: tuple | None, state: compaction.CompactionState
) -> dict:
    """One streaming model call through the Router, inside a route attempt."""
    attempt = RouteAttempt(scope, SELECTION.model_key, SELECTION.provider, provider_instance_id="hosted")
    with attempt.observe():
        with Laminar.start_as_current_span(name="llm_call_stream", span_type="LLM", session_id=scope.session_id):
            attribute_current_span()
            stream = await ROUTER.acompletion(
                model=SELECTION.alias,
                messages=messages,
                tools=TOOLS,
                stream=True,
                stream_options={"include_usage": True},
                **_mock_kwargs(mock),
            )
            chunks = [chunk async for chunk in stream]
            response = litellm.stream_chunk_builder(chunks, messages=messages)
            message = _attach_mock_tool_call(response.choices[0].message.model_dump(), mock)
            gateway.record_llm_span(SELECTION, response.usage, messages, message, TOOLS)
            Laminar.set_span_attributes(compaction.inference_attributes(scope.session_id, state))
            return message


async def _complete(
    scope: ExecutionScope,
    messages: list[dict],
    mock_text: str,
    state: compaction.CompactionState | None = None,
) -> str:
    """One non-streaming model call for auxiliary work: titles and compaction."""
    attempt = RouteAttempt(scope, SELECTION.model_key, SELECTION.provider, provider_instance_id="hosted")
    with attempt.observe():
        with Laminar.start_as_current_span(name="llm_call", span_type="LLM", session_id=scope.session_id):
            attribute_current_span()
            response = await ROUTER.acompletion(
                model=SELECTION.alias,
                messages=messages,
                **_mock_kwargs((mock_text, None) if gateway.MOCK_LLM else None),
            )
            message = response.choices[0].message.model_dump()
            gateway.record_llm_span(SELECTION, response.usage, messages, message, None)
            Laminar.set_span_attributes(compaction.inference_attributes(scope.session_id, state))
            return message.get("content") or ""


def _transcript(messages: list[dict]) -> str:
    """Flatten a history, tool calls included, into text a summarizer can read."""
    lines = []
    for m in messages[1:]:
        if m.get("content"):
            lines.append(f"{m['role']}: {m['content']}")
        for call in m.get("tool_calls") or []:
            lines.append(f"{m['role']} called {call['function']['name']}({call['function']['arguments']})")
    return "\n".join(lines)


async def _compact_if_needed(scope: ExecutionScope, conversation: Conversation) -> None:
    """Replace the history with a summary when it nears the context window."""
    state = conversation.compaction
    tokens_before = compaction.estimate_tokens(SELECTION.model_key, conversation.messages)
    trigger = compaction.pick_trigger(tokens_before)
    if trigger is None:
        return
    aux = ExecutionScope(scope.account_id, scope.session_id, scope.subagent_id, purpose=CallPurpose.COMPACTION)
    transcript = [{"role": "user", "content": _transcript(conversation.messages)}]
    # The terms and the summary are the outputs of their stage spans, as a
    # production agent records them, so a trace viewer can show the summary
    # at the point where the history was replaced.
    with Laminar.start_as_current_span(name=f"summarizing_compact [{state.agent_key}]", session_id=scope.session_id):
        with Laminar.start_as_current_span(name=f"compaction_extract_terms_from_text [{state.agent_key}]") as span:
            terms = await _complete(aux, [*transcript, {"role": "user", "content": TERMS_PROMPT}], _MOCK_TERMS, state)
            span.set_output(terms)
        with Laminar.start_as_current_span(name="summarizing_get_summary") as summary_span:
            with Laminar.start_as_current_span(name="compaction_call_model_api"):
                prompt = SUMMARY_PROMPT.format(terms=terms)
                summary = await _complete(
                    aux, [*transcript, {"role": "user", "content": prompt}], _MOCK_SUMMARY, state
                )
            summary_span.set_output(summary)
        messages_before = len(conversation.messages)
        conversation.messages = compaction.compacted_history(
            conversation.messages[0], summary, conversation.user_requests[-RECENT_USER_REQUESTS:]
        )
        tokens_after = compaction.estimate_tokens(SELECTION.model_key, conversation.messages)
        row = compaction.record(
            state, trigger, (tokens_before, messages_before), (tokens_after, len(conversation.messages)), summary
        )
        Laminar.set_span_attributes(row.attributes(scope.session_id, state))


async def _run_tool(scope: ExecutionScope, call: dict) -> str:
    name = call["function"]["name"]
    args = json.loads(call["function"]["arguments"] or "{}")
    with Laminar.start_as_current_span(
        name=f"tool_call [{name}]",
        span_type="TOOL",
        input={"tool_id": call["id"], "tool_name": name, "args": args},
    ) as span:
        if name == "add_task" and scope.subagent_id is None:
            result = await _run_subagent(scope, args.get("question", ""))
            span.set_output({"result": result})
            return result
        stdout = FAKE_REPO.get(args.get("command", "").strip())
        output = {
            "stdout": stdout or "",
            "stderr": "" if stdout is not None else f"{args.get('command')}: command not found",
            "exitCode": 0 if stdout is not None else 127,
            "outputExceededThreshold": False,
        }
        span.set_output(output)
        return output["stdout"] or output["stderr"]


def _new_conversation(config: RunConfig) -> Conversation:
    system = "Answer briefly." if config.subagent_id else SYSTEM_PROMPT
    agent_key = config.subagent_id or "main"
    return Conversation(
        messages=[{"role": "system", "content": system}],
        compaction=compaction.CompactionState(agent_key, config.subagent_type or "main"),
    )


# The conversation is the agent's whole history; the span input keeps only
# this turn's config and messages.
@observe(name="run_agent_with_messages", ignore_inputs=["conversation"])
async def run_agent_with_messages(
    config: RunConfig,
    user_messages: list[dict],
    message_ids: list[int],
    conversation: Conversation | None = None,
) -> RunResult:
    scope = ExecutionScope(config.account_id, config.session_id, config.subagent_id)
    script = (_MOCK_SUBAGENT if config.subagent_id else _MOCK_MAIN) if gateway.MOCK_LLM else None
    conversation = conversation or _new_conversation(config)
    conversation.messages.extend(user_messages)
    conversation.user_requests.extend(user_messages)
    result = RunResult()
    with input_batch(scope, message_ids):
        for turn in range(MAX_TURNS):
            mock = script[min(turn, len(script) - 1)] if script is not None else None
            await _compact_if_needed(scope, conversation)
            message = await _stream_turn(scope, conversation.messages, mock, conversation.compaction)
            conversation.messages.append({k: v for k, v in message.items() if v is not None})
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                result.final_text = message.get("content") or ""
                result.completed_without_response = not result.final_text
                return result
            for call in tool_calls:
                result.tool_call_count += 1
                result.tool_names.append(call["function"]["name"])
                output = await _run_tool(scope, call)
                conversation.messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
    result.interrupted = True
    return result


async def _run_subagent(parent: ExecutionScope, question: str) -> str:
    subagent_id = f"explore-{uuid.uuid4().hex[:8]}"
    with Laminar.start_as_current_span(name="subagent [explore]", session_id=parent.session_id):
        result = await run_agent_with_messages(
            RunConfig(parent.account_id, parent.session_id, subagent_id=subagent_id, subagent_type="explore"),
            [{"role": "user", "content": question}],
            [1],
        )
    return result.final_text or ""


async def _generate_title(scope: ExecutionScope, prompt: str) -> None:
    """Auxiliary non-streaming call with its own purpose, like title generation."""
    aux = ExecutionScope(scope.account_id, scope.session_id, purpose=CallPurpose.CLASSIFICATION)
    await _complete(aux, [{"role": "user", "content": f"Write a 3-word title for: {prompt}"}], "List repo files")


async def run_session(prompt: str, followups: list[str] | None = None, account_id: str = "demo-account") -> dict:
    """Run one session: the prompt, then each follow-up, one trace per user message."""
    session_id = str(uuid.uuid4())
    # Session id and account metadata ride the Laminar context, so every
    # descendant span carries lmnr.association.properties.*.
    metadata = {"account_id": account_id, "environment": os.environ.get("ENV", "demo")}
    config = RunConfig(account_id, session_id)
    conversation = _new_conversation(config)
    trace_ids: list[str] = []
    result = RunResult()
    for message_id, text in enumerate([prompt, *(followups or [])], start=1):
        with (
            Laminar.start_as_current_span(name="session_workflow", session_id=session_id, metadata=metadata),
            Laminar.start_as_current_span(name="agent_session", session_id=session_id, metadata=metadata),
        ):
            trace_ids.append(format(Laminar.get_current_span().get_span_context().trace_id, "032x"))
            if message_id == 1:
                await _generate_title(ExecutionScope(account_id, session_id), prompt)
            result = await run_agent_with_messages(
                config, [{"role": "user", "content": text}], [message_id], conversation
            )
    return {
        "session_id": session_id,
        "trace_id": trace_ids[0],
        "trace_ids": trace_ids,
        "compactions": conversation.compaction.round,
        "answer": result.final_text,
    }
