"""One turn of the agent, and one tool call. Both emit GenAI spans.

The improver's gate runs this same agent too: Oodle's experiment runner calls it
through a webhook (see web.py), so a candidate prompt is tested on the real path.
"""

import json
import logging
import os
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from opentelemetry.trace import Status, StatusCode

from otel import AGENT_NAME, tracer
from tools import TOOLS

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

log = logging.getLogger("agent")
_client = None


def client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


class QuotaExhausted(Exception):
    """The daily cap. Retrying cannot help, so Temporal must not retry it either
    (see non_retryable_error_types in worker.py)."""


def _quota(exc):
    """Pull the quota id and the server's own retry delay out of a 429."""
    quota, retry_after = None, None
    for detail in ((exc.details or {}).get("error") or {}).get("details") or []:
        for violation in detail.get("violations") or []:
            quota = violation.get("quotaId") or quota
        if detail.get("retryDelay"):
            retry_after = detail["retryDelay"]
    return quota, retry_after


def generate(**kwargs):
    """A free-tier Gemini key caps both per minute and per DAY, and one agent run
    spends several calls. An eval-gate run is a whole agent loop inside a single
    Activity, so Temporal's retry cannot cover a 429 halfway through it.

    A per-minute cap is worth waiting out. A per-day cap is not: retrying it just
    burns two minutes to fail anyway, so say so plainly and give up."""
    for attempt in range(4):
        try:
            return client().models.generate_content(model=MODEL, **kwargs)
        except (genai_errors.ClientError, genai_errors.ServerError) as exc:
            if exc.code not in (429, 503):
                raise
            quota, retry_after = _quota(exc)
            if quota and "PerDay" in quota:
                raise QuotaExhausted(
                    f"Gemini daily free-tier quota exhausted for {MODEL} ({quota}). "
                    f"It resets at midnight Pacific. Set GEMINI_MODEL to another model "
                    f"- the cap is per model - or use a paid key."
                )  # not `from exc`: this message is the actionable one, keep it the leaf
            if attempt == 3:
                raise
            delay = 15 * (attempt + 1)
            log.warning("Gemini %s (%s, retryDelay %s), backing off %ds",
                        exc.code, quota or "no quota id", retry_after or "-", delay)
            time.sleep(delay)


def llm_turn(system: str, tool_declarations: list, history: list) -> dict:
    """Ask the model what to do next. Returns the model's content plus any tool calls."""
    response = generate(
        contents=history,
        config=types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=tool_declarations)],
            temperature=0.2,
        ),
    )

    candidates = response.candidates or []
    content = candidates[0].content if candidates else types.Content(role="model", parts=[])

    tool_calls, text = [], None
    for part in content.parts or []:
        if part.function_call:
            tool_calls.append({
                "name": part.function_call.name,
                "args": dict(part.function_call.args or {}),
            })
        elif part.text:
            text = (text or "") + part.text

    return {
        # Round-tripped verbatim: thinking models reject history whose function
        # calls have lost their thought_signature.
        "model_content": content.model_dump(mode="json", exclude_none=True),
        "text": text,
        "tool_calls": tool_calls,
    }


def run_tool(name: str, args: dict) -> dict:
    """Execute a tool inside an `execute_tool` span Oodle recognises."""
    with tracer().start_as_current_span(f"execute_tool {name}") as span:
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        span.set_attribute("gen_ai.agent.name", AGENT_NAME)
        span.set_attribute("gen_ai.tool.name", name)
        span.set_attribute("gen_ai.tool.type", "function")
        span.set_attribute("gen_ai.tool.call.arguments", json.dumps(args, default=str))

        fn = TOOLS.get(name)
        if fn is None:
            result = {"error": "tool_not_found", "message": f"no tool named {name!r}"}
        else:
            result = fn(**args)

        span.set_attribute("gen_ai.tool.call.result", json.dumps(result, default=str))
        if "error" in result:
            span.set_attribute("error.type", result["error"])
            span.set_status(Status(StatusCode.ERROR, result["message"]))
        return result


def tool_response(name: str, result: dict) -> dict:
    return {"role": "user", "parts": [{"function_response": {"name": name, "response": result}}]}
