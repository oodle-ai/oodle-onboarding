# LangGraph Agent Demo

Agent observability demo for graphs built directly on
[LangGraph](https://langchain-ai.github.io/langgraph/)'s `StateGraph`,
traced through the
[LangChain OpenTelemetry instrumentor](https://github.com/traceloop/openllmetry/tree/main/packages/opentelemetry-instrumentation-langchain)
and exported to Oodle via an OTel Collector.

LangGraph runs every node through LangChain's callback system, so one
call to `LangchainInstrumentor().instrument()` traces the graph run,
each node, every model call and every tool call. There is no
LangGraph-specific instrumentor and no manual span.

The same graph is also built in TypeScript on
[LangGraph.js](https://langchain-ai.github.io/langgraphjs/), served
from a second container, to show the one thing the JavaScript
instrumentation needs that the Python one does not (see below).

## Architecture

```
POST /chat | POST /plan-trip          POST /chat
     |                                     |
     v                                     v
FastAPI app (:8099)                   Node app (:8101)
StateGraph agents,                    LangGraph.js StateGraph,
LangChain OTel instrumentor           LangChain OTel instrumentation
     |                                     |
     +---> LLM API (OpenAI, or an OpenAI-compatible gateway)
     |                                     |
     v                                     v
OTel Collector (OTLP :4318) --> Oodle (traces)
```

## What Gets Traced

| Span | `gen_ai.operation.name` | Key Attributes |
|------|------------------------|----------------|
| Graph run | `invoke_agent` | `gen_ai.agent.name` (`LangGraph`), `gen_ai.workflow.nodes`, `gen_ai.workflow.edges` |
| Node | `execute_task` | `gen_ai.task.name` (the node name), node input and output |
| Model call | `chat` | `gen_ai.request.model`, `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |
| Tool call | `execute_tool` | `gen_ai.tool.name`, arguments, result |

## The JavaScript instrumentation needs an active span

`@traceloop/instrumentation-langchain` (the Node package) starts
every callback span under whatever span is **active** when it starts,
and reads no `parentRunId`. With no active span, each node, model
call and tool call becomes a root of its own, and one run arrives as
a dozen one-span traces with every number on them correct.

`app-ts/src/instrumentation.js` therefore registers the HTTP
instrumentation beside the LangChain one: the request span is active
while the handler runs, so one request is one trace with no manual
span. A script with no server opens one span per run with
`tracer.startActiveSpan(...)`, which is what the Oodle LangGraph and
LangChain tiles show for TypeScript. The Python instrumentor links
spans through the callback parent ids and needs neither.

## Two graphs

- **`/chat`**: a ReAct loop written on `StateGraph` with a `ToolNode`
  and `tools_condition`. The model calls tools until it has an answer.
- **`/plan-trip`**: two agents as two nodes, joined by a conditional
  edge: a research node that calls tools, then a planner node that
  writes from the research.

## Prerequisites

- Docker & Docker Compose
- An [Oodle](https://oodle.ai) account (instance ID and API key)
- An [OpenAI](https://platform.openai.com/api-keys) API key

## Quick Start

```bash
make help        # view available commands
```

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your credentials:
   ```bash
   OODLE_INSTANCE=your-instance-id
   OODLE_API_KEY=your-api-key
   OPENAI_API_KEY=your-openai-api-key
   ```

3. Build and start all services:
   ```bash
   make up
   ```

4. Send test requests:
   ```bash
   make test-chat      # ReAct loop with tool calls (Python)
   make test-trip      # research node, then planner node (Python)
   make test-chat-ts   # ReAct loop with tool calls (LangGraph.js)
   make test-all       # all three
   ```

## Viewing Traces in Oodle

1. Log in to your Oodle instance
2. Navigate to **Agent Observability > Traces** (`/genai/traces`)
3. Filter by service name `langgraph-agent-demo` (Python) or
   `langgraph-agent-demo-ts` (LangGraph.js)
4. Click a trace to see the graph run, each node, the model calls
   with their prompt and response, the tool calls, and the token
   usage and cost
5. Open the **Agent Graph** tab for the call topology: the
   `LangGraph` agent, its model calls and its tools

## Using a Different Model

`MODEL` takes an OpenAI model id:

```bash
MODEL=gpt-4o-mini
MODEL=gpt-4o
```

Set `OPENAI_GATEWAY_URL` to call an OpenAI-compatible gateway instead.
A gateway that answers with its own model id (for example
`openai/gpt-4o-mini`) is traced the same way, but Oodle prices cost
from the response model, so an id it does not know shows no cost.

## Cleanup

```bash
make clean
```
