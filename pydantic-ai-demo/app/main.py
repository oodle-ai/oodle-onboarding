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
from pydantic_ai import Agent, ModelSettings, NativeOutput
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ThinkingPart, ToolCallPart
from pydantic_ai.models.anthropic import AnthropicModelSettings
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

# The research agent needs a thinking model, so it has its own setting.
RESEARCH_MODEL = os.environ.get("RESEARCH_MODEL", "anthropic:claude-opus-5")


def research_model_settings(model: str) -> ModelSettings:
    """Model settings that turn thinking on for the research agent.

    On Claude, adaptive thinking lets the model decide when to think,
    including between tool calls (interleaved thinking). Claude Opus 5
    defaults to display "omitted", which returns thinking blocks with
    empty text, so ask for "summarized" to get readable thinking into
    gen_ai.output.messages. Server-side fallbacks retry a refused
    request on another Claude model instead of failing the run.

    Other providers get Pydantic AI's unified `thinking` setting.
    """
    if not model.startswith("anthropic:"):
        return ModelSettings(thinking="high")
    return AnthropicModelSettings(
        max_tokens=16000,
        anthropic_thinking={"type": "adaptive", "display": "summarized"},
        anthropic_effort="high",
        anthropic_betas=["server-side-fallback-2026-07-01"],
        extra_body={"fallbacks": "default"},
    )


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


class ResearchReport(BaseModel):
    question: str
    recommendation: str
    key_findings: list[str]
    rejected_options: list[str]
    sources_cited: list[str]
    confidence: str


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


# Simulated research corpus. The two Lisbon sources disagree on
# internet quality, so the agent has to weigh recency in its thinking.
SOURCES = {
    "src-lisbon-2019": {
        "title": "Digital nomad notes: Lisbon",
        "published": "2019-04-02",
        "tags": ["lisbon", "internet", "coworking"],
        "text": (
            "Cafe wifi in Lisbon is patchy, often 20 Mbps or less. "
            "Coworking spaces are rare outside Cais do Sodre."
        ),
    },
    "src-lisbon-2026": {
        "title": "Portugal broadband report 2026",
        "published": "2026-02-10",
        "tags": ["lisbon", "internet", "coworking"],
        "text": (
            "Median fixed broadband in Lisbon is 180 Mbps; fiber reaches "
            "94% of homes. Over 60 coworking spaces with day passes."
        ),
    },
    "src-cdmx-2025": {
        "title": "Mexico City for remote teams",
        "published": "2025-11-18",
        "tags": ["mexico city", "internet", "coworking"],
        "text": (
            "Median fixed broadband is 95 Mbps. Short power cuts are "
            "common in the June-September rainy season."
        ),
    },
    "src-cdmx-air": {
        "title": "Air quality in Mexico City by month",
        "published": "2025-06-01",
        "tags": ["mexico city", "air quality", "weather"],
        "text": (
            "March to May is the ozone season: environmental "
            "contingencies restricting outdoor activity are declared "
            "several times most springs."
        ),
    },
    "src-tokyo-2025": {
        "title": "Tokyo for remote workers",
        "published": "2025-09-30",
        "tags": ["tokyo", "internet", "coworking"],
        "text": (
            "Median fixed broadband is 210 Mbps. Late March is cherry "
            "blossom season; short-term rentals book out early."
        ),
    },
    "src-flights-2026": {
        "title": "Round-trip fares from New York, March 2026",
        "published": "2026-01-15",
        "tags": ["flights", "lisbon", "mexico city", "tokyo"],
        "text": (
            "Average economy round trip per person: Lisbon $700, "
            "Mexico City $450, Tokyo $1,400."
        ),
    },
}


def search_sources(query: str) -> list[dict]:
    """Search research sources. Returns id, title, and publish date."""
    words = query.lower().split()
    return [
        {"id": source_id, "title": s["title"], "published": s["published"]}
        for source_id, s in SOURCES.items()
        if any(w in " ".join(s["tags"]) + " " + s["title"].lower() for w in words)
    ]


def read_source(source_id: str) -> str:
    """Read the full text of a source returned by search_sources."""
    source = SOURCES.get(source_id)
    if source is None:
        return f"No source with id {source_id}"
    return f"{source['title']} ({source['published']}): {source['text']}"


def get_cost_of_living(city: str) -> dict:
    """Monthly cost per person in USD, excluding flights."""
    costs = {
        "lisbon": {"rent": 1900, "food": 600, "coworking": 250, "transport": 60},
        "mexico city": {"rent": 1500, "food": 450, "coworking": 200, "transport": 40},
        "tokyo": {"rent": 2600, "food": 800, "coworking": 300, "transport": 100},
    }
    return costs.get(city.lower(), {"error": f"No cost data for {city}"})


def get_climate(city: str, month: str) -> str:
    """Typical climate for a city in a given month."""
    climate = {
        ("lisbon", "march"): "Avg high 18°C, 9 rainy days",
        ("mexico city", "march"): "Avg high 26°C, dry, 1 rainy day",
        ("tokyo", "march"): "Avg high 14°C, 10 rainy days",
    }
    return climate.get(
        (city.lower(), month.lower()),
        f"No climate data for {city} in {month}",
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

research_agent = Agent(
    name="research-agent",
    instructions=(
        "You are a research analyst. Answer the question from the "
        "tools, not from memory: search for sources, read the ones "
        "that matter, and pull cost and climate data for every option. "
        "When sources disagree, prefer the more recent one and say so. "
        "Show your arithmetic against any budget in key_findings."
    ),
    tools=[search_sources, read_source, get_cost_of_living, get_climate],
    # The default tool output forces a tool call every turn
    # (tool_choice "any"), and Claude doesn't think on forced turns.
    # Native structured output keeps tool_choice "auto".
    output_type=NativeOutput(ResearchReport),
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


DEFAULT_RESEARCH_QUESTION = (
    "Our 6-person team is based in New York and has a $25,000 budget "
    "for a 4-week remote-work offsite in March, flights included. "
    "Should we pick Lisbon, Mexico City, or Tokyo? We need reliable "
    "internet and weather that lets us work outdoors."
)


@app.post("/research")
async def research(question: str = DEFAULT_RESEARCH_QUESTION):
    """Research agent that thinks between tool calls.

    Returns the report plus the thinking and tool calls in the order
    the model produced them. The same sequence is on the trace: each
    chat span's gen_ai.output.messages holds the thinking parts.
    """
    result = await research_agent.run(
        question,
        model=RESEARCH_MODEL,
        model_settings=research_model_settings(RESEARCH_MODEL),
    )

    steps = []
    for message in result.all_messages():
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if isinstance(part, ThinkingPart) and part.content:
                steps.append({"type": "thinking", "content": part.content})
            elif isinstance(part, ToolCallPart):
                steps.append(
                    {
                        "type": "tool_call",
                        "tool": part.tool_name,
                        "args": part.args_as_dict(),
                    }
                )

    usage = result.usage
    return {
        "report": result.output.model_dump(),
        "model": RESEARCH_MODEL,
        "steps": steps,
        "usage": {
            "requests": usage.requests,
            "tool_calls": usage.tool_calls,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8091"))
    uvicorn.run(app, host="0.0.0.0", port=port)
