#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "opentelemetry-sdk>=1.25.0",
#     "opentelemetry-exporter-otlp-proto-http>=1.25.0",
# ]
# ///
"""Replay a LiveKit voice-agent trace from a Jaeger-format
JSON export, sending it via OTLP to an OTel Collector.

Usage:
    ./replay.py sample-trace.json              # default endpoint
    ./replay.py sample-trace.json --endpoint http://localhost:4319
"""
import argparse
import json
import sys
import time
import uuid

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.trace import (
    SpanContext,
    SpanKind,
    TraceFlags,
    NonRecordingSpan,
    StatusCode,
)
from opentelemetry.context import Context


def parse_args():
    p = argparse.ArgumentParser(
        description="Replay a LiveKit trace via OTLP",
    )
    p.add_argument(
        "trace_file",
        help="Path to Jaeger-format trace JSON",
    )
    p.add_argument(
        "--endpoint",
        default="http://localhost:4319",
        help="OTel Collector OTLP/HTTP endpoint",
    )
    p.add_argument(
        "--fresh-ids",
        action="store_true",
        help="Generate new trace/span IDs "
        "instead of preserving originals",
    )
    return p.parse_args()


def load_trace(path):
    with open(path) as f:
        data = json.load(f)

    if isinstance(data, list):
        if len(data) == 1:
            data = data[0]
        else:
            data = {
                "traceID": data[0].get("traceID", ""),
                "spans": [
                    s for d in data for s in d["spans"]
                ],
                "processes": data[0].get("processes", {}),
            }

    return data


def jaeger_tag_value(tag):
    if "value" in tag:
        return tag["value"]
    for k in ("vStr", "vInt64", "vFloat64", "vBool"):
        if k in tag:
            return tag[k]
    return ""


def replay_trace(data, endpoint, fresh_ids):
    process = data.get("processes", {}).get("p1", {})
    svc_name = process.get("serviceName", "livekit-demo")

    resource = Resource.create(
        {"service.name": svc_name},
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=f"{endpoint}/v1/traces",
    )
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    tracer = provider.get_tracer(
        "livekit-agents",
        "1.0.0",
    )

    spans = data["spans"]
    orig_trace_id = data.get("traceID", "")
    if ":" in orig_trace_id:
        orig_trace_id = orig_trace_id.split(":")[0]

    if fresh_ids:
        new_trace_id = int.from_bytes(
            uuid.uuid4().bytes, "big",
        )
        span_id_map = {}
    else:
        new_trace_id = int(orig_trace_id, 16)
        span_id_map = {}

    now_ns = time.time_ns()
    first_start = min(
        s.get("startTime", 0) for s in spans
    )
    if first_start > 1e15:
        time_unit_ns = 1
    elif first_start > 1e12:
        time_unit_ns = 1000
    else:
        time_unit_ns = 1_000_000

    parent_map = {}
    for s in spans:
        sid = s["spanID"]
        psid = s.get("parentSpanID", "")
        if not psid:
            refs = s.get("references") or []
            for r in refs:
                if r.get("refType") == "CHILD_OF":
                    psid = r.get("spanID", "")
                    break
        parent_map[sid] = psid

    def get_new_span_id(orig_id):
        if not orig_id:
            return 0
        if orig_id not in span_id_map:
            if fresh_ids:
                span_id_map[orig_id] = int.from_bytes(
                    uuid.uuid4().bytes[:8], "big",
                )
            else:
                span_id_map[orig_id] = int(
                    orig_id, 16,
                )
        return span_id_map[orig_id]

    sorted_spans = sorted(
        spans,
        key=lambda s: s.get("startTime", 0),
    )

    display_id = (
        f"{new_trace_id:032x}"[:16]
        if fresh_ids
        else orig_trace_id[:16]
    )
    print(
        f"Replaying {len(sorted_spans)} spans "
        f"from trace {display_id}..."
    )
    print(f"Service: {svc_name}")
    print(f"Endpoint: {endpoint}")

    for s in sorted_spans:
        orig_sid = s["spanID"]
        orig_psid = parent_map.get(orig_sid, "")

        new_sid = get_new_span_id(orig_sid)
        new_psid = get_new_span_id(orig_psid)

        start_us = s.get("startTime", 0) * time_unit_ns
        end_us = (
            start_us + s.get("duration", 0) * time_unit_ns
        )
        offset = now_ns - (first_start * time_unit_ns)
        start_ns = start_us + offset
        end_ns = end_us + offset

        parent_ctx = SpanContext(
            trace_id=new_trace_id,
            span_id=new_psid if new_psid else new_sid,
            is_remote=True,
            trace_flags=TraceFlags(
                TraceFlags.SAMPLED,
            ),
        )
        ctx = trace.set_span_in_context(
            NonRecordingSpan(parent_ctx),
        )

        span_name = s.get("operationName", "unknown")

        attrs = {}
        for tag in s.get("tags", []):
            val = jaeger_tag_value(tag)
            if isinstance(val, bool):
                attrs[tag["key"]] = val
            elif isinstance(val, (int, float)):
                attrs[tag["key"]] = val
            else:
                attrs[tag["key"]] = str(val)

        span = tracer.start_span(
            name=span_name,
            context=ctx,
            kind=SpanKind.INTERNAL,
            attributes=attrs,
            start_time=start_ns,
        )
        span._context = SpanContext(
            trace_id=new_trace_id,
            span_id=new_sid,
            is_remote=False,
            trace_flags=TraceFlags(
                TraceFlags.SAMPLED,
            ),
        )

        for log_entry in s.get("logs", []):
            event_name = ""
            event_attrs = {}
            for field in log_entry.get("fields", []):
                val = jaeger_tag_value(field)
                if field["key"] == "event":
                    event_name = str(val)
                else:
                    event_attrs[field["key"]] = str(val)

            log_ts = log_entry.get(
                "timestamp", 0
            ) * time_unit_ns
            log_ns = log_ts + offset

            if event_name:
                span.add_event(
                    event_name,
                    attributes=event_attrs,
                    timestamp=log_ns,
                )

        status_tag = attrs.get(
            "otel.status_code", "",
        )
        if status_tag == "ERROR":
            span.set_status(
                StatusCode.ERROR,
                attrs.get("otel.status_description", ""),
            )
        elif status_tag == "OK":
            span.set_status(StatusCode.OK)

        span.end(end_time=end_ns)

    provider.force_flush()
    provider.shutdown()
    print(f"Done — {len(sorted_spans)} spans exported.")


def main():
    args = parse_args()
    data = load_trace(args.trace_file)
    replay_trace(data, args.endpoint, args.fresh_ids)


if __name__ == "__main__":
    main()
