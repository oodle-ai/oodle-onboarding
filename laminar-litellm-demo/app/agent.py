"""One LiteLLM coding agent, traced three ways.

The agent is the same in every mode: a session of several turns,
each turn a loop of model calls and tool executions until the
model answers. What differs is who writes the spans:

- TRACER=litellm-otel   LiteLLM's own `otel` callback, to Oodle.
                        This is the setup the Oodle LiteLLM tile
                        ships.
- TRACER=laminar        Laminar's `LaminarLiteLLMCallback` plus
                        `@observe` around turns and tools, to a
                        self-hosted Laminar.
- TRACER=laminar-to-oodle
                        The same Laminar instrumentation, with the
                        Laminar SDK's exporter pointed at Oodle.

The prompt is built to make the gaps show. The system prompt is
over a thousand tokens so the provider caches it from the second
call on; every call carries a session id and a user id in LiteLLM
`metadata`; and the task needs several tool calls.
"""

import json
import os
import sys
import time

import litellm

TRACER = os.environ.get("TRACER", "litellm-otel")
MODEL = os.environ.get("MODEL", "gpt-4o-mini")
SESSION_ID = os.environ.get("SESSION_ID", "demo-session-1")
USER_ID = os.environ.get("USER_ID", "demo-user")
TURNS = int(os.environ.get("TURNS", "2"))

# ---------------------------------------------------------------
# Instrumentation. Exactly one of the three branches runs.
# ---------------------------------------------------------------

if TRACER == "litellm-otel":
    # LiteLLM builds its own tracer provider from the
    # OTEL_EXPORTER_OTLP_* environment. Nothing else to set up.
    litellm.callbacks = ["otel"]

    def observe(**_kwargs):
        def wrap(fn):
            return fn

        return wrap

    def flush():
        # LiteLLM exports on a batch timer; give it a moment
        # before the process exits.
        time.sleep(3)

elif TRACER in ("laminar", "laminar-to-oodle"):
    from lmnr import Laminar, LaminarLiteLLMCallback, observe

    if TRACER == "laminar":
        Laminar.initialize(
            project_api_key=os.environ["LMNR_PROJECT_API_KEY"],
            base_url=os.environ.get("LMNR_BASE_URL", "http://localhost"),
            http_port=int(os.environ.get("LMNR_HTTP_PORT", "8000")),
            grpc_port=int(os.environ.get("LMNR_GRPC_PORT", "8001")),
        )
    else:
        # With no project key the Laminar SDK reads the standard
        # OTEL_EXPORTER_OTLP_* variables and exports there, so
        # Oodle receives the spans Laminar would have.
        Laminar.initialize(force_http=True)

    litellm.callbacks = [LaminarLiteLLMCallback()]

    def flush():
        Laminar.flush()

else:
    sys.exit(f"unknown TRACER {TRACER!r}")


# ---------------------------------------------------------------
# A small repository the agent can read and run against.
# ---------------------------------------------------------------

REPO = {
    "README.md": (
        "# invoice-service\n\nParses supplier invoices and posts "
        "them to the ledger. Run `make test` before opening a PR.\n"
    ),
    "invoice/parse.py": (
        "import re\n\n"
        "TOTAL = re.compile(r'Total:\\s*(\\d+)\\.(\\d{2})')\n\n"
        "def parse_total(text: str) -> int:\n"
        "    m = TOTAL.search(text)\n"
        "    if not m:\n"
        "        raise ValueError('no total')\n"
        "    return int(m.group(1)) * 100 + int(m.group(2))\n"
    ),
    "invoice/ledger.py": (
        "def post(entries, total_cents):\n"
        "    if sum(e['cents'] for e in entries) != total_cents:\n"
        "        raise ValueError('entries do not sum to total')\n"
        "    return {'posted': len(entries), 'total_cents': total_cents}\n"
    ),
    "tests/test_parse.py": (
        "from invoice.parse import parse_total\n\n"
        "def test_total():\n"
        "    assert parse_total('Total: 12.30') == 1230\n\n"
        "def test_total_with_thousands():\n"
        "    assert parse_total('Total: 1,250.00') == 125000\n"
    ),
}

TEST_OUTPUT = (
    "tests/test_parse.py::test_total PASSED\n"
    "tests/test_parse.py::test_total_with_thousands FAILED\n"
    "  ValueError: no total\n"
    "1 failed, 1 passed\n"
)


@observe(name="list_files", span_type="TOOL")
def list_files() -> dict:
    return {"files": sorted(REPO)}


@observe(name="read_file", span_type="TOOL")
def read_file(path: str) -> dict:
    if path not in REPO:
        return {"error": f"{path}: no such file"}
    return {"path": path, "content": REPO[path]}


@observe(name="run_tests", span_type="TOOL")
def run_tests() -> dict:
    return {"exit_code": 1, "output": TEST_OUTPUT}


@observe(name="write_file", span_type="TOOL")
def write_file(path: str, content: str) -> dict:
    REPO[path] = content
    return {"path": path, "bytes": len(content)}


TOOL_FUNCTIONS = {
    "list_files": list_files,
    "read_file": read_file,
    "run_tests": run_tests,
    "write_file": write_file,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List every file in the repository.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read one file from the repository.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the test suite and return its output.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Replace the content of one file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
]

# A system prompt long enough to be cached. OpenAI caches a
# prefix from 1024 tokens; this one is about 1500. The policy
# text is repeated on purpose: what matters is the size and that
# it is byte-identical on every call.
POLICY = """
You are a careful coding agent working in a small Python service.
Work through the tools only. Read before you write, run the tests
after every change, and keep every change as small as it can be.
Never invent a file that the tools have not shown you. When the
task is complete, answer in at most three sentences: what was
wrong, what you changed, and what the tests say now.

Rules of the repository:
1. A change to parsing must keep every existing test passing.
2. A change to the ledger must not alter the posted total.
3. Monetary values are integers in cents. Never use floats.
4. Regular expressions must be anchored on a label such as
   "Total:" and must accept thousands separators.
5. A test failure is a bug in the code unless the test itself
   contradicts a rule above.
6. Do not rename files. Do not add dependencies.
7. Before writing a file, read it once in this turn.
8. After writing a file, run the tests once.
9. If the tests still fail after two attempts, stop and report.
10. Report the exit code of the last test run in your answer.
"""
SYSTEM_PROMPT = "You are a coding agent.\n" + POLICY * 6

TURN_PROMPTS = [
    "The invoice parser fails on totals with a thousands separator. "
    "Find the failing test, fix the parser, and run the tests.",
    "Now make sure the ledger rejects an entry list that does not "
    "sum to the total, and confirm with the tests.",
    "Summarize what changed in this session in one paragraph.",
]


def completion(messages: list) -> litellm.ModelResponse:
    kwargs = dict(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        # LiteLLM `metadata` is where Laminar reads the session and
        # the user from. LiteLLM's own callback does not forward
        # these keys.
        metadata={
            "session_id": SESSION_ID,
            "user_id": USER_ID,
            "tags": ["laminar-litellm-demo"],
        },
    )
    if os.environ.get("OPENAI_API_BASE"):
        kwargs["api_base"] = os.environ["OPENAI_API_BASE"]
    return litellm.completion(**kwargs)


@observe(name="agent_turn")
def agent_turn(history: list, prompt: str) -> str:
    if TRACER != "litellm-otel":
        # Stamps the ids on the turn's trace. Needs an active
        # span, which the decorator above opened.
        from lmnr import Laminar

        Laminar.set_trace_session_id(SESSION_ID)
        Laminar.set_trace_user_id(USER_ID)

    history.append({"role": "user", "content": prompt})
    for _ in range(8):
        response = completion(history)
        message = response.choices[0].message
        usage = response.usage.model_dump() if response.usage else {}
        cached = (usage.get("prompt_tokens_details") or {}).get(
            "cached_tokens"
        )
        print(
            f"  model call: prompt={usage.get('prompt_tokens')} "
            f"cached={cached} completion={usage.get('completion_tokens')} "
            f"tool_calls={len(message.tool_calls or [])}"
        )
        history.append(message.model_dump(exclude_none=True))
        if not message.tool_calls:
            return message.content or ""
        for call in message.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            fn = TOOL_FUNCTIONS[call.function.name]
            result = fn(**args)
            print(f"  tool: {call.function.name}({args})")
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result),
                }
            )
    return "stopped after too many tool calls"


def main() -> None:
    print(f"tracer={TRACER} model={MODEL} session={SESSION_ID}")
    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    for i, prompt in enumerate(TURN_PROMPTS[:TURNS]):
        print(f"turn {i + 1}: {prompt}")
        answer = agent_turn(history, prompt)
        print(f"  answer: {answer.strip()[:200]}")
    flush()


if __name__ == "__main__":
    main()
