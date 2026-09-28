"""A small coding agent traced like a production agent platform.

Span tree for one session:

    session_workflow
      agent_session                     session id + account metadata; route_completed
        llm_call                        title generation via the Router; route_started
          chat <model>                  LiteLLM GenAI span (Oodle only)
        run_agent_with_messages         input: run config + messages; output: run result
          llm_call_stream               usage, cache, content, tool definitions, route
            chat <model>
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
from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER
from lmnr import Laminar, observe

import gateway
from route_audit import CallPurpose, ExecutionScope, RouteAttempt, attribute_current_span, input_batch

MAX_TURNS = 6
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


async def _stream_turn(scope: ExecutionScope, messages: list[dict], mock: tuple | None) -> dict:
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
            return message


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


@observe(name="run_agent_with_messages")
async def run_agent_with_messages(
    config: RunConfig, user_messages: list[dict], message_ids: list[int]
) -> RunResult:
    scope = ExecutionScope(config.account_id, config.session_id, config.subagent_id)
    script = (_MOCK_SUBAGENT if config.subagent_id else _MOCK_MAIN) if gateway.MOCK_LLM else None
    system = "Answer briefly." if config.subagent_id else SYSTEM_PROMPT
    messages = [{"role": "system", "content": system}, *user_messages]
    result = RunResult()
    with input_batch(scope, message_ids):
        for turn in range(MAX_TURNS):
            mock = script[min(turn, len(script) - 1)] if script is not None else None
            message = await _stream_turn(scope, messages, mock)
            messages.append({k: v for k, v in message.items() if v is not None})
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                result.final_text = message.get("content") or ""
                result.completed_without_response = not result.final_text
                return result
            for call in tool_calls:
                result.tool_call_count += 1
                result.tool_names.append(call["function"]["name"])
                output = await _run_tool(scope, call)
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
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
    messages = [{"role": "user", "content": f"Write a 3-word title for: {prompt}"}]
    attempt = RouteAttempt(aux, SELECTION.model_key, SELECTION.provider, provider_instance_id="hosted")
    with attempt.observe():
        with Laminar.start_as_current_span(name="llm_call", span_type="LLM", session_id=scope.session_id):
            attribute_current_span()
            response = await ROUTER.acompletion(
                model=SELECTION.alias,
                messages=messages,
                **_mock_kwargs(("List repo files", None) if gateway.MOCK_LLM else None),
            )
            gateway.record_llm_span(SELECTION, response.usage, messages, response.choices[0].message.model_dump(), None)


async def run_session(prompt: str, account_id: str = "demo-account") -> dict:
    session_id = str(uuid.uuid4())
    # Session id and account metadata ride the Laminar context, so every
    # descendant span carries lmnr.association.properties.*.
    metadata = {"account_id": account_id, "environment": os.environ.get("ENV", "demo")}
    with (
        Laminar.start_as_current_span(name="session_workflow", session_id=session_id, metadata=metadata),
        Laminar.start_as_current_span(name="agent_session", session_id=session_id, metadata=metadata),
    ):
        trace_id = format(Laminar.get_current_span().get_span_context().trace_id, "032x")
        scope = ExecutionScope(account_id, session_id)
        await _generate_title(scope, prompt)
        result = await run_agent_with_messages(
            RunConfig(account_id, session_id), [{"role": "user", "content": prompt}], [1]
        )
    # LiteLLM emits its callback spans from a background task; drain it here.
    await GLOBAL_LOGGING_WORKER.flush()
    return {"session_id": session_id, "trace_id": trace_id, "answer": result.final_text}
