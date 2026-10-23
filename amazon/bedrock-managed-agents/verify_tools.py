"""Verify AWS requests and the real MCP client protocol against local boundaries."""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import boto3
from botocore.stub import Stubber
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
import aws_tools  # noqa: E402
import mcp_tools  # noqa: E402

requests = []
fail_mcp = False


class MCPServer(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        requests.append(request)
        method = request["method"]
        if "id" not in request:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if method == "initialize":
            result = {"protocolVersion": request["params"]["protocolVersion"], "capabilities": {"tools": {}},
                      "serverInfo": {"name": "test-aws-knowledge", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [{"name": mcp_tools.REMOTE_TOOL, "description": "Search AWS docs",
                                 "inputSchema": {"type": "object", "properties": {"search_phrase": {"type": "string"}},
                                                 "required": ["search_phrase"]}}]}
        elif method == "tools/call":
            assert request["params"]["name"] == mcp_tools.REMOTE_TOOL
            assert request["params"]["arguments"] == {
                "search_phrase": "DynamoDB point-in-time recovery", "limit": 3, "topics": ["reference_documentation"],
            }
            result = {"isError": fail_mcp, "content": [{"type": "text", "text": "test documentation result"}]}
        else:
            raise AssertionError(method)
        body = json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    global fail_mcp
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)
    session = boto3.Session(aws_access_key_id="test", aws_secret_access_key="test", region_name="us-west-2")
    ddb = session.client("dynamodb")
    ssm = session.client("ssm")
    server = ThreadingHTTPServer(("127.0.0.1", 0), MCPServer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch.dict(os.environ, {"TOOL_DATA_SOURCE": "aws", "ORDERS_TABLE_NAME": "test-orders",
                                     "RETURN_POLICY_PARAMETER": "/test/policy"}), \
                patch("aws_tools.boto3.client", side_effect=lambda service, **kwargs: {"dynamodb": ddb, "ssm": ssm}[service]), \
                Stubber(ddb) as orders, Stubber(ssm) as policy:
            expected = {"TableName": "test-orders", "Key": {"order_id": {"S": "ORD-1001"}}, "ConsistentRead": True}
            orders.add_response("get_item", {"Item": {"payload": {"S": json.dumps(aws_tools.ORDERS["ORD-1001"])}}}, expected)
            policy.add_response("get_parameter", {"Parameter": {"Value": json.dumps(aws_tools.POLICY)}},
                                {"Name": "/test/policy", "WithDecryption": False})
            orders.add_client_error("get_item", "AccessDeniedException", "Denied by test policy", expected_params=expected)
            with tracer.start_as_current_span("test.aws-tools"):
                assert aws_tools.lookup_order("ORD-1001")["days_since_delivery"] == 7
                assert aws_tools.get_return_policy()["return_window_days"] == 30
                try:
                    aws_tools.lookup_order("ORD-1001")
                    raise AssertionError("Denied AWS call must not fall back to fixtures")
                except RuntimeError as exc:
                    assert "AccessDeniedException" in str(exc)
            orders.assert_no_pending_responses()
            policy.assert_no_pending_responses()
        with patch("mcp_tools.ENDPOINT", f"http://127.0.0.1:{server.server_port}/mcp"):
            with tracer.start_as_current_span("test.mcp-tools"):
                with tracer.start_as_current_span("execute_tool search_aws_docs"):
                    result = mcp_tools.search_aws_docs("DynamoDB point-in-time recovery")
                assert result["results"] == "test documentation result"
                fail_mcp = True
                try:
                    with tracer.start_as_current_span("execute_tool search_aws_docs"):
                        mcp_tools.search_aws_docs("DynamoDB point-in-time recovery")
                    raise AssertionError("MCP isError must propagate")
                except RuntimeError:
                    pass
        methods = [r["method"] for r in requests]
        assert methods.count("initialize") == 2 and methods.count("tools/list") == 2 and methods.count("tools/call") == 2
        spans = exporter.get_finished_spans()
        assert sum(s.name == "dynamodb.get_item" for s in spans) == 2
        assert any(s.name == "dynamodb.get_item" and s.status.is_ok is False for s in spans)
        calls = [s for s in spans if s.name == "execute_tool search_aws_docs"]
        assert len(calls) == 2 and sum(s.status.is_ok is False for s in calls) == 1
        ids = {s.context.span_id for s in spans}
        assert all(not s.parent or s.parent.span_id in ids for s in spans)
        assert sum(s.name == "MCP send initialize" for s in spans) == 2
        assert sum(s.name == "MCP send tools/list" for s in spans) == 2
        assert sum(s.name == "MCP send tools/call " + mcp_tools.REMOTE_TOOL for s in spans) == 2
        assert all(s.attributes["mcp.tool.name"] == mcp_tools.REMOTE_TOOL for s in calls)
        assert not any(s.name.startswith("mcp.") for s in spans), "Duplicated manual MCP RPC spans"
        print(json.dumps({"passed": True, "aws_requests": 3, "mcp_sessions": 2, "spans": len(spans)}))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        provider.shutdown()


if __name__ == "__main__":
    main()
