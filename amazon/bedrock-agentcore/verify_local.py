"""Exercise real Strands/tool/OTLP code using stubbed Bedrock responses."""

import gzip
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import boto3
from botocore.stub import Stubber
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
requests = []


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        request = ExportTraceServiceRequest.FromString(body)
        requests.append((self.path, dict(self.headers), request))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


def response(content, stop_reason):
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop_reason,
        "usage": {"inputTokens": 20, "outputTokens": 10, "totalTokens": 30},
        "metrics": {"latencyMs": 1},
    }


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ.update({
        "OODLE_INSTANCE": "offline-test",
        "OODLE_API_KEY": "offline-test-key",
        "OODLE_OTLP_ENDPOINT": f"http://127.0.0.1:{server.server_port}",
        "AWS_EC2_METADATA_DISABLED": "true",
    })
    is_agentcore = (Path(__file__).parent / "deploy.py").exists()
    if is_agentcore:
        import main as runtime_app

        provider = runtime_app.provider
    else:
        from telemetry import setup_telemetry

        provider = setup_telemetry("amazon-bedrock-demo")

    from strands.models import BedrockModel
    from support_agent import DEFAULT_PROMPT, run_agent

    model = BedrockModel(
        model_id="us.amazon.nova-lite-v1:0",
        boto_session=boto3.Session(aws_access_key_id="test", aws_secret_access_key="test", region_name="us-west-2"),
        streaming=False,
    )
    results = []
    try:
        with Stubber(model.client) as stub:
            stub.add_response("converse", response([
                {"toolUse": {"toolUseId": "order", "name": "lookup_order", "input": {"order_id": "ORD-1001"}}},
                {"toolUse": {"toolUseId": "policy", "name": "get_return_policy", "input": {}}},
            ], "tool_use"))
            stub.add_response("converse", response([{"text": "Delivered 7 days ago; eligible for a return within 30 days."}], "end_turn"))
            stub.add_response("converse", response([
                {"toolUse": {"toolUseId": "failure", "name": "lookup_order", "input": {"order_id": "ORD-ERROR"}}},
            ], "tool_use"))
            stub.add_response("converse", response([{"text": "The order backend is unavailable. Please try again later."}], "end_turn"))

            with patch("support_agent.BedrockModel", return_value=model):
                if is_agentcore:
                    from starlette.testclient import TestClient

                    with TestClient(runtime_app.app) as client:
                        assert client.get("/ping").status_code == 200
                        for prompt in (DEFAULT_PROMPT, "Look up ORD-ERROR"):
                            res = client.post("/invocations", json={"prompt": prompt}, headers={
                                "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": "offline-demo-session-12345678901234567890",
                            })
                            assert res.status_code == 200, res.text
                            results.append(res.json())
                else:
                    results.append(run_agent(DEFAULT_PROMPT))
                    results.append(run_agent("Look up ORD-ERROR"))
            stub.assert_no_pending_responses()
        provider.force_flush()

        spans = []
        for path, headers, request in requests:
            assert path == "/v1/traces"
            headers = {key.lower(): value for key, value in headers.items()}
            assert headers["x-api-key"] == "offline-test-key"
            assert headers["x-oodle-instance"] == "offline-test"
            assert headers["content-encoding"] == "gzip"
            for resource in request.resource_spans:
                for scope in resource.scope_spans:
                    spans.extend(scope.spans)
        assert spans, "No OTLP spans received"
        attrs = [{a.key: a.value for a in span.attributes} for span in spans]
        operations = [a["gen_ai.operation.name"].string_value for a in attrs if "gen_ai.operation.name" in a]
        assert "invoke_agent" in operations, operations
        assert operations.count("chat") == 4, operations
        assert operations.count("execute_tool") == 3, operations
        assert any(s.status.code == 2 and "lookup_order" in s.name for s in spans), "Tool failure was not marked ERROR"
        assert any(a.get("gen_ai.usage.input_tokens") and a["gen_ai.usage.input_tokens"].int_value == 20 for a in attrs)
        content = [a[k].string_value for a in attrs for k in ("gen_ai.input.messages", "gen_ai.output.messages") if k in a]
        assert content, "Transcript is missing"
        if os.environ.get("CAPTURE_CONTENT", "true").lower() == "true":
            assert any("ORD-1001" in value for value in content)
        else:
            assert all(value == "[REDACTED]" for value in content), content
        trace_ids = {span.trace_id.hex() for span in spans}
        assert len(trace_ids) == 2, trace_ids
        assert all(result["trace_id"] in trace_ids for result in results), results
        assert len({(span.trace_id, span.span_id) for span in spans}) == len(spans), "Duplicate export"
        span_ids = {span.span_id for span in spans}
        assert all(not span.parent_span_id or span.parent_span_id in span_ids for span in spans), "Broken parent links"
        assert "30 days" in results[0]["answer"]
        assert "unavailable" in results[1]["answer"]
        print(json.dumps({"passed": True, "traces": len(trace_ids), "spans": len(spans), "operations": operations}))
    finally:
        provider.shutdown()
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
