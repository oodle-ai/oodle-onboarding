"""Offline end-to-end check of the dual write, with no Laminar or Oodle account.

Starts a local gRPC OTLP receiver in place of Laminar and a local HTTP OTLP
receiver in place of the Oodle collector, runs one mocked agent session
through the real tracing setup, and compares what each side received.

The session has several user messages, one trace each, and a small context
window, so the main agent compacts more than once and the compaction
timeline can be checked across traces. Small trim thresholds make the agent
trim tool output between compactions too.

    python verify_local.py            # expect every check to pass
    python verify_local.py --capture  # same, with message content sent to Oodle
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
from itertools import pairwise

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
    start_time: int = 0
    scope: str = ""


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
                    rows.append(
                        Row(
                            service, s.name, s.trace_id.hex(), s.span_id.hex(), s.parent_span_id.hex(), attrs,
                            s.start_time_unix_nano, ss.scope.name,
                        )
                    )
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


# Small enough that the scripted session compacts more than once, and large
# enough that the file it reads is old by the time the trimmer fires.
CONTEXT_WINDOW_TOKENS = 700
# Small enough that the file the agent reads is trimmed between compactions.
TOOL_TRIM_CHAR_THRESHOLD = 200
TOOL_TRIM_MIN_MESSAGES = 4
FOLLOWUPS = [
    "Which tests exist?",
    "Where does the Flask app start?",
    "Is there a README?",
    "What should I read first?",
    "Summarize the layout again.",
]

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
        # agent_session makes a model call (the title) only for the first message.
        (f"{backend}: turn loops and agent_session end with event=route_completed",
         bool(loops) and all(route(r).get(prefix + "event") == "route_completed" for r in loops)
         and any(route(r) for r in rows if r.name == "agent_session")
         and all(route(r).get(prefix + "event") == "route_completed"
                 for r in rows if r.name == "agent_session" and route(r))),
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


def _value(value):
    kind = value.WhichOneof("value")
    return None if kind is None else getattr(value, kind)


TIMELINE_KEYS = {
    "round", "trigger", "strategy", "context_window_tokens", "threshold", "tokens_before", "tokens_after",
    "messages_before", "messages_after", "summary_id", "agent_key",
}


def compaction_checks(rows: list[Row], backend: str, session_id: str, with_content: bool) -> list[tuple[str, bool]]:
    """The main agent's compaction timeline, rebuilt from spans alone.

    Rounds must count up across traces, each compaction must link to the one
    before it, and every later inference span must say which round it runs in.
    Where content is captured, each compaction's handoff summary must be the
    output of its summary span.
    """
    prefix = compaction.COMPACTION_ATTRIBUTE_PREFIX
    route_child = route_audit.ROUTE_ATTRIBUTE_PREFIX + "child_id"

    def attr(row: Row, key: str):
        value = row.attributes.get(key)
        return None if value is None else _value(value)

    compactions = sorted((r for r in rows if r.name == "summarizing_compact [main]"), key=lambda r: r.start_time)
    rounds = [attr(r, prefix + "round") for r in compactions]
    summaries = [r for r in rows if r.name == "summarizing_get_summary"]
    streams = sorted(
        (r for r in rows if r.name == "llm_call_stream" and not attr(r, route_child)), key=lambda r: r.start_time
    )

    def expected_round(row: Row) -> int:
        return sum(1 for c in compactions if c.start_time < row.start_time)

    return [
        (f"{backend}: main agent compacted at least twice, in more than one trace, rounds 1..N",
         len(compactions) >= 2 and len({r.trace_id for r in compactions}) >= 2
         and rounds == list(range(1, len(compactions) + 1))),
        (f"{backend}: every compaction carries the timeline attributes and shrinks the context",
         bool(compactions) and all(
             {prefix + k for k in TIMELINE_KEYS} <= set(r.attributes)
             and attr(r, prefix + "tokens_after") < attr(r, prefix + "tokens_before")
             and attr(r, prefix + "trigger") in {t.value for t in compaction.CompactionTrigger}
             and attr(r, "gen_ai.conversation.id") == session_id
             for r in compactions)),
        (f"{backend}: each round links to the previous summary and time since it; round 1 has neither",
         bool(compactions)
         and prefix + "previous_summary_id" not in compactions[0].attributes
         and prefix + "seconds_since_previous" not in compactions[0].attributes
         and all(attr(cur, prefix + "previous_summary_id") == attr(prev, prefix + "summary_id")
                 and attr(cur, prefix + "seconds_since_previous") is not None
                 for prev, cur in pairwise(compactions))),
        (f"{backend}: inference spans carry the conversation id, compacted=true and the round they run in",
         bool(streams) and any(expected_round(r) == 0 for r in streams) and any(expected_round(r) for r in streams)
         and all(attr(r, "gen_ai.conversation.id") == session_id
                 and attr(r, "gen_ai.conversation.compacted") is (True if expected_round(r) else None)
                 and attr(r, prefix + "round") == (expected_round(r) or None)
                 for r in streams)),
    ] + ([
        (f"{backend}: each compaction's summary span carries the handoff summary as its output",
         bool(summaries) and len(summaries) >= len(compactions)
         and all("# Handoff Summary" in _text(r.attributes.get("lmnr.span.output", _EMPTY)) for r in summaries)),
    ] if with_content else [])


TRIM_KEYS = {"outcome", "messages_trimmed", "tokens_before", "tokens_after", "threshold_tokens", "trimmed_tool_call_ids"}


def _strings(value) -> list[str] | None:
    """A string-array attribute as a list, or None when it is not an array."""
    if value is None or value.WhichOneof("value") != "array_value":
        return None
    return [v.string_value for v in value.array_value.values]


def tool_trim_checks(rows: list[Row], backend: str, with_content: bool) -> list[tuple[str, bool]]:
    """The main agent's tool-output trims, rebuilt from spans alone.

    A trim must say what it replaced as a list of tool call ids that survives
    export, fire at most once per compaction cycle, and, where tool payloads
    are captured, name only tool calls the agent made before it.
    """
    prefix = tool_trim.TOOL_TRIM_ATTRIBUTE_PREFIX

    def attr(row: Row, key: str):
        value = row.attributes.get(prefix + key)
        return None if value is None else _value(value)

    trims = sorted((r for r in rows if r.name == "tool_trim [main]"), key=lambda r: r.start_time)
    trimmed = [r for r in trims if attr(r, "outcome") == "trimmed"]
    starts = [r.start_time for r in rows if r.name == "summarizing_compact [main]"]
    cycles = Counter(sum(1 for s in starts if s < r.start_time) for r in trims)
    tool_ids = {
        _json(r, "lmnr.span.input").get("tool_id"): r.start_time
        for r in rows if r.name.startswith("tool_call [")
    }

    def ids(row: Row) -> list[str]:
        return _strings(row.attributes.get(prefix + "trimmed_tool_call_ids")) or []

    return [
        (f"{backend}: main agent trimmed tool output, and every trim carries the trim attributes",
         bool(trimmed) and all({prefix + k for k in TRIM_KEYS} <= set(r.attributes) for r in trims)),
        (f"{backend}: trimmed_tool_call_ids arrives as a string array that matches messages_trimmed",
         bool(trims) and all(_strings(r.attributes[prefix + "trimmed_tool_call_ids"]) is not None
                             and len(ids(r)) == attr(r, "messages_trimmed") for r in trims)),
        (f"{backend}: a trim that replaced output shrank the context",
         bool(trimmed) and all(attr(r, "tokens_after") < attr(r, "tokens_before") for r in trimmed)),
        (f"{backend}: at most one trim per compaction cycle, in more than one cycle",
         len(cycles) >= 2 and max(cycles.values()) == 1),
    ] + ([
        (f"{backend}: every trimmed id is the tool_id of a tool call made before the trim",
         bool(trimmed) and all(i in tool_ids and tool_ids[i] < r.start_time for r in trimmed for i in ids(r))),
    ] if with_content else [])


def report(laminar: list[Row], oodle: list[Row], trace_ids: list[str], session_id: str) -> bool:
    laminar = [r for r in laminar if r.trace_id in trace_ids]
    oodle = [r for r in oodle if r.trace_id in trace_ids]
    lam_ids, ood_ids = {r.span_id for r in laminar}, {r.span_id for r in oodle}
    lam_names, ood_names = Counter(r.name for r in laminar), Counter(r.name for r in oodle)

    print(f"\n{'span':44} {'Laminar':>8} {'Oodle':>6}")
    for name in sorted(set(lam_names) | set(ood_names)):
        print(f"{name:44} {lam_names[name]:>8} {ood_names[name]:>6}")

    dangling = [r for r in oodle if r.parent_id and r.parent_id not in ood_ids]
    oodle_llm = [r for r in oodle if r.name in LLM_SPANS]
    checks = [
        ("Laminar received the session trace", len(laminar) > 0),
        # A second instrumentation (LiteLLM's OTel callback) would add a span
        # per model call that repeats the Laminar LLM span's model, tokens
        # and prompt, and double the model calls Oodle counts.
        ("Oodle received exactly the spans Laminar did, same ids", lam_ids == ood_ids),
        ("no LiteLLM spans reach Oodle", not any(r.scope == "litellm" for r in oodle)),
        ("every Oodle span's parent is in Oodle", not dangling),
        ("Oodle service.name is the app, not argv[0]", {r.service for r in oodle} == {SERVICE_NAME}),
        (
            "session id reaches Oodle",
            any(r.attributes.get("lmnr.association.properties.session_id") for r in oodle),
        ),
        # Oodle prices a model call from its model and token counts.
        ("Oodle LLM spans name the model they called",
         bool(oodle_llm) and all(_text(r.attributes.get("gen_ai.request.model", _EMPTY)) for r in oodle_llm)),
    ]
    capture = os.environ["OODLE_CAPTURE_MESSAGE_CONTENT"] == "true"
    checks += attribute_checks(laminar, "Laminar", with_content=True)
    checks += attribute_checks([r for r in oodle if r.span_id in lam_ids], "Oodle", with_content=capture)
    checks += compaction_checks(laminar, "Laminar", session_id, with_content=True)
    checks += compaction_checks([r for r in oodle if r.span_id in lam_ids], "Oodle", session_id, with_content=capture)
    checks += tool_trim_checks(laminar, "Laminar", with_content=True)
    checks += tool_trim_checks([r for r in oodle if r.span_id in lam_ids], "Oodle", with_content=capture)
    print()
    for label, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if dangling:
        print(f"       {len(dangling)} Oodle span(s) point at parents only Laminar has")
    return all(ok for _, ok in checks)


def main() -> None:
    parser = argparse.ArgumentParser()
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
            "OODLE_CAPTURE_MESSAGE_CONTENT": "true" if args.capture else "false",
            "CONTEXT_WINDOW_TOKENS": str(CONTEXT_WINDOW_TOKENS),
            "TOOL_TRIM_CHAR_THRESHOLD": str(TOOL_TRIM_CHAR_THRESHOLD),
            "TOOL_TRIM_MIN_MESSAGES": str(TOOL_TRIM_MIN_MESSAGES),
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
    global agent, compaction, route_audit, tool_trim
    import agent
    import compaction
    import route_audit
    import tool_trim

    result = asyncio.run(agent.run_session("What is in this repository?", FOLLOWUPS))
    tracing.flush()
    time.sleep(1)
    stop()
    print(f"session {result['session_id']}  traces {len(result['trace_ids'])}  compactions {result['compactions']}")
    print(f"answer: {result['answer']}")
    sys.exit(0 if report(laminar.rows, oodle.rows, result["trace_ids"], result["session_id"]) else 1)


if __name__ == "__main__":
    main()
