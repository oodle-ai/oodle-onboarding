"""OpenAI SDK observability demo.

Auto-instruments the OpenAI SDK with the official OpenTelemetry
GenAI instrumentation and exports traces and logs to Oodle via an
OTel Collector.
"""

import json
import os

from fastapi import FastAPI
from opentelemetry import _logs as otel_logs
from opentelemetry import trace as otel_trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel


def setup_opentelemetry():
    resource = Resource.create({"service.name": "openai-demo"})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter())
    )
    otel_trace.set_tracer_provider(tracer_provider)

    # This instrumentation writes prompts and responses as log
    # records, not span attributes. Registered against traces
    # alone, the spans arrive with no content on them.
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter())
    )
    otel_logs.set_logger_provider(logger_provider)


setup_opentelemetry()
OpenAIInstrumentor().instrument()

# Import the client only after instrument(): auto-instrumentation
# patches modules as they load.
from openai import OpenAI  # noqa: E402

app = FastAPI(title="OpenAI Demo")

# The knob is deliberately not called OPENAI_BASE_URL, so the
# four demos in this repo name the gateway the same way.
_gateway = os.environ.get("OPENAI_GATEWAY_URL") or None
client = OpenAI(base_url=_gateway) if _gateway else OpenAI()
MODEL = os.environ.get("MODEL", "gpt-4o-mini")

CONDITIONS = ["clear", "cloudy", "light rain", "windy"]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]


def get_weather(city: str) -> dict:
    return {
        "city": city,
        "tempC": 12 + (len(city) % 15),
        "conditions": CONDITIONS[len(city) % len(CONDITIONS)],
    }


class ChatRequest(BaseModel):
    message: str = "Say hello in one sentence."


@app.post("/chat")
def chat(req: ChatRequest):
    """One model call, no tools."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are helpful. Answer in one sentence.",
            },
            {"role": "user", "content": req.message},
        ],
    )
    return {
        "text": response.choices[0].message.content,
        "usage": response.usage.model_dump() if response.usage else None,
    }


@app.post("/tool-call")
def tool_call(req: ChatRequest):
    """Two model calls around one tool execution."""
    messages = [
        {
            "role": "system",
            "content": "Use the tools. Answer in one sentence.",
        },
        {"role": "user", "content": req.message},
    ]

    first = client.chat.completions.create(
        model=MODEL, messages=messages, tools=TOOLS
    )
    message = first.choices[0].message
    if not message.tool_calls:
        return {"text": message.content, "tool_used": False}

    messages.append(message.model_dump(exclude_none=True))
    for call in message.tool_calls:
        args = json.loads(call.function.arguments)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(get_weather(**args)),
            }
        )

    second = client.chat.completions.create(
        model=MODEL, messages=messages, tools=TOOLS
    )
    return {
        "text": second.choices[0].message.content,
        "tool_used": True,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app, host="0.0.0.0", port=int(os.environ.get("PORT", 8095))
    )
