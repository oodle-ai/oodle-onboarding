"""Offline check of both PII modes, with no Oodle, LiveKit or OpenAI account.

Stands up a local OTLP/HTTP receiver in place of Oodle, records one call's
span tree through LiveKit's own tracer and attribute names in each mode,
and checks what the receiver got:

- in both modes, the span tree, the service name, the per-call metadata
  on every span, and Oodle's headers;
- with personal data allowed, the caller's name, number and address in
  the transcript, the tool arguments and the GenAI messages;
- with it withheld, none of that text anywhere, while the timings, model,
  token counts, tool name and agent label survive.

What is being checked is the export wiring and LiveKit's PII filter, not
the voice pipeline.

    python verify_local.py

Each mode runs in its own subprocess, as each call runs in its own job
process in the agent.
"""

import gzip
import json
import multiprocessing
import os
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from opentelemetry.proto.common.v1.common_pb2 import AnyValue

OODLE_PORT = 14320
SERVICE_NAME = "livekit-voice-worker"
OODLE_INSTANCE = "verify-instance"
OODLE_API_KEY = "oodle-verify-key"

CALL = {"call_id": "verifycall0001", "contact_id": "contact-0001"}

# What the caller says about themselves. None of it may reach Oodle when
# personal data is withheld.
NAME = "Jane Doe"
PHONE = "555-0142"
ADDRESS = "12 Elm Street"
PERSONAL = (NAME, PHONE, ADDRESS)

# span name -> parent span name
CALL_TREE = {
    "agent_session": None,
    "user_turn": "agent_session",
    "agent_turn": "agent_session",
    "llm_request": "agent_turn",
    "function_tool": "agent_turn",
    "tts_request": "agent_turn",
}


def _value(any_value: AnyValue):
    kind = any_value.WhichOneof("value")
    if kind is None:
        return None
    if kind == "array_value":
        return [_value(v) for v in any_value.array_value.values]
    if kind == "kvlist_value":
        return {kv.key: _value(kv.value) for kv in any_value.kvlist_value.values}
    return getattr(any_value, kind)


def _attributes(pairs) -> dict:
    return {kv.key: _value(kv.value) for kv in pairs}


@dataclass
class Span:
    name: str
    scope: str
    span_id: str
    parent_id: str
    trace_id: str
    service: str
    attributes: dict
    events: list[tuple[str, dict]]


@dataclass
class Sink:
    """A local stand-in for Oodle's OTLP collector."""

    spans: list[Span] = field(default_factory=list)
    paths: set = field(default_factory=set)
    auth: set = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reset(self) -> None:
        with self.lock:
            self.spans.clear()
            self.paths.clear()
            self.auth.clear()

    def record(self, path: str, headers, body: bytes) -> None:
        if headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)

        request = trace_service_pb2.ExportTraceServiceRequest()
        request.ParseFromString(body)

        spans = []
        for resource_spans in request.resource_spans:
            service = _attributes(resource_spans.resource.attributes).get("service.name", "")
            for scope_spans in resource_spans.scope_spans:
                for span in scope_spans.spans:
                    spans.append(
                        Span(
                            name=span.name,
                            scope=scope_spans.scope.name,
                            span_id=span.span_id.hex(),
                            parent_id=span.parent_span_id.hex(),
                            trace_id=span.trace_id.hex(),
                            service=service,
                            attributes=_attributes(span.attributes),
                            events=[(e.name, _attributes(e.attributes)) for e in span.events],
                        )
                    )

        with self.lock:
            self.spans.extend(spans)
            self.paths.add(path)
            self.auth.add(f"{headers.get('X-API-KEY')}|{headers.get('X-OODLE-INSTANCE')}")

    def by_name(self) -> dict[str, Span]:
        with self.lock:
            return {span.name: span for span in self.spans}


def _serve(sink: Sink) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                sink.record(self.path, self.headers, body)
            except Exception as error:  # a malformed body is a failed check
                print(f"  ! could not parse a request: {error}")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", OODLE_PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# --- The traced call, run in a subprocess ---------------------------------


def _emit_call() -> None:
    """Record the spans of one booking turn, as LiveKit Agents names them."""
    from livekit.agents.telemetry import trace_types as tt
    from livekit.agents.telemetry import tracer

    user_words = f"I'm {NAME}, my number is {PHONE}, the house is at {ADDRESS}."
    reply = f"Thanks {NAME}, you're booked for Tuesday at 1 PM."
    arguments = json.dumps(
        {"full_name": NAME, "phone_number": PHONE, "address": ADDRESS, "day": "Tuesday", "slot": "1:00 PM"}
    )

    with tracer.start_as_current_span(
        "agent_session",
        attributes={
            tt.ATTR_AGENT_NAME: "livekit-demo-agent",
            tt.ATTR_ROOM_NAME: "web-call-verifycall0001",
            tt.ATTR_GEN_AI_OPERATION_NAME: "agent_session",
            tt.ATTR_GEN_AI_AGENT_NAME: "livekit-demo-agent",
        },
    ):
        with tracer.start_as_current_span(
            "user_turn",
            attributes={
                tt.ATTR_USER_TRANSCRIPT: user_words,
                tt.ATTR_PARTICIPANT_IDENTITY: CALL["contact_id"],
                tt.ATTR_PARTICIPANT_KIND: "PARTICIPANT_KIND_STANDARD",
            },
        ):
            pass

        with tracer.start_as_current_span(
            "agent_turn",
            attributes={tt.ATTR_AGENT_LABEL: "voice_agent", tt.ATTR_RESPONSE_TEXT: reply},
        ):
            with tracer.start_as_current_span(
                "llm_request",
                attributes={
                    tt.ATTR_GEN_AI_OPERATION_NAME: "chat",
                    tt.ATTR_GEN_AI_REQUEST_MODEL: "gpt-4.1-mini",
                    tt.ATTR_GEN_AI_USAGE_INPUT_TOKENS: 812,
                    tt.ATTR_GEN_AI_USAGE_OUTPUT_TOKENS: 41,
                    tt.ATTR_GEN_AI_SYSTEM_INSTRUCTIONS: "You are Max, an assistant for Maple Street Realty.",
                    tt.ATTR_GEN_AI_INPUT_MESSAGES: json.dumps(
                        [{"role": "user", "parts": [{"type": "text", "content": user_words}]}]
                    ),
                    tt.ATTR_GEN_AI_OUTPUT_MESSAGES: json.dumps(
                        [{"role": "assistant", "parts": [{"type": "tool_call", "arguments": arguments}]}]
                    ),
                },
            ) as span:
                span.add_event(tt.EVENT_GEN_AI_USER_MESSAGE, {"content": user_words})
                span.add_event(tt.EVENT_GEN_AI_CHOICE, {"role": "assistant", "tool_calls": arguments})

            with tracer.start_as_current_span(
                "function_tool",
                attributes={
                    tt.ATTR_FUNCTION_TOOL_NAME: "book_valuation",
                    tt.ATTR_FUNCTION_TOOL_ARGS: arguments,
                    tt.ATTR_FUNCTION_TOOL_OUTPUT: f"Booked {NAME} at {ADDRESS}. A text goes to {PHONE}.",
                    tt.ATTR_FUNCTION_TOOL_IS_ERROR: False,
                },
            ):
                pass

            with tracer.start_as_current_span(
                "tts_request",
                attributes={tt.ATTR_TTS_INPUT_TEXT: reply, tt.ATTR_TTS_LABEL: "livekit.plugins.openai.tts.TTS"},
            ):
                pass


def _run_mode(mode: str) -> None:
    """Child process: set up tracing as the agent does for one call."""
    os.environ.update(
        {
            "OODLE_INSTANCE": OODLE_INSTANCE,
            "OODLE_API_KEY": OODLE_API_KEY,
            "OODLE_TRACES_ENDPOINT": f"http://127.0.0.1:{OODLE_PORT}/v1/traces",
        }
    )

    import agent
    import tracing

    provider = tracing.init(
        SERVICE_NAME,
        metadata=agent.call_metadata(CALL, "AJ_verify", mode),
        allow_pii=mode == tracing.PII_ALLOW,
    )
    _emit_call()
    provider.shutdown()


def _run_in_subprocess(mode: str) -> None:
    context = multiprocessing.get_context("spawn")
    process = context.Process(target=_run_mode, args=(mode,))
    process.start()
    process.join(60)
    if process.exitcode != 0:
        raise SystemExit(f"{mode} mode exited with code {process.exitcode}")


# --- Checks ---------------------------------------------------------------


class Checks:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def that(self, condition: bool, description: str, detail: str = "") -> None:
        if condition:
            print(f"  ok   {description}")
            return
        self.failures.append(description)
        print(f"  FAIL {description}" + (f" — {detail}" if detail else ""))


def _text_of(span: Span) -> str:
    """Every attribute and event value on a span, as one string to search."""
    return json.dumps([span.attributes, span.events], default=str)


def _check_common(checks: Checks, sink: Sink, mode: str) -> None:
    spans = sink.by_name()
    checks.that(set(spans) == set(CALL_TREE), f"Oodle received {sorted(CALL_TREE)}", f"got {sorted(spans)}")
    if set(spans) != set(CALL_TREE):
        return

    checks.that(len({s.trace_id for s in spans.values()}) == 1, "the spans form one trace")
    for name, parent in CALL_TREE.items():
        if parent:
            checks.that(
                spans[name].parent_id == spans[parent].span_id,
                f"{name} is a child of {parent}",
                f"parent_id {spans[name].parent_id!r}",
            )

    checks.that(
        all(s.scope == "livekit-agents" for s in spans.values()),
        "every span is in the livekit-agents scope",
        f"got {sorted({s.scope for s in spans.values()})}",
    )
    checks.that(
        all(s.service == SERVICE_NAME for s in spans.values()),
        f"every span carries service.name={SERVICE_NAME}",
    )

    missing = [
        name
        for name, span in spans.items()
        if span.attributes.get("session.id") != CALL["call_id"]
        or span.attributes.get("user.id") != CALL["contact_id"]
        or span.attributes.get("langfuse.session.id") != CALL["call_id"]
        or f"PII_MODE={mode}" not in (span.attributes.get("langfuse.tags") or [])
    ]
    checks.that(not missing, "every span carries the call's session, user and langfuse metadata", f"missing on {missing}")

    llm = spans["llm_request"].attributes
    checks.that(
        llm.get("gen_ai.request.model") == "gpt-4.1-mini"
        and llm.get("gen_ai.usage.input_tokens") == 812
        and llm.get("gen_ai.usage.output_tokens") == 41,
        "the LLM span keeps its model and token counts",
        f"got {llm}",
    )
    checks.that(
        spans["function_tool"].attributes.get("lk.function_tool.name") == "book_valuation",
        "the tool span keeps the tool's name",
    )
    checks.that(
        spans["agent_turn"].attributes.get("lk.agent_label") == "voice_agent",
        "the agent turn keeps its agent label",
    )
    checks.that(
        sink.auth == {f"{OODLE_API_KEY}|{OODLE_INSTANCE}"} and sink.paths == {"/v1/traces"},
        "Oodle was addressed at /v1/traces with X-API-KEY and X-OODLE-INSTANCE",
        f"got {sink.auth} at {sink.paths}",
    )


def _check_allowed(checks: Checks, sink: Sink) -> None:
    spans = sink.by_name()
    if set(spans) != set(CALL_TREE):
        return

    checks.that(NAME in spans["user_turn"].attributes.get("lk.pii.user_transcript", ""), "the transcript is in lk.pii.user_transcript")
    checks.that(PHONE in spans["function_tool"].attributes.get("lk.pii.function_tool.arguments", ""), "the tool arguments are in lk.pii.function_tool.arguments")
    checks.that(ADDRESS in spans["llm_request"].attributes.get("gen_ai.input.messages", ""), "the LLM input is in gen_ai.input.messages")
    checks.that(
        {"gen_ai.user.message", "gen_ai.choice"} <= {name for name, _ in spans["llm_request"].events},
        "the GenAI message events are on the LLM span",
    )


def _check_withheld(checks: Checks, sink: Sink) -> None:
    spans = sink.by_name()
    if set(spans) != set(CALL_TREE):
        return

    leaks = [f"{name}: {value!r}" for name, span in spans.items() for value in PERSONAL if value in _text_of(span)]
    checks.that(not leaks, "no name, phone number or address reached Oodle", "; ".join(leaks))

    pii_keys = sorted({key for span in spans.values() for key in span.attributes if "pii" in key.split(".")})
    checks.that(not pii_keys, "no lk.pii.* attribute reached Oodle", f"got {pii_keys}")

    message_keys = sorted(
        {
            key
            for span in spans.values()
            for key in span.attributes
            if key in ("gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.system_instructions")
        }
    )
    checks.that(not message_keys, "no gen_ai.*.messages or system instructions reached Oodle", f"got {message_keys}")
    checks.that(not spans["llm_request"].events, "the GenAI message events were dropped", f"got {spans['llm_request'].events}")
    checks.that(
        spans["user_turn"].attributes.get("lk.participant_kind") == "PARTICIPANT_KIND_STANDARD",
        "what is not personal, such as the participant kind, is kept",
    )


def main() -> int:
    sink = Sink()
    server = _serve(sink)
    checks = Checks()

    try:
        print("\npii_mode=allow — the conversation reaches Oodle")
        sink.reset()
        _run_in_subprocess("allow")
        _check_common(checks, sink, "allow")
        _check_allowed(checks, sink)

        print("\npii_mode=withhold — LiveKit strips personal data before export")
        sink.reset()
        _run_in_subprocess("withhold")
        _check_common(checks, sink, "withhold")
        _check_withheld(checks, sink)
    finally:
        server.shutdown()

    print()
    if checks.failures:
        print(f"{len(checks.failures)} check(s) failed:")
        for failure in checks.failures:
            print(f"  - {failure}")
        return 1

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
