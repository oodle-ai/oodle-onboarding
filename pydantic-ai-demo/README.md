# Pydantic AI Demo

Agent observability demo using [Pydantic AI](https://pydantic.dev/pydantic-ai) with built-in OpenTelemetry instrumentation, exporting traces to Oodle via an OTel Collector.

Pydantic AI automatically emits spans following the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — no manual instrumentation required. One call to `Agent.instrument_all()` enables tracing for all agents.

## Architecture

```
User Request
     |
     v
FastAPI App (:8091) — Pydantic AI agents with OTel instrumentation
     |
     +---> LLM API (OpenAI, Google, Anthropic, etc.)
     |
     v
OTel Collector (OTLP :4318) --> Oodle (traces)
```

## What Gets Traced

Pydantic AI v5 instrumentation emits spans for:

| Span | `gen_ai.operation.name` | Key Attributes |
|------|------------------------|----------------|
| Agent run | `invoke_agent` | `gen_ai.agent.name`, `gen_ai.usage.*` |
| Model request | `chat` | `gen_ai.request.model`, `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |
| Tool execution | `execute_tool` | `gen_ai.tool.name`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result` |

When the model thinks, each `chat` span's `gen_ai.output.messages` carries
`{"type": "thinking", "content": ...}` parts next to the tool calls. See
[Thinking Blocks](#thinking-blocks).

## Prerequisites

- Docker & Docker Compose
- An [Oodle](https://oodle.ai) account (instance ID and API key)
- An [OpenAI](https://platform.openai.com/api-keys) API key (or another supported provider)
- An [Anthropic](https://platform.claude.com/settings/keys) API key for the `/research` agent

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
   ANTHROPIC_API_KEY=your-anthropic-api-key
   ```

3. Build and start all services:
   ```bash
   make up
   ```

4. Send test requests:
   ```bash
   make test-chat      # simple chat with tool use
   make test-city      # structured output (CityInfo)
   make test-trip      # tool use + structured output
   make test-review    # code review (structured output)
   make test-multi     # multi-agent workflow
   make test-research  # research agent that thinks between tool calls
   ```

## API Endpoints

### POST /chat
General chat with tool access (weather, time).

### POST /city-info?city=Tokyo
Returns structured `CityInfo` with weather lookup.

### POST /plan-trip?city=Paris&days=3
Plans a trip using attraction search and weather tools.

### POST /review-code
Reviews a code snippet, returns structured `CodeReview`.

### POST /multi-agent?city=Tokyo
Runs two agents sequentially: city info feeds into trip planning.

### POST /research?question=...
Research agent on `RESEARCH_MODEL` (default `anthropic:claude-opus-5`) with
thinking turned on. Returns a structured `ResearchReport` and the `steps` the
model took (thinking and tool calls, in order). The default question asks it to
pick an offsite city under a budget.

### GET /health
Health check.

## Viewing Traces in Oodle

1. Log in to your Oodle instance
2. Navigate to **GenAI > Traces** (`/genai/traces`)
3. Filter by service name `pydantic-ai-demo`
4. Click on a trace to see:
   - **Agent run spans** (`invoke_agent`) showing the full agent workflow
   - **Model request spans** (`chat`) with prompt/response content
   - **Tool execution spans** (`execute_tool`) with arguments and results
   - **Token usage** on each model call
   - **Structured outputs** validated by Pydantic
   - **Latency breakdown** across agents, tools, and model calls

## Thinking Blocks

`/research` runs `research-agent`, which answers a question by searching
sources, reading them, and pulling cost and climate data. With thinking on,
Claude can reason before its first tool call and between tool results
(interleaved thinking). The data is simulated and built to need that reasoning:

- Two Lisbon sources disagree on internet speed (2019 vs 2026), so the
  model has to decide which one to trust.
- The budget includes flights, so it has to add up cost of living for six
  people plus fares, and Tokyo comes out over budget.
- Mexico City is cheapest, but a source flags March as its ozone season.

The thinking config lives in `research_model_settings()` in `app/main.py`:

```python
AnthropicModelSettings(
    max_tokens=16000,
    anthropic_thinking={"type": "adaptive", "display": "summarized"},
    anthropic_effort="high",
    anthropic_betas=["server-side-fallback-2026-07-01"],
    extra_body={"fallbacks": "default"},
)
```

- `adaptive` lets Claude decide when and how much to think, including
  between tool calls.
- `display: "summarized"` matters. Claude Opus 5 defaults to `"omitted"`,
  which returns thinking blocks with empty text, so the spans would show
  thinking parts with nothing in them.
- `anthropic_effort` controls thinking depth and token spend.
- The fallback setting retries a refused request on another Claude model
  instead of failing the run.

The agent also uses `output_type=NativeOutput(ResearchReport)`. Pydantic AI's
default tool output sets `tool_choice` to `"any"`, which forces a tool call on
every turn, and Claude doesn't think on forced turns. Native structured output
keeps `tool_choice` on `"auto"`, so the thinking blocks come back.

For a non-Claude `RESEARCH_MODEL` the agent uses Pydantic AI's unified
`thinking="high"` setting instead.

Try it:

```bash
make test-research
curl -s -X POST 'http://localhost:8091/research' \
  --get --data-urlencode 'question=Lisbon or Tokyo for 2 people for 2 weeks in March on $8,000?' \
  | python3 -m json.tool
```

In Oodle, open the `research-agent` trace. The `invoke_agent` span has one
`chat` span per model turn, and they alternate with `execute_tool` spans. Open a
`chat` span's output messages to see the thinking part behind its tool calls.
Adaptive thinking skips turns it doesn't need, so not every `chat` span has one.
The final `chat` span holds the reasoning behind the recommendation.

## Using a Different Model

Pydantic AI supports multiple providers. Set the `MODEL` env var:

```bash
# OpenAI
MODEL=openai:gpt-4o-mini

# Google Gemini (requires GOOGLE_API_KEY in .env)
MODEL=google:gemini-3.5-flash

# Anthropic (requires ANTHROPIC_API_KEY in .env)
MODEL=anthropic:claude-sonnet-4-20250514
```

The `/research` agent reads `RESEARCH_MODEL` instead, so it can stay on a
thinking model while the other agents use `MODEL`.

## Cleanup

```bash
make clean
```
