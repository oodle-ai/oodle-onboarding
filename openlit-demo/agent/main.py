"""LangGraph ReAct agent instrumented with OpenLIT in one line.

Matches the blog's canonical example: Anthropic Claude + Tavily search +
MemorySaver checkpointer. Set PROVIDER=google to use Gemini instead.

Demonstrates the nested span trees (invoke_workflow / invoke_agent / chat /
execute_tool) that OpenLIT auto-generates for LangGraph agents, exported to
Oodle via the shared OTel Collector.
"""

import os
from datetime import datetime, timezone

import openlit
from fastapi import FastAPI, Query
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

openlit.init(
    service_name="research-agent",
    environment=os.environ.get("OTEL_DEPLOYMENT_ENVIRONMENT", "production"),
    otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"),
    capture_message_content=True,
    custom_metrics_attributes={"team": "platform-ai"},
)

app = FastAPI(title="OpenLIT Agent Demo")

PROVIDER = os.environ.get("PROVIDER", "anthropic")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
TAVILY_MAX_RESULTS = int(os.environ.get("TAVILY_MAX_RESULTS", "2"))

memory = MemorySaver()


# --- Tools ---


def _create_search_tool():
    from langchain_community.tools.tavily_search import TavilySearchResults
    return TavilySearchResults(max_results=TAVILY_MAX_RESULTS)


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
    return weather_data.get(city.lower(), f"Mild, 20°C (no data for {city})")


@tool
def search_attractions(city: str, category: str) -> str:
    """Search for attractions in a city by category.

    Categories: culture, food, nature.
    """
    attractions = {
        "tokyo": {
            "culture": "Senso-ji Temple, Meiji Shrine, Tokyo National Museum",
            "food": "Tsukiji Outer Market, Ramen Street, Yakitori Alley",
            "nature": "Shinjuku Gyoen, Mount Takao, Ueno Park",
        },
        "paris": {
            "culture": "Louvre, Musée d'Orsay, Sacré-Cœur",
            "food": "Le Marais, Rue Montorgueil, Saint-Germain cafés",
            "nature": "Luxembourg Gardens, Bois de Boulogne, Tuileries",
        },
        "new york": {
            "culture": "MoMA, Met Museum, Broadway",
            "food": "Chelsea Market, Smorgasburg, Chinatown",
            "nature": "Central Park, High Line, Brooklyn Botanic Garden",
        },
    }
    city_data = attractions.get(city.lower(), {})
    return city_data.get(category.lower(), f"No {category} data for {city}")


@tool
def calculate_budget(city: str, days: int, style: str) -> str:
    """Estimate travel budget for a trip.

    Style options: budget, moderate, luxury.
    """
    daily_costs = {"budget": 80, "moderate": 150, "luxury": 350}
    daily = daily_costs.get(style.lower(), 150)
    total = daily * days
    return f"Estimated {days}-day {style} trip to {city}: ${total} USD (~${daily}/day)"


# --- Agents ---


def _create_llm():
    if PROVIDER == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=0)
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model=ANTHROPIC_MODEL)


def _create_research_agent():
    """The blog's canonical example: LLM + Tavily search + MemorySaver."""
    search = _create_search_tool()
    return create_react_agent(
        _create_llm(), [search], checkpointer=memory,
    )


def _create_travel_agent():
    """Multi-tool agent for trip planning."""
    search = _create_search_tool()
    return create_react_agent(
        _create_llm(),
        tools=[search, get_weather, search_attractions, calculate_budget],
        checkpointer=memory,
    )


# --- Endpoints ---


_thread_counter = 0


def _next_thread_id() -> str:
    global _thread_counter
    _thread_counter += 1
    return f"thread-{_thread_counter}"


@app.get("/health")
async def health():
    model = ANTHROPIC_MODEL if PROVIDER == "anthropic" else GEMINI_MODEL
    return {"status": "ok", "service": "research-agent", "provider": PROVIDER, "model": model}


@app.post("/chat")
async def chat(message: str = Query(default="whats the weather in San Francisco?")):
    """Research-style chat with Tavily search — the blog's canonical agent pattern.

    Produces nested span trees: invoke_workflow -> invoke_agent -> chat + execute_tool.
    """
    agent = _create_research_agent()
    config = {"configurable": {"thread_id": _next_thread_id()}}
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=message)]}, config,
    )
    reply = result["messages"][-1].content
    model = ANTHROPIC_MODEL if PROVIDER == "anthropic" else GEMINI_MODEL
    return {"reply": reply, "model": model, "provider": PROVIDER}


@app.post("/plan-trip")
async def plan_trip(
    city: str = Query(default="Paris"),
    days: int = Query(default=3),
    style: str = Query(default="moderate"),
):
    """Plan a trip using a ReAct agent with Tavily search + simulated tools.

    Produces deep span trees with multiple tool invocations per turn.
    """
    agent = _create_travel_agent()
    config = {"configurable": {"thread_id": _next_thread_id()}}
    prompt = (
        f"Plan a {days}-day {style} trip to {city}. "
        f"Search for real-time travel info, "
        f"check the weather for packing tips, and "
        f"estimate the budget. "
        f"Provide a structured summary."
    )
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=prompt)]}, config,
    )
    reply = result["messages"][-1].content
    model = ANTHROPIC_MODEL if PROVIDER == "anthropic" else GEMINI_MODEL
    return {"trip_plan": reply, "city": city, "days": days, "model": model}


@app.post("/research")
async def research(query: str = Query(default="latest developments in AI observability")):
    """Open-ended research using the ReAct agent with Tavily search."""
    agent = _create_research_agent()
    config = {"configurable": {"thread_id": _next_thread_id()}}
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=query)]}, config,
    )
    reply = result["messages"][-1].content
    model = ANTHROPIC_MODEL if PROVIDER == "anthropic" else GEMINI_MODEL
    return {"research": reply, "query": query, "model": model}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8093"))
    uvicorn.run(app, host="0.0.0.0", port=port)
