"""LangChain agent observability demo.

Demonstrates ReAct agents with tool use, multi-agent
workflows, and full OpenTelemetry tracing exported to
Oodle via an OTel Collector.
"""

import os
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.langchain import (
    LangchainInstrumentor,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider


def setup_opentelemetry():
    resource = Resource.create(
        {"service.name": "langchain-agent-demo"}
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter())
    )
    set_tracer_provider(tracer_provider)


setup_opentelemetry()

LangchainInstrumentor().instrument()

app = FastAPI(title="LangChain Agent Demo")

MODEL = os.environ.get("MODEL", "gemini-2.5-flash")
PROVIDER = os.environ.get("PROVIDER", "google")


# --- Tools ---


@tool
def get_current_time() -> str:
    """Get the current UTC time."""
    return datetime.now(timezone.utc).isoformat()


@tool
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


@tool
def search_attractions(city: str, category: str) -> str:
    """Search for attractions in a city by category.

    Categories: culture, food, nature.
    """
    attractions = {
        "tokyo": {
            "culture": "Senso-ji Temple, Meiji Shrine",
            "food": "Tsukiji Market, Ramen Street",
            "nature": "Shinjuku Gyoen, Mount Takao",
        },
        "paris": {
            "culture": "Louvre, Musée d'Orsay",
            "food": "Le Marais, Rue Montorgueil",
            "nature": (
                "Luxembourg Gardens, Bois de Boulogne"
            ),
        },
    }
    city_data = attractions.get(city.lower(), {})
    return city_data.get(
        category.lower(),
        f"No {category} data for {city}",
    )


@tool
def calculate_budget(
    city: str,
    days: int,
    style: str,
) -> str:
    """Estimate travel budget for a trip.

    Style options: budget, moderate, luxury.
    """
    daily_costs = {
        "budget": 80,
        "moderate": 150,
        "luxury": 350,
    }
    daily = daily_costs.get(style.lower(), 150)
    total = daily * days
    return (
        f"Estimated {days}-day {style} trip to {city}: "
        f"${total} USD (~${daily}/day)"
    )


# --- Agents ---


def _create_llm():
    if PROVIDER == "google":
        return ChatGoogleGenerativeAI(
            model=MODEL,
            temperature=0,
        )
    return ChatOpenAI(model=MODEL, temperature=0)


def _create_chat_agent():
    return create_react_agent(
        _create_llm(),
        tools=[get_current_time, get_weather],
    )


def _create_travel_agent():
    return create_react_agent(
        _create_llm(),
        tools=[
            get_weather,
            search_attractions,
            calculate_budget,
        ],
    )


def _create_research_agent():
    return create_react_agent(
        _create_llm(),
        tools=[
            get_weather,
            search_attractions,
            get_current_time,
        ],
    )


# --- API endpoints ---


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "langchain-agent-demo",
    }


@app.post("/chat")
async def chat(message: str = "What time is it?"):
    """General chat with tool access."""
    agent = _create_chat_agent()
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=message)]}
    )
    reply = result["messages"][-1].content
    return {"reply": reply, "model": MODEL}


@app.post("/plan-trip")
async def plan_trip(
    city: str = "Paris",
    days: int = 3,
    style: str = "moderate",
):
    """Plan a trip using a ReAct agent with tools."""
    agent = _create_travel_agent()
    prompt = (
        f"Plan a {days}-day {style} trip to {city}. "
        f"Look up cultural and food attractions, "
        f"check the weather for packing tips, and "
        f"estimate the budget. "
        f"Provide a structured summary."
    )
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=prompt)]}
    )
    reply = result["messages"][-1].content
    return {
        "trip_plan": reply,
        "city": city,
        "days": days,
        "model": MODEL,
    }


@app.post("/research")
async def research(city: str = "Tokyo"):
    """Research a city using a ReAct agent."""
    agent = _create_research_agent()
    prompt = (
        f"Research {city} as a travel destination. "
        f"Find cultural, food, and nature attractions. "
        f"Check the current weather. "
        f"Summarize your findings."
    )
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=prompt)]}
    )
    reply = result["messages"][-1].content
    return {"research": reply, "city": city, "model": MODEL}


@app.post("/multi-agent")
async def multi_agent(city: str = "Tokyo"):
    """Multi-agent workflow: research then plan."""
    research_agent = _create_research_agent()
    research_prompt = (
        f"Research {city}: find key attractions "
        f"(culture, food, nature) and check weather. "
        f"Provide a brief summary."
    )
    research_result = await research_agent.ainvoke(
        {
            "messages": [
                HumanMessage(content=research_prompt)
            ]
        }
    )
    research_summary = (
        research_result["messages"][-1].content
    )

    travel_agent = _create_travel_agent()
    plan_prompt = (
        f"Based on this research about {city}:\n\n"
        f"{research_summary}\n\n"
        f"Plan a 3-day moderate trip. "
        f"Estimate the budget and suggest packing tips "
        f"based on the weather."
    )
    plan_result = await travel_agent.ainvoke(
        {"messages": [HumanMessage(content=plan_prompt)]}
    )
    plan_summary = plan_result["messages"][-1].content

    return {
        "research": research_summary,
        "trip_plan": plan_summary,
        "city": city,
        "model": MODEL,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8092"))
    uvicorn.run(app, host="0.0.0.0", port=port)
