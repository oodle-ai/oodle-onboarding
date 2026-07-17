"""OpenLit demo app showcasing AI Observability, Guardrails, and MCP features.

All LLM calls (Gemini) and MCP tool invocations are automatically instrumented
by the OpenLit SDK and exported to Oodle via an OpenTelemetry Collector.
"""

import asyncio
import os

import openlit
from flask import Flask, jsonify, request
from google import genai
from google.genai import types
from mcp import ClientSession
from mcp.client.sse import sse_client
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor

app = Flask(__name__)
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

openlit.init(
    otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"),
    application_name="openlit-demo",
)
FlaskInstrumentor().instrument_app(app)

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-server:8080/sse")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


tracer = trace.get_tracer("openlit-demo")


def _user_content(text: str) -> list[types.Content]:
    """Wrap a string in a Content object so OpenLit captures it as a user message."""
    return [types.Content(role="user", parts=[types.Part(text=text)])]


def _gemini_call(
    model: str,
    contents: list[types.Content],
    system_instruction: str,
    operation_name: str = "chat",
) -> str:
    """Call Gemini wrapped in a span that sets GenAI attributes before the call,
    so error traces still carry the model/provider metadata Oodle needs."""
    with tracer.start_as_current_span(
        f"{operation_name} {model}", kind=trace.SpanKind.CLIENT
    ) as span:
        span.set_attribute("gen_ai.system", "gemini")
        span.set_attribute("gen_ai.request.model", model)
        span.set_attribute("gen_ai.operation.name", operation_name)
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config={"system_instruction": system_instruction},
        )
        return response.text

guard_pipeline = openlit.guard.Pipeline(guards=[
    openlit.guard.PromptInjection(),
    openlit.guard.SensitiveTopic(),
])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "openlit-demo"})


# --- AI Observability: /chat and /summarize ---


@app.route("/chat", methods=["POST"])
def chat():
    """Send a chat message to Gemini.

    Request body: {"message": "Hello!", "model": "gemini-flash-latest"}
    """
    body = request.get_json(force=True)
    message = body.get("message", "Say hello!")
    model = body.get("model", DEFAULT_MODEL)

    try:
        reply = _gemini_call(
            model, _user_content(message),
            "You are a helpful assistant. Keep responses concise.",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    return jsonify({"reply": reply, "model": model})


@app.route("/summarize", methods=["POST"])
def summarize():
    """Summarize a block of text.

    Request body: {"text": "Long text to summarize..."}
    """
    body = request.get_json(force=True)
    text = body.get("text", "")
    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        summary = _gemini_call(
            DEFAULT_MODEL, _user_content(text),
            "Summarize the following text in 1-2 sentences.",
            operation_name="summarize",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    return jsonify({"summary": summary})


# --- Guardrails: /safe-chat ---


@app.route("/safe-chat", methods=["POST"])
def safe_chat():
    """Chat with guardrail pre-check. The prompt is screened for injection,
    sensitive content, and topic violations before being sent to Gemini.

    Request body: {"message": "Hello!", "model": "gemini-flash-latest"}
    """
    body = request.get_json(force=True)
    message = body.get("message", "Say hello!")
    model = body.get("model", DEFAULT_MODEL)

    with tracer.start_as_current_span("safe-chat", kind=trace.SpanKind.SERVER) as span:
        span.set_attribute("gen_ai.operation.name", "guardrail")
        span.set_attribute("gen_ai.system", "openlit")
        span.set_attribute("gen_ai.request.model", model)

        result = guard_pipeline.evaluate(message)

        if result.action.value == "deny":
            violations = [
                {
                    "guard": r.guard_name,
                    "score": r.score,
                    "classification": r.classification,
                    "explanation": r.explanation,
                }
                for r in result.results
            ]
            span.set_attribute("gen_ai.guardrail.action", "deny")
            span.set_attribute("gen_ai.guardrail.violations", str(violations))
            return jsonify({"blocked": True, "violations": violations}), 422

        span.set_attribute("gen_ai.guardrail.action", "allow")

        try:
            reply = _gemini_call(
                model, _user_content(message),
                "You are a helpful assistant. Keep responses concise.",
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 502

        return jsonify({"reply": reply, "model": model, "guard_passed": True})


# --- MCP Observability: /mcp-search ---

search_tool = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="duckduckgo_web_search",
        description="Search the web for information matching a query. "
                    "Returns titles, snippets, and source URLs.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
            },
            "required": ["query"],
        },
    ),
])

SEARCH_SYSTEM_INSTRUCTION = (
    "You are a helpful assistant. Use the duckduckgo_web_search "
    "tool to find information, then answer concisely."
)

search_config = types.GenerateContentConfig(
    tools=[search_tool],
    tool_config=types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(mode="ANY"),
    ),
    system_instruction=SEARCH_SYSTEM_INSTRUCTION,
)


async def _call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """Connect to the MCP server and invoke a tool."""
    async with sse_client(MCP_SERVER_URL) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            return result.content[0].text if result.content else ""


@app.route("/mcp-search", methods=["POST"])
def mcp_search():
    """Agentic search using Gemini function calling + MCP tool execution.

    Turn 1: Gemini receives the query and returns a function_call.
    We execute it against the MCP server.
    Turn 2: We send the tool result back; Gemini synthesizes the answer.

    Request body: {"query": "What is OpenTelemetry?", "synthesize": true}
    """
    body = request.get_json(force=True)
    query = body.get("query", "")
    synthesize = body.get("synthesize", True)

    if not query:
        return jsonify({"error": "query is required"}), 400

    model = body.get("model", DEFAULT_MODEL)

    try:
        # Turn 1 — Gemini decides which tool to call
        response = client.models.generate_content(
            model=model, contents=query, config=search_config,
        )

        if not response.function_calls:
            return jsonify({"answer": response.text, "tool_result": None})

        fc = response.function_calls[0]
        tool_args = dict(fc.args) if fc.args else {"query": query}

        # Execute the tool via the MCP server
        tool_result = asyncio.run(_call_mcp_tool(fc.name, tool_args))

        if not synthesize:
            return jsonify({"tool_result": tool_result})

        # Turn 2 — full history including the real function_call (with
        # thought_signature) and the tool response so Gemini can answer.
        user_content = types.Content(
            role="user", parts=[types.Part.from_text(text=query)],
        )
        model_fc_content = response.candidates[0].content
        tool_response_content = types.Content(
            role="tool",
            parts=[types.Part.from_function_response(
                name=fc.name,
                response={"result": tool_result},
            )],
        )

        final = client.models.generate_content(
            model=model,
            contents=[user_content, model_fc_content, tool_response_content],
            config=types.GenerateContentConfig(
                tools=[search_tool],
                system_instruction=SEARCH_SYSTEM_INSTRUCTION,
            ),
        )
        answer = final.text

    except Exception as e:
        return jsonify({"error": str(e)}), 502

    return jsonify({"answer": answer, "tool_result": tool_result})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8090"))
    app.run(host="0.0.0.0", port=port)
