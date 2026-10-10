"""Offline check of both tracing paths, with no Langfuse or Oodle account.

Stands up two local OTLP/HTTP receivers — one in place of Langfuse, one in
place of the Oodle collector — then runs each tracing path against them
and compares what the two sides received.

The spans are a Pipecat voice turn: a ``conversation`` span with a
``turn`` beneath it and ``stt``, ``llm`` and ``tts`` beneath that, written
through Pipecat's own tracer names and its own span-attribute helpers, so
the scopes and attribute keys are the ones a real session produces. What
is being checked is the export wiring, not Pipecat.

    python verify_local.py

Each path runs in its own subprocess, because registering the
process-wide tracer provider is a one-time act.
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

LANGFUSE_PORT = 14318
OODLE_PORT = 14319
SERVICE_NAME = "pipecat-demo"
AGENT_NAME = "pipecat-voice-agent"

# What a traced Pipecat turn looks like: span name -> parent span name.
PIPECAT_TREE = {
    "conversation": None,
    "turn": "conversation",
    "stt": "turn",
    "llm": "turn",
    "tts": "turn",
}

# Credentials the subprocesses are given. Neither destination is real, so
# these only have to be distinguishable from each other.
LANGFUSE_PUBLIC_KEY = "pk-lf-verify"
LANGFUSE_SECRET_KEY = "sk-lf-verify"
OODLE_INSTANCE = "verify-instance"
OODLE_API_KEY = "oodle-verify-key"

_EMPTY = AnyValue()


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


@dataclass
class Sink:
    """One local stand-in for a tracing backend."""

    label: str
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
                        )
                    )

        with self.lock:
            self.spans.extend(spans)
            self.paths.add(path)
            auth = headers.get("Authorization") or headers.get("X-API-KEY") or ""
            instance = headers.get("X-OODLE-INSTANCE")
            self.auth.add(f"{auth}|{instance}" if instance else auth)

    def by_name(self) -> dict[str, Span]:
        with self.lock:
            return {span.name: span for span in self.spans}


def _serve(sink: Sink, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length)
            try:
                sink.record(self.path, self.headers, body)
            except Exception as error:  # a malformed body is a failed check
                print(f"  ! {sink.label} could not parse a request: {error}")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# --- The traced work, run in a subprocess ---------------------------------


def _emit_pipecat_trace() -> None:
    """Record the span tree a Pipecat voice turn produces.

    Uses Pipecat's own tracer names and attribute helpers so the
    instrumentation scopes and attribute keys match a real session; that
    is what the Langfuse export filter decides on.
    """
    from opentelemetry import trace
    from opentelemetry.trace import set_span_in_context
    from pipecat.utils.tracing.service_attributes import (
        add_llm_span_attributes,
        add_stt_span_attributes,
        add_tts_span_attributes,
    )

    turn_tracer = trace.get_tracer("pipecat.turn")
    service_tracer = trace.get_tracer("pipecat")

    conversation = turn_tracer.start_span("conversation")
    conversation.set_attribute("conversation.id", "verify-conversation")
    conversation.set_attribute("conversation.type", "voice")
    # What bot.py passes as additional_span_attributes.
    conversation.set_attribute("gen_ai.operation.name", "invoke_agent")
    conversation.set_attribute("gen_ai.agent.name", AGENT_NAME)

    turn = turn_tracer.start_span("turn", context=set_span_in_context(conversation))
    turn.set_attribute("turn.number", 1)
    turn.set_attribute("turn.type", "conversation")
    turn.set_attribute("turn.duration_seconds", 2.5)
    turn.set_attribute("turn.was_interrupted", False)
    turn.set_attribute("conversation.id", "verify-conversation")
    turn_context = set_span_in_context(turn)

    stt = service_tracer.start_span("stt", context=turn_context)
    add_stt_span_attributes(
        span=stt,
        service_name="OpenAISTTService",
        model="gpt-4o-mini-transcribe",
        transcript="What is OpenTelemetry?",
        is_final=True,
        language="en",
        vad_enabled=True,
        ttfb=0.21,
    )
    stt.end()

    llm = service_tracer.start_span("llm", context=turn_context)
    add_llm_span_attributes(
        span=llm,
        service_name="OpenAILLMService",
        model="gpt-4o-mini",
        messages=json.dumps([{"role": "user", "content": "What is OpenTelemetry?"}]),
        output="It is an open standard for traces, metrics and logs.",
        ttfb=0.33,
    )
    llm.set_attribute("gen_ai.usage.input_tokens", 24)
    llm.set_attribute("gen_ai.usage.output_tokens", 12)
    llm.end()

    tts = service_tracer.start_span("tts", context=turn_context)
    add_tts_span_attributes(
        span=tts,
        service_name="OpenAITTSService",
        model="gpt-4o-mini-tts",
        voice_id="alloy",
        text="It is an open standard for traces, metrics and logs.",
        character_count=51,
        ttfb=0.18,
    )
    tts.end()

    turn.end()
    conversation.end()


def _run_path(backend: str, export_pipecat_spans: bool) -> None:
    """Child process: set up one tracing path and record one trace."""
    os.environ.update(
        {
            "TRACING_BACKEND": backend,
            "LANGFUSE_BASE_URL": f"http://127.0.0.1:{LANGFUSE_PORT}",
            "LANGFUSE_PUBLIC_KEY": LANGFUSE_PUBLIC_KEY,
            "LANGFUSE_SECRET_KEY": LANGFUSE_SECRET_KEY,
            "LANGFUSE_EXPORT_PIPECAT_SPANS": "true" if export_pipecat_spans else "false",
            "OODLE_INSTANCE": OODLE_INSTANCE,
            "OODLE_API_KEY": OODLE_API_KEY,
            "OODLE_TRACES_ENDPOINT": f"http://127.0.0.1:{OODLE_PORT}/v1/traces",
            "OODLE_LANGFUSE_BASE_URL": f"http://127.0.0.1:{OODLE_PORT}",
            # The Langfuse SDK's own retries would hide a failed export
            # behind a long wait; one attempt is enough against localhost.
            "LANGFUSE_FLUSH_INTERVAL": "1",
        }
    )

    import tracing

    tracing.init(SERVICE_NAME)
    _emit_pipecat_trace()
    tracing.shutdown()


def _run_in_subprocess(backend: str, export_pipecat_spans: bool = True) -> None:
    context = multiprocessing.get_context("spawn")
    process = context.Process(target=_run_path, args=(backend, export_pipecat_spans))
    process.start()
    process.join(120)
    if process.exitcode != 0:
        raise SystemExit(f"{backend} path exited with code {process.exitcode}")


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


def _check_tree(checks: Checks, sink: Sink, expected: set[str]) -> None:
    spans = sink.by_name()
    checks.that(
        set(spans) == expected,
        f"{sink.label} received {sorted(expected)}",
        f"got {sorted(spans)}",
    )
    if set(spans) != expected:
        return

    trace_ids = {span.trace_id for span in spans.values()}
    checks.that(
        len(trace_ids) == 1, f"{sink.label} holds one trace", f"trace ids {trace_ids}"
    )

    for name, parent in PIPECAT_TREE.items():
        if name not in spans or parent not in spans:
            continue
        checks.that(
            spans[name].parent_id == spans[parent].span_id,
            f"{sink.label}: {name} is a child of {parent}",
            f"parent_id {spans[name].parent_id!r}",
        )

    checks.that(
        all(span.service == SERVICE_NAME for span in spans.values()),
        f"{sink.label}: every span carries service.name={SERVICE_NAME}",
        f"got {sorted({span.service for span in spans.values()})}",
    )


def _check_identical(checks: Checks, left: Sink, right: Sink) -> None:
    def shape(sink: Sink) -> dict:
        return {
            name: (span.scope, span.span_id, span.parent_id, span.trace_id)
            for name, span in sink.by_name().items()
        }

    checks.that(
        shape(left) == shape(right),
        f"{left.label} and {right.label} hold the same span ids and scopes",
    )


def _check_transcript(checks: Checks, sink: Sink) -> None:
    """What was said has to reach the backend, under the names Pipecat uses.

    Pipecat does not follow the GenAI semantic conventions here: the
    conversation is in `input` and `output` on the LLM span, `transcript`
    on STT and `text` on TTS, not in `gen_ai.input.messages` /
    `gen_ai.output.messages`. A backend that renders a transcript from the
    conventions alone will show none of it — see the README.
    """
    spans = sink.by_name()

    def attribute(name: str, key: str):
        return spans[name].attributes.get(key) if name in spans else None

    checks.that(
        attribute("stt", "transcript") == "What is OpenTelemetry?",
        f"{sink.label}: the STT span carries the user's words as `transcript`",
        f"got {attribute('stt', 'transcript')!r}",
    )
    checks.that(
        json.loads(attribute("llm", "input") or "[]")
        == [{"role": "user", "content": "What is OpenTelemetry?"}],
        f"{sink.label}: the LLM span carries the messages as `input`",
        f"got {attribute('llm', 'input')!r}",
    )
    checks.that(
        attribute("llm", "output") == "It is an open standard for traces, metrics and logs.",
        f"{sink.label}: the LLM span carries the answer as `output`",
        f"got {attribute('llm', 'output')!r}",
    )
    checks.that(
        attribute("tts", "text") == "It is an open standard for traces, metrics and logs.",
        f"{sink.label}: the TTS span carries the spoken text as `text`",
        f"got {attribute('tts', 'text')!r}",
    )
    checks.that(
        attribute("llm", "gen_ai.input.messages") is None,
        f"{sink.label}: nothing rewrites them into the GenAI conventions",
    )


def _check_credentials(checks: Checks, langfuse: Sink, oodle: Sink, path: str) -> None:
    import base64

    expected_langfuse = "Basic " + base64.b64encode(
        f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()
    ).decode()

    checks.that(
        langfuse.auth == {expected_langfuse},
        "Langfuse received its own project credentials",
        f"got {langfuse.auth}",
    )

    if path == "otel":
        expected_oodle = {f"{OODLE_API_KEY}|{OODLE_INSTANCE}"}
        description = "Oodle received X-API-KEY and X-OODLE-INSTANCE"
        expected_path = {"/v1/traces"}
    else:
        expected_oodle = {
            "Basic " + base64.b64encode(f"default:{OODLE_API_KEY}".encode()).decode()
        }
        description = "Oodle received Langfuse ingest credentials (default / API key)"
        expected_path = {"/api/public/otel/v1/traces"}

    checks.that(oodle.auth == expected_oodle, description, f"got {oodle.auth}")
    checks.that(
        oodle.paths == expected_path,
        f"Oodle was addressed at {sorted(expected_path)}",
        f"got {sorted(oodle.paths)}",
    )
    checks.that(
        langfuse.paths == {"/api/public/otel/v1/traces"},
        "Langfuse was addressed at /api/public/otel/v1/traces",
        f"got {sorted(langfuse.paths)}",
    )


def main() -> int:
    langfuse = Sink("Langfuse")
    oodle = Sink("Oodle")
    servers = [_serve(langfuse, LANGFUSE_PORT), _serve(oodle, OODLE_PORT)]
    checks = Checks()

    try:
        all_spans = set(PIPECAT_TREE)

        print("\nTRACING_BACKEND=otel — two OpenTelemetry OTLP exporters")
        langfuse.reset()
        oodle.reset()
        _run_in_subprocess("otel")
        _check_tree(checks, oodle, all_spans)
        _check_tree(checks, langfuse, all_spans)
        _check_identical(checks, langfuse, oodle)
        _check_credentials(checks, langfuse, oodle, "otel")
        _check_transcript(checks, oodle)
        _check_transcript(checks, langfuse)

        print("\nTRACING_BACKEND=langfuse-sdk — the Langfuse SDK, two destinations")
        langfuse.reset()
        oodle.reset()
        _run_in_subprocess("langfuse-sdk")
        _check_tree(checks, oodle, all_spans)
        _check_tree(checks, langfuse, all_spans)
        _check_identical(checks, langfuse, oodle)
        _check_credentials(checks, langfuse, oodle, "langfuse-sdk")

        print(
            "\nTRACING_BACKEND=langfuse-sdk with LANGFUSE_EXPORT_PIPECAT_SPANS=false\n"
            "  — the SDK's default filter, which is why bot.py widens it"
        )
        langfuse.reset()
        oodle.reset()
        _run_in_subprocess("langfuse-sdk", export_pipecat_spans=False)
        # The conversation span passes the default filter only because
        # bot.py puts gen_ai.* attributes on it. The turn span has none, so
        # it is dropped and its children arrive orphaned.
        checks.that(
            "turn" not in langfuse.by_name(),
            "the default filter drops the turn span",
            f"got {sorted(langfuse.by_name())}",
        )
        checks.that(
            {"stt", "llm", "tts"} <= set(langfuse.by_name()),
            "its stt/llm/tts children are still exported, now parented to nothing",
            f"got {sorted(langfuse.by_name())}",
        )
    finally:
        for server in servers:
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
