"""Call real AWS/MCP tools directly and emit a tool-check trace, without a model."""

import json
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from opentelemetry import trace

from aws_tools import get_return_policy, lookup_order
from mcp_tools import search_aws_docs
from telemetry import setup_telemetry


def run_tool_checks(session_id=None):
    tracer = trace.get_tracer(__name__)
    results = {}
    with tracer.start_as_current_span("tools.smoke", attributes={
        "demo.run.type": "tool-check", "session.id": session_id or str(uuid.uuid4()),
        "demo.data_source": os.environ.get("TOOL_DATA_SOURCE", "aws"),
    }) as root:
        trace_id = format(root.get_span_context().trace_id, "032x")
        print("Oodle trace ID:", trace_id, flush=True)
        for name, function, arguments in [
            ("lookup_order", lookup_order, {"order_id": "ORD-1001"}),
            ("get_return_policy", get_return_policy, {}),
            ("search_aws_docs", search_aws_docs, {"search_phrase": "DynamoDB point-in-time recovery"}),
        ]:
            try:
                with tracer.start_as_current_span("execute_tool " + name, attributes={
                    "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": name,
                }) as span:
                    capture = os.environ.get("CAPTURE_CONTENT", "true").lower() == "true"
                    if capture:
                        span.set_attribute("gen_ai.tool.call.arguments", json.dumps(arguments))
                    result = function(**arguments)
                    if capture:
                        span.set_attribute("gen_ai.tool.call.result", json.dumps(result))
                    results[name] = {"ok": True}
                    print(name + ": OK", flush=True)
            except Exception as exc:
                results[name] = {"ok": False, "error": str(exc)}
                print(f"{name}: FAILED: {exc}", flush=True)
        failures = [name for name, result in results.items() if not result["ok"]]
        if failures:
            from opentelemetry.trace import Status, StatusCode
            root.set_status(Status(StatusCode.ERROR, "Tool checks failed: " + ", ".join(failures)))
        return {"trace_id": trace_id, "mode": "tool-check", "ok": not failures, "tools": results}


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    provider = setup_telemetry("amazon-bedrock-agentcore-demo")
    try:
        result = run_tool_checks()
        print(json.dumps(result, indent=2))
        if not result["ok"]:
            raise SystemExit(1)
    finally:
        provider.shutdown()


if __name__ == "__main__":
    main()
