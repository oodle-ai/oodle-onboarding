"""Check the managed-agent protocol and actual OTLP export with no external calls."""

import gzip
import json
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import botocore.session
from botocore.exceptions import EventStreamError
from botocore.validate import validate_parameters
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
from managed_agent import run_agent  # noqa: E402
from telemetry import setup_telemetry  # noqa: E402

received = []
service = botocore.session.get_session().get_service_model("bedrock-agent-runtime")
operation = service.operation_model("InvokeAgent")


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        assert self.path == "/v1/traces"
        assert self.headers["X-API-KEY"] == "offline-key"
        assert self.headers["X-OODLE-INSTANCE"] == "offline-test"
        assert self.headers["Content-Encoding"] == "gzip"
        received.append(ExportTraceServiceRequest.FromString(gzip.decompress(body)))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


class Stream:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def __iter__(self):
        for event in self.events:
            if isinstance(event, Exception):
                raise event
            validate_parameters(event, operation.output_shape.members["completion"])
            yield event

    def close(self):
        self.closed = True


class Client:
    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.calls = []
        self.streams = []

    def invoke_agent(self, **request):
        validate_parameters(request, operation.input_shape)
        assert request["enableTrace"] is True
        self.calls.append(request)
        stream = Stream(self.rounds.pop(0))
        self.streams.append(stream)
        return {"completion": stream}


def model_events(trace_id, tokens=20):
    now = datetime.now(timezone.utc) - timedelta(milliseconds=100)
    def event(payload):
        return {"trace": {"agentId": "ABCDEFGHIJ", "agentAliasId": "TSTALIASID",
                          "agentVersion": "DRAFT", "sessionId": "offline-session", "eventTime": now,
                          "trace": {"orchestrationTrace": payload}}}
    return [
        event({"modelInvocationInput": {"traceId": trace_id, "foundationModel": "amazon.nova-lite-v1:0",
                                       "type": "ORCHESTRATION", "text": "private model input"}}),
        event({"modelInvocationOutput": {"traceId": trace_id, "rawResponse": {"content": "private output"},
                                        "metadata": {"startTime": now, "endTime": now + timedelta(milliseconds=50),
                                                     "usage": {"inputTokens": tokens, "outputTokens": 10}}}}),
    ]


def control(order_id):
    return {"returnControl": {"invocationId": "invocation-001", "invocationInputs": [
        {"functionInvocationInput": {"actionGroup": "OrderSupport", "function": "lookup_order",
                                     "parameters": [{"name": "order_id", "type": "string", "value": order_id}]}},
        {"functionInvocationInput": {"actionGroup": "OrderSupport", "function": "get_return_policy"}},
        {"functionInvocationInput": {"actionGroup": "OrderSupport", "function": "search_aws_docs",
                                     "parameters": [{"name": "search_phrase", "type": "string", "value": "DynamoDB recovery"}]}},
    ]}}


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ.update({"TOOL_DATA_SOURCE": "fixture", "OODLE_INSTANCE": "offline-test", "OODLE_API_KEY": "offline-key",
                       "OODLE_OTLP_ENDPOINT": f"http://127.0.0.1:{server.server_port}"})
    provider = setup_telemetry("amazon-bedrock-managed-agents-demo")
    try:
        clients = []
        for order_id in ("ORD-1001", "ORD-ERROR"):
            first = model_events("step1")
            # Duplicate service output must not double count tokens.
            first.append(first[-1])
            first.append(control(order_id))
            client = Client(first, model_events("step2") + [{"chunk": {"bytes": "Answer: café".encode()[:-1]}},
                                                          {"chunk": {"bytes": "Answer: café".encode()[-1:]}}])
            with patch("tools.search_aws_docs", return_value={"results": "offline documentation"}) as docs:
                result = run_agent(client, "ABCDEFGHIJ", "TSTALIASID", f"Check {order_id}")
                docs.assert_called_once_with("DynamoDB recovery")
            assert result["answer"] == "Answer: café"
            assert len(client.calls) == 2
            first_call, continuation = client.calls
            assert first_call["sessionId"] == continuation["sessionId"]
            assert "inputText" not in continuation
            state = continuation["sessionState"]
            assert state["invocationId"] == "invocation-001"
            lookup, policy, documentation = [x["functionResult"] for x in state["returnControlInvocationResults"]]
            assert policy["function"] == "get_return_policy"
            assert json.loads(documentation["responseBody"]["TEXT"]["body"])["results"] == "offline documentation"
            assert json.loads(policy["responseBody"]["TEXT"]["body"])["return_window_days"] == 30
            if order_id == "ORD-ERROR":
                assert lookup["responseState"] == "REPROMPT"
            else:
                assert json.loads(lookup["responseBody"]["TEXT"]["body"])["days_since_delivery"] == 7
                assert "responseState" not in lookup
            clients.append(client)

        client = Client(model_events("interrupted")[:1] + [EventStreamError(
            {"Error": {"Code": "accessDeniedException", "Message": "Denied by test policy"}}, "InvokeAgent",
        )])
        try:
            run_agent(client, "ABCDEFGHIJ", "TSTALIASID")
            raise AssertionError("Stream failure was swallowed")
        except EventStreamError:
            pass
        clients.append(client)

        client = Client([control("ORD-1001")])
        try:
            with patch("tools.search_aws_docs", return_value={"results": "offline documentation"}):
                run_agent(client, "ABCDEFGHIJ", "TSTALIASID", max_rounds=1)
            raise AssertionError("Unbounded return-control loop")
        except RuntimeError as exc:
            assert "exceeded" in str(exc)
        clients.append(client)
        assert all(not c.rounds and all(s.closed for s in c.streams) for c in clients)

        provider.force_flush()
        spans = [s for batch in received for rs in batch.resource_spans for scope in rs.scope_spans for s in scope.spans]
        attrs = [{a.key: a.value for a in s.attributes} for s in spans]
        roots = [s for s, a in zip(spans, attrs) if a.get("gen_ai.operation.name") and a["gen_ai.operation.name"].string_value == "invoke_agent"]
        models = [s for s, a in zip(spans, attrs) if a.get("gen_ai.operation.name") and a["gen_ai.operation.name"].string_value == "chat"]
        assert len(roots) == 4 and len(models) == 5, (len(roots), len(models))
        assert sum(a["gen_ai.usage.input_tokens"].int_value for a in attrs if "gen_ai.usage.input_tokens" in a) == 80
        assert sum(s.status.code == 2 for s in roots) == 2
        assert any(s.status.code == 2 and s.name == "execute_tool lookup_order" for s in spans)
        assert any(s.status.code == 2 for s in models), "Incomplete model span must be marked as error"
        assert all(49_000_000 <= s.end_time_unix_nano - s.start_time_unix_nano <= 51_000_000
                   for s in models if s.status.code != 2)
        ids = {s.span_id for s in spans}
        assert all(not s.parent_span_id or s.parent_span_id in ids for s in spans)
        content_fields = {"gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.tool.call.arguments",
                          "gen_ai.tool.call.result", "aws.bedrock.model.input", "aws.bedrock.model.output"}
        content = [key for a in attrs for key in a if key in content_fields]
        assert bool(content) == (os.environ.get("CAPTURE_CONTENT", "true").lower() == "true")
        print(json.dumps({"passed": True, "traces": len(roots), "spans": len(spans), "model_spans": len(models)}))
    finally:
        provider.shutdown()
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
