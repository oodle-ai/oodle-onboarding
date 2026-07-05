"""Pydantic AI agent observability demo.

Demonstrates multi-agent workflows with tool use,
structured outputs, and full OpenTelemetry tracing
exported to Oodle via an OTel Collector.
"""

import os
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.instrumented import InstrumentationSettings


def setup_opentelemetry():
    resource = Resource.create(
        {"service.name": "pydantic-ai-demo"}
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter())
    )
    set_tracer_provider(tracer_provider)


setup_opentelemetry()

Agent.instrument_all(
    InstrumentationSettings(
        use_aggregated_usage_attribute_names=False,
    )
)

app = FastAPI(title="Pydantic AI Demo")

MODEL = os.environ.get("MODEL", "openai:gpt-4o-mini")


@app.exception_handler(ModelHTTPError)
async def model_http_error_handler(request, exc):
    return JSONResponse(
        status_code=502,
        content={
            "error": str(exc),
            "model": exc.model_name,
        },
    )


# --- Structured output models ---


class CityInfo(BaseModel):
    name: str
    country: str
    population_estimate: int
    famous_for: list[str]
    best_time_to_visit: str


class TripPlan(BaseModel):
    destination: str
    duration_days: int
    activities: list[str]
    estimated_budget_usd: float
    packing_tips: list[str]


class CodeReview(BaseModel):
    summary: str
    issues: list[str]
    suggestions: list[str]
    quality_score: int


# --- Tools ---


def get_current_time() -> str:
    """Get the current UTC time."""
    return datetime.now(timezone.utc).isoformat()


def get_weather(city: str) -> str:
    """Get current weather for a city (simulated)."""
    weather_data = {
        "tokyo": "Clear, 22°C",
        "paris": "Cloudy, 18°C",
        "new york": "Sunny, 25°C",
        "london": "Rainy, 14°C",
        "sydney": "Warm, 28°C",
    }
    return weather_data.get(
        city.lower(),
        f"Mild, 20°C (no data for {city})",
    )


def search_attractions(city: str, category: str) -> str:
    """Search for attractions in a city by category."""
    attractions = {
        "tokyo": {
            "culture": "Senso-ji Temple, Meiji Shrine",
            "food": "Tsukiji Market, Ramen Street",
            "nature": "Shinjuku Gyoen, Mount Takao",
        },
        "paris": {
            "culture": "Louvre, Musée d'Orsay",
            "food": "Le Marais, Rue Montorgueil",
            "nature": "Luxembourg Gardens, Bois de Boulogne",
        },
    }
    city_data = attractions.get(city.lower(), {})
    return city_data.get(
        category.lower(),
        f"No {category} data for {city}",
    )


# --- Agents ---

city_info_agent = Agent(
    name="city-info-agent",
    instructions=(
        "You are a knowledgeable travel expert. "
        "Provide accurate, concise city information. "
        "Use tools when available."
    ),
    tools=[get_weather, get_current_time],
    output_type=CityInfo,
)

trip_planner_agent = Agent(
    name="trip-planner-agent",
    instructions=(
        "You are an experienced trip planner. "
        "Create practical, budget-conscious travel plans. "
        "Use search_attractions to find specific activities."
    ),
    tools=[search_attractions, get_weather],
    output_type=TripPlan,
)

code_review_agent = Agent(
    name="code-review-agent",
    instructions=(
        "You are a senior software engineer. "
        "Review code for bugs, style issues, and "
        "suggest improvements. Be constructive."
    ),
    output_type=CodeReview,
)

chat_agent = Agent(
    name="chat-agent",
    instructions=(
        "You are a helpful assistant. "
        "Keep responses concise and informative. "
        "Use tools when they can help answer the question."
    ),
    tools=[get_current_time, get_weather],
)


# --- API endpoints ---


@app.get("/health")
async def health():
    return {"status": "ok", "service": "pydantic-ai-demo"}


@app.post("/chat")
async def chat(message: str = "What time is it?"):
    """General chat with tool access."""
    result = await chat_agent.run(message, model=MODEL)
    return {"reply": result.output, "model": MODEL}


@app.post("/city-info")
async def city_info(city: str = "Tokyo"):
    """Get structured city information."""
    result = await city_info_agent.run(
        f"Tell me about {city} as a travel destination. "
        f"Include current weather.",
        model=MODEL,
    )
    return {"city_info": result.output.model_dump()}


@app.post("/plan-trip")
async def plan_trip(
    city: str = "Paris",
    days: int = 3,
):
    """Plan a trip with activities and budget."""
    result = await trip_planner_agent.run(
        f"Plan a {days}-day trip to {city}. "
        f"Find cultural and food attractions. "
        f"Check the weather to give packing tips.",
        model=MODEL,
    )
    return {"trip_plan": result.output.model_dump()}


@app.post("/review-code")
async def review_code(
    code: str = "def add(a, b): return a + b",
):
    """Review a code snippet."""
    result = await code_review_agent.run(
        f"Review this code:\n\n```\n{code}\n```",
        model=MODEL,
    )
    return {"review": result.output.model_dump()}


@app.post("/multi-agent")
async def multi_agent(city: str = "Tokyo"):
    """Multi-agent workflow: city info then trip plan."""
    info_result = await city_info_agent.run(
        f"Tell me about {city}. Include current weather.",
        model=MODEL,
    )

    plan_result = await trip_planner_agent.run(
        f"Plan a 3-day trip to {city}. "
        f"The city is famous for: "
        f"{', '.join(info_result.output.famous_for)}. "
        f"Best time to visit: "
        f"{info_result.output.best_time_to_visit}.",
        model=MODEL,
    )

    return {
        "city_info": info_result.output.model_dump(),
        "trip_plan": plan_result.output.model_dump(),
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8091"))
    uvicorn.run(app, host="0.0.0.0", port=port)
