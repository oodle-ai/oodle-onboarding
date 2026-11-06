"""Invoke a managed Bedrock agent and translate its service trace stream to OTel."""

import codecs
import json
import os
import time
import uuid
from datetime import datetime

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from tools import execute

DEFAULT_PROMPT = "Where is order ORD-1001, and can I return it? Check the order and return policy. Also find AWS documentation on DynamoDB point-in-time recovery and include a source link."


def capture_content():
    return os.environ.get("CAPTURE_CONTENT", "true").lower() == "true"


def messages(role, text):
    return json.dumps([{"role": role, "parts": [{"type": "text", "content": text}]}])


def timestamp_ns(value, fallback):
    return int(value.timestamp() * 1_000_000_000) if isinstance(value, datetime) else fallback


class TraceBridge:
    """One bridge per InvokeAgent call; service trace IDs correlate model inputs/outputs."""

    def __init__(self, tracer, parent):
        self.tracer = tracer
        self.parent = parent
        self.pending = {}
        self.completed = set()

    def consume(self, envelope):
        for phase, event in envelope.get("trace", {}).items():
            if phase == "failureTrace":
                raise RuntimeError(event.get("failureReason", "Managed agent failed"))
            if not isinstance(event, dict):
                continue
            invocation_input = event.get("modelInvocationInput")
            if invocation_input:
                key = (phase, invocation_input["traceId"])
                if key not in self.completed:
                    self.pending[key] = (invocation_input, time.time_ns())
            output = event.get("modelInvocationOutput")
            if output:
                key = (phase, output["traceId"])
                if key in self.completed:
                    continue
                model_input, received_at = self.pending.pop(key, ({}, time.time_ns()))
                self.emit(key, model_input, received_at, output)
                self.completed.add(key)
            # Rationale, observations, and guardrail internals are intentionally not copied.

    def emit(self, key, model_input, received_at, output, error=None):
        metadata = output.get("metadata", {})
        start = timestamp_ns(metadata.get("startTime"), received_at)
        end = max(start, timestamp_ns(metadata.get("endTime"), time.time_ns()))
        attrs = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "aws.bedrock",
            "aws.bedrock.trace.phase": key[0],
            "aws.bedrock.trace.id": key[1],
            "aws.bedrock.trace.timing": "service" if metadata.get("startTime") else "client_observed",
        }
        if model_input.get("foundationModel"):
            attrs["gen_ai.request.model"] = model_input["foundationModel"]
        for source, target in (("inputTokens", "input_tokens"), ("outputTokens", "output_tokens")):
            count = metadata.get("usage", {}).get(source)
            if count is not None:
                attrs[f"gen_ai.usage.{target}"] = count
        if capture_content():
            if model_input.get("text"):
                attrs["aws.bedrock.model.input"] = model_input["text"]
            if output.get("rawResponse", {}).get("content"):
                attrs["aws.bedrock.model.output"] = output["rawResponse"]["content"]
        span = self.tracer.start_span(
            "chat " + model_input.get("foundationModel", "bedrock-managed-model"),
            context=trace.set_span_in_context(self.parent), kind=SpanKind.CLIENT,
            attributes=attrs, start_time=start,
        )
        if error is not None:
            span.set_status(Status(StatusCode.ERROR, str(error)))
            span.set_attribute("error.type", type(error).__name__)
        span.end(end_time=end)

    def close(self, error=None):
        for key, (model_input, received_at) in self.pending.items():
            self.emit(key, model_input, received_at, {}, error or RuntimeError("Model trace ended without output"))
        self.pending.clear()


def fulfill_control(control, tracer, agent_id):
    results = []
    if not control.get("invocationId") or not control.get("invocationInputs"):
        raise ValueError("Return-control response is missing invocation ID or inputs")
    for item in control["invocationInputs"]:
        call = item.get("functionInvocationInput")
        if not call or call.get("actionGroup") != "OrderSupport" or call.get("agentId", agent_id) != agent_id:
            raise ValueError("Only this agent's OrderSupport function actions are supported")
        function = call["function"]
        arguments = {p["name"]: p["value"] for p in call.get("parameters", [])}
        with tracer.start_as_current_span(f"execute_tool {function}", attributes={
            "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": function,
            "gen_ai.tool.call.id": control["invocationId"],
        }) as span:
            if capture_content():
                span.set_attribute("gen_ai.tool.call.arguments", json.dumps(arguments))
            result = {"actionGroup": call["actionGroup"], "function": function}
            try:
                output = execute(function, arguments)
            except (ValueError, RuntimeError) as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.set_attribute("error.type", type(exc).__name__)
                output = {"error": str(exc)}
                result["responseState"] = "REPROMPT"
            if capture_content():
                span.set_attribute("gen_ai.tool.call.result", json.dumps(output))
            result["responseBody"] = {"TEXT": {"body": json.dumps(output)}}
            results.append({"functionResult": result})
    return {"invocationId": control["invocationId"], "returnControlInvocationResults": results}


def run_agent(client, agent_id, alias_id, prompt=DEFAULT_PROMPT, session_id=None, max_rounds=8):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    session_id = session_id or str(uuid.uuid4())
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("invoke_agent managed-order-support", kind=SpanKind.CLIENT, attributes={
        "gen_ai.operation.name": "invoke_agent", "gen_ai.provider.name": "aws.bedrock",
        "gen_ai.agent.name": "managed-order-support", "gen_ai.agent.id": agent_id,
        "aws.bedrock.agent.alias_id": alias_id,
        "session.id": session_id, "gen_ai.conversation.id": session_id,
    }) as root:
        trace_id = format(root.get_span_context().trace_id, "032x")
        if capture_content():
            root.set_attribute("gen_ai.input.messages", messages("user", prompt))
        state = None
        answer = []
        try:
            for _ in range(max_rounds):
                request = {"agentId": agent_id, "agentAliasId": alias_id,
                           "sessionId": session_id, "enableTrace": True}
                if state is None:
                    request["inputText"] = prompt
                else:
                    request["sessionState"] = state
                bridge = TraceBridge(tracer, root)
                stream = None
                failure = None
                control = None
                decoder = codecs.getincrementaldecoder("utf-8")()
                try:
                    stream = client.invoke_agent(**request)["completion"]
                    for event in stream:
                        if "trace" in event:
                            bridge.consume(event["trace"])
                        elif "chunk" in event:
                            answer.append(decoder.decode(event["chunk"]["bytes"]))
                        elif "returnControl" in event:
                            if control is not None:
                                raise RuntimeError("Multiple return-control responses in one invocation")
                            control = event["returnControl"]
                        else:
                            errors = [k for k in event if k.endswith("Exception")]
                            if errors:
                                raise RuntimeError(f"{errors[0]}: {event[errors[0]].get('message', '')}")
                    answer.append(decoder.decode(b"", final=True))
                except Exception as exc:
                    failure = exc
                    raise
                finally:
                    bridge.close(failure)
                    if stream is not None and hasattr(stream, "close"):
                        stream.close()
                if control is not None:
                    state = fulfill_control(control, tracer, agent_id)
                    continue
                text = "".join(answer)
                if not text.strip():
                    raise RuntimeError("Managed agent returned neither an answer nor a tool request")
                if capture_content():
                    root.set_attribute("gen_ai.output.messages", messages("assistant", text))
                return {"answer": text, "session_id": session_id, "trace_id": trace_id}
            raise RuntimeError(f"Managed agent exceeded {max_rounds} return-control rounds")
        except Exception as exc:
            root.set_attribute("error.type", type(exc).__name__)
            exc.add_note(f"Oodle trace ID: {trace_id}")
            raise
