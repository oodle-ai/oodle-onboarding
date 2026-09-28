"""Offline end-to-end check of the dual write, with no Laminar or Oodle account.

Starts a local gRPC OTLP receiver in place of Laminar and a local HTTP OTLP
receiver in place of the Oodle collector, runs one mocked agent session
through the real tracing setup, and compares what each side received.

    python verify_local.py              # mirror on: expect every check to pass
    python verify_local.py --no-mirror  # pre-fix behaviour: parent checks fail
"""

import argparse
import asyncio
import gzip
import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent import futures
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import grpc
from opentelemetry.proto.collector.logs.v1 import logs_service_pb2, logs_service_pb2_grpc
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc
from opentelemetry.proto.common.v1.common_pb2 import AnyValue

_EMPTY = AnyValue()

LAMINAR_PORT = 18443
OODLE_PORT = 14318
SERVICE_NAME = "litellm-laminar-demo"


@dataclass
class Row:
    service: str
    name: str
    trace_id: str
    span_id: str
    parent_id: str
    attributes: dict


class Capture:
    def __init__(self) -> None:
        self.rows: list[Row] = []
        self._lock = threading.Lock()

    def add(self, request: trace_service_pb2.ExportTraceServiceRequest) -> None:
        rows = []
        for rs in request.resource_spans:
            service = next((a.value.string_value for a in rs.resource.attributes if a.key == "service.name"), "")
            for ss in rs.scope_spans:
                for s in ss.spans:
                    attrs = {a.key: a.value for a in s.attributes}
                    rows.append(Row(service, s.name, s.trace_id.hex(), s.span_id.hex(), s.parent_span_id.hex(), attrs))
        with self._lock:
            self.rows.extend(rows)


def start_receivers() -> tuple[Capture, Capture, callable]:
    laminar, oodle = Capture(), Capture()

    class Traces(trace_service_pb2_grpc.TraceServiceServicer):
        def Export(self, request, context):
            laminar.add(request)
            return trace_service_pb2.ExportTraceServiceResponse()

    class Logs(logs_service_pb2_grpc.LogsServiceServicer):
        def Export(self, request, context):
            return logs_service_pb2.ExportLogsServiceResponse()

    grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    trace_service_pb2_grpc.add_TraceServiceServicer_to_server(Traces(), grpc_server)
    logs_service_pb2_grpc.add_LogsServiceServicer_to_server(Logs(), grpc_server)
    grpc_server.add_insecure_port(f"127.0.0.1:{LAMINAR_PORT}")
    grpc_server.start()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            request = trace_service_pb2.ExportTraceServiceRequest()
            request.ParseFromString(body)
            oodle.add(request)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            return

    http_server = ThreadingHTTPServer(("127.0.0.1", OODLE_PORT), Handler)
    threading.Thread(target=http_server.serve_forever, daemon=True).start()

    def stop() -> None:
        grpc_server.stop(0)
        http_server.shutdown()

    return laminar, oodle, stop


def _text(value) -> str:
    kind = value.WhichOneof("value")
    return "" if kind is None else str(getattr(value, kind))


def _json(row: Row, key: str) -> dict:
    try:
        parsed = json.loads(_text(row.attributes[key]))
    except (KeyError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


ROUTE_FIELDS = 27
LLM_SPANS = {"llm_call", "llm_call_stream"}


CONTENT_KEYS = {"lmnr.span.input", "lmnr.span.output", "gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.tool.definitions"}


def attribute_checks(rows: list[Row], backend: str, with_content: bool) -> list[tuple[str, bool]]:
    """Complex attributes a backend's copy of the trace must carry.

    Content (messages, tool schemas, tool and turn payloads) is expected only
    where it is captured; elsewhere it must be absent from every span.
    """
    prefix = route_audit.ROUTE_ATTRIBUTE_PREFIX

    def route(row: Row) -> dict[str, str]:
        return {k: _text(v) for k, v in row.attributes.items() if k.startswith(prefix)}

    llm = [r for r in rows if r.name in LLM_SPANS]
    streams = [r for r in rows if r.name == "llm_call_stream"]
    loops = [r for r in rows if r.name == "run_agent_with_messages"]
    tools = [r for r in rows if r.name == "tool_call [bash_execute]"]
    usage_keys = {
        "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "llm.usage.total_tokens",
        "llm.usage.visible_output_tokens", "cache.read_tokens", "cache.creation_tokens",
        "cache.hit_pct", "llm.resolved.reasoning_effort", "llm.model_selection.fast_mode_enabled",
    }
    checks = [
        (f"{backend}: every LLM span has all {ROUTE_FIELDS} route fields, event=route_started",
         bool(llm) and all(len(route(r)) == ROUTE_FIELDS and route(r)[prefix + "event"] == "route_started" for r in llm)),
        (f"{backend}: turn loops and agent_session end with event=route_completed",
         bool(loops) and all(route(r).get(prefix + "event") == "route_completed"
                             for r in rows if r.name in {"run_agent_with_messages", "agent_session"})),
        (f"{backend}: route input batch correlates each call to its turn",
         bool(streams) and all(len(route(r).get(prefix + "input_batch_id", "")) == 64 for r in streams)),
        (f"{backend}: LLM spans carry usage, cache and resolved-config attributes",
         bool(llm) and all(usage_keys <= set(r.attributes) for r in llm)),
    ]
    if not with_content:
        return checks + [
            (f"{backend}: no prompt, completion, tool schema or payload content on any span",
             bool(rows) and not any(CONTENT_KEYS & set(r.attributes) for r in rows)),
        ]
    return checks + [
        (f"{backend}: LLM spans carry input messages, output messages and tool definitions",
         bool(streams) and all({"gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.tool.definitions"} <= set(r.attributes) for r in streams)),
        (f"{backend}: tool spans carry {{tool_id, tool_name, args}} in and {{stdout, exitCode}} out",
         bool(tools) and all({"tool_id", "tool_name", "args"} <= set(_json(r, "lmnr.span.input"))
                             and {"stdout", "stderr", "exitCode"} <= set(_json(r, "lmnr.span.output")) for r in tools)),
        (f"{backend}: turn-loop spans carry run config in and run result out",
         bool(loops) and all("config" in _json(r, "lmnr.span.input") and "tool_call_count" in _json(r, "lmnr.span.output") for r in loops)),
    ]


def report(laminar: list[Row], oodle: list[Row], trace_id: str) -> bool:
    laminar = [r for r in laminar if r.trace_id == trace_id]
    oodle = [r for r in oodle if r.trace_id == trace_id]
    lam_ids, ood_ids = {r.span_id for r in laminar}, {r.span_id for r in oodle}
    lam_names, ood_names = Counter(r.name for r in laminar), Counter(r.name for r in oodle)

    print(f"\n{'span':34} {'Laminar':>8} {'Oodle':>6}")
    for name in sorted(set(lam_names) | set(ood_names), key=lambda n: (n.startswith("chat"), n)):
        print(f"{name:34} {lam_names[name]:>8} {ood_names[name]:>6}")

    chats = [r for r in oodle if r.attributes.get("gen_ai.operation.name") is not None]
    dangling = [r for r in oodle if r.parent_id and r.parent_id not in ood_ids]
    chat_parents = Counter(next((l.name for l in laminar if l.span_id == c.parent_id), "?") for c in chats)
    alias = agent.SELECTION.alias
    checks = [
        ("Laminar received the session trace", len(laminar) > 0),
        ("Oodle received LiteLLM chat spans", len(chats) >= 4),
        ("every Laminar span also reached Oodle, same ids", lam_ids <= ood_ids),
        ("every Oodle span's parent is in Oodle", not dangling),
        ("chat spans are children of llm_call / llm_call_stream", set(chat_parents) <= LLM_SPANS),
        ("Oodle service.name is the app, not argv[0]", {r.service for r in oodle} == {SERVICE_NAME}),
        (
            "session id reaches Oodle",
            any(r.attributes.get("lmnr.association.properties.session_id") for r in oodle),
        ),
        (f"Oodle chat spans name the Router group ({alias})",
         bool(chats) and all(_text(c.attributes.get("litellm.model_group", _EMPTY)) == alias for c in chats)),
    ]
    capture = os.environ["OODLE_CAPTURE_MESSAGE_CONTENT"] == "true"
    checks += attribute_checks(laminar, "Laminar", with_content=True)
    checks += attribute_checks([r for r in oodle if r.span_id in lam_ids], "Oodle", with_content=capture)
    if not capture:
        checks.append(("Oodle: chat spans carry no prompt or completion",
                       bool(chats) and not any(CONTENT_KEYS & set(c.attributes) for c in chats)))
    print()
    for label, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if dangling:
        print(f"       {len(dangling)} Oodle span(s) point at parents only Laminar has")
    return all(ok for _, ok in checks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-mirror", action="store_true")
    parser.add_argument("--capture", action="store_true", help="send message content to Oodle too")
    args = parser.parse_args()

    os.environ.update(
        {
            "MOCK_LLM": "true",
            "LMNR_PROJECT_API_KEY": "local",
            "LMNR_BASE_URL": f"http://127.0.0.1:{LAMINAR_PORT}",
            "OODLE_INSTANCE": "local",
            "OODLE_API_KEY": "local",
            "OODLE_TRACES_ENDPOINT": f"http://127.0.0.1:{OODLE_PORT}/v1/traces",
            "OODLE_MIRROR_LAMINAR_SPANS": "false" if args.no_mirror else "true",
            "OODLE_CAPTURE_MESSAGE_CONTENT": "true" if args.capture else "false",
        }
    )
    laminar, oodle, stop = start_receivers()

    # Laminar.initialize keeps only the host of LMNR_BASE_URL and dials its
    # gRPC port separately, so point that port at the local receiver.
    import lmnr

    original = lmnr.Laminar.initialize.__func__

    def initialize(cls, *a, **kw):
        kw.setdefault("grpc_port", LAMINAR_PORT)
        return original(cls, *a, **kw)

    lmnr.Laminar.initialize = classmethod(initialize)

    import tracing

    tracing.init_laminar()
    tracing.init_oodle(SERVICE_NAME)
    global agent, route_audit
    import agent
    import route_audit

    result = asyncio.run(agent.run_session("What is in this repository?"))
    tracing.flush()
    time.sleep(1)
    stop()
    print(f"session {result['session_id']}  trace {result['trace_id']}")
    print(f"answer: {result['answer']}")
    sys.exit(0 if report(laminar.rows, oodle.rows, result["trace_id"]) else 1)


if __name__ == "__main__":
    main()
