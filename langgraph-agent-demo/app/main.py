"""LangGraph agent observability demo.

Builds LangGraph graphs directly on StateGraph (a ReAct
loop with a ToolNode, and a two-agent pipeline) and traces
every node, model call and tool call through the LangChain
OpenTelemetry instrumentor. Spans go to Oodle via an OTel
Collector.
"""

import os
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
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
        {"service.name": "langgraph-agent-demo"}
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter())
    )
    set_tracer_provider(tracer_provider)


setup_opentelemetry()

# LangGraph runs its nodes through LangChain's callback system,
# so the LangChain instrumentor traces the graph, each node, every
# model call and every tool call. No manual spans required.
LangchainInstrumentor().instrument()

app = FastAPI(title="LangGraph Agent Demo")

MODEL = os.environ.get("MODEL", "gpt-4o-mini")


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
            "nature": "Luxembourg Gardens, Bois de Boulogne",
        },
    }
    city_data = attractions.get(city.lower(), {})
    return city_data.get(
        category.lower(),
        f"No {category} data for {city}",
    )


TOOLS = [get_current_time, get_weather, search_attractions]


# --- Graphs ---


def _build_react_graph():
    """A ReAct loop written directly on StateGraph.

    model -> (tool calls?) -> tools -> model ... -> END
    """
    llm = ChatOpenAI(model=MODEL, temperature=0).bind_tools(TOOLS)

    def call_model(state: MessagesState):
        return {"messages": [llm.invoke(state["messages"])]}

    graph = StateGraph(MessagesState)
    graph.add_node("model", call_model)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_edge(START, "model")
    # tools_condition routes to "tools" when the last message
    # carries tool calls, and to END otherwise.
    graph.add_conditional_edges("model", tools_condition)
    graph.add_edge("tools", "model")
    return graph.compile()


class PipelineState(MessagesState):
    city: str
    research: str
    plan: str


def _build_pipeline_graph():
    """Two agents in sequence, each its own node.

    research -> (enough?) -> plan -> END
    """
    researcher = ChatOpenAI(model=MODEL, temperature=0).bind_tools(
        TOOLS
    )
    planner = ChatOpenAI(model=MODEL, temperature=0)

    def research(state: PipelineState):
        city = state["city"]
        prompt = (
            f"Research {city}: find culture and food attractions "
            f"and check the weather. Call the tools, then write a "
            f"brief summary."
        )
        messages = [HumanMessage(content=prompt)]
        response = researcher.invoke(messages)
        messages.append(response)
        # Run the tool calls in-line so the summary has the results.
        for call in response.tool_calls:
            result = next(
                t for t in TOOLS if t.name == call["name"]
            ).invoke(call["args"])
            messages.append(
                {
                    "role": "tool",
                    "content": str(result),
                    "tool_call_id": call["id"],
                }
            )
        summary = researcher.invoke(messages)
        return {"research": summary.content, "messages": messages}

    def should_plan(
        state: PipelineState,
    ) -> Literal["plan", "__end__"]:
        return "plan" if state.get("research") else END

    def plan(state: PipelineState):
        response = planner.invoke(
            [
                SystemMessage(
                    content="You plan short city trips from research."
                ),
                HumanMessage(
                    content=(
                        f"Research about {state['city']}:\n\n"
                        f"{state['research']}\n\n"
                        f"Plan a 2-day trip in five bullet points."
                    )
                ),
            ]
        )
        return {"plan": response.content}

    graph = StateGraph(PipelineState)
    graph.add_node("research", research)
    graph.add_node("plan", plan)
    graph.add_edge(START, "research")
    graph.add_conditional_edges("research", should_plan)
    graph.add_edge("plan", END)
    return graph.compile()


REACT_GRAPH = _build_react_graph()
PIPELINE_GRAPH = _build_pipeline_graph()


# --- API endpoints ---


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "langgraph-agent-demo",
    }


@app.post("/chat")
async def chat(message: str = "What time is it?"):
    """ReAct loop on a StateGraph with a ToolNode."""
    result = await REACT_GRAPH.ainvoke(
        {"messages": [HumanMessage(content=message)]}
    )
    reply = result["messages"][-1].content
    return {"reply": reply, "model": MODEL}


@app.post("/plan-trip")
async def plan_trip(city: str = "Tokyo"):
    """Two-node pipeline: a research agent, then a planner."""
    result = await PIPELINE_GRAPH.ainvoke({"city": city, "messages": []})
    return {
        "research": result["research"],
        "trip_plan": result["plan"],
        "city": city,
        "model": MODEL,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8099"))
    uvicorn.run(app, host="0.0.0.0", port=port)
