"""LiteLLM observability demo.

LiteLLM routes one call to whichever provider the model names, and
its OTel callback emits GenAI spans for each of them. Traces go to
Oodle through an OTel Collector.
"""

import json
import os

import litellm
from fastapi import FastAPI
from pydantic import BaseModel

# LiteLLM builds its own tracer provider from the
# OTEL_EXPORTER_OTLP_* variables in docker-compose.yml, so there is
# no OpenTelemetry SDK setup to write here. The `otel` callback is
# the whole integration.
litellm.callbacks = ["otel"]

app = FastAPI(title="LiteLLM Demo")

MODEL = os.environ.get("MODEL", "gpt-4o-mini")
API_BASE = os.environ.get("OPENAI_GATEWAY_URL") or None

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


def completion(**kwargs):
    if API_BASE:
        kwargs["api_base"] = API_BASE
    return litellm.completion(model=MODEL, **kwargs)


class ChatRequest(BaseModel):
    message: str = "Say hello in one sentence."


@app.post("/chat")
def chat(req: ChatRequest):
    """One model call, no tools."""
    response = completion(
        messages=[
            {
                "role": "system",
                "content": "You are helpful. Answer in one sentence.",
            },
            {"role": "user", "content": req.message},
        ]
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

    first = completion(messages=messages, tools=TOOLS)
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

    second = completion(messages=messages, tools=TOOLS)
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
        app, host="0.0.0.0", port=int(os.environ.get("PORT", 8096))
    )
