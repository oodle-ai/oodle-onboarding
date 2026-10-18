# Claude Managed Agents (SDK + API tracing + a custom tool's service)

A Managed Agents session where a data analyst agent pulls sales data with a
custom tool, `query_warehouse`, then writes and runs a Python script in its
Anthropic-hosted sandbox. The custom tool is backed by a separate Python
service, [`warehouse`](./warehouse), that has no tracing code: it runs under
OpenTelemetry's zero-code auto-instrumentation. The trace has three sources:

- **SDK tracing** (this process): an `anthropic.sessions.*` CLIENT span for
  each Sessions API request.
- **API tracing** (Anthropic's side): the SERVER span of each request, and
  the work the agent does: `anthropic.session.turn`, its
  `anthropic.model_request` spans, and an `anthropic.tool_use <tool>` span for
  each sandbox tool (`bash`, `write`, ...).
- **Custom tool** (this process and the warehouse): an
  `anthropic.custom_tool_use query_warehouse` span for each call, the
  instrumented httpx `POST` to the warehouse, and the warehouse's own
  `POST /query` SERVER span with a `SELECT` span under it.

The SDK sees only the requests, so without the
[destination](../README.md#api-tracing-destination) you get the CLIENT spans
and nothing about what the agent did as spans. The app span still gets a
summary from the event stream: an `agent.tool_use` span event per tool call,
and `demo.session.*` token totals and stop reason. Those use the `demo.*`
namespace, not `gen_ai.usage.*`, so they aren't counted twice once
Anthropic's `anthropic.model_request` spans arrive under the same trace.

```
demo.managed_agent_task                             claude-otel-managed-agents
├─ anthropic.sessions.create            [CLIENT]
│  └─ anthropic.sessions.create         [SERVER]    claude-platform
├─ anthropic.sessions.events.stream     [CLIENT]
├─ anthropic.sessions.events.send       [CLIENT]    the task
│  └─ anthropic.sessions.events.send    [SERVER]    claude-platform
│     └─ anthropic.session.turn                     stop_reason=requires_action
│        └─ anthropic.model_request                 asks for query_warehouse
├─ anthropic.custom_tool_use query_warehouse        claude-otel-managed-agents
│  └─ POST                              [CLIENT]    (httpx instrumentation)
│     └─ POST /query                    [SERVER]    claude-otel-warehouse
│        └─ SELECT                      [CLIENT]    (sqlite3 instrumentation)
└─ anthropic.sessions.events.send       [CLIENT]    the tool result
   └─ anthropic.sessions.events.send    [SERVER]    claude-platform
      └─ anthropic.session.turn                     stop_reason=end_turn
         ├─ anthropic.model_request
         ├─ anthropic.tool_use bash
         └─ anthropic.model_request
```

## The custom tool and its service

A custom tool runs in the client, not in the sandbox. When the agent calls
`query_warehouse`, the session emits `agent.custom_tool_use` and goes idle
(`requires_action`). `main.py` sends the SQL to the warehouse and answers
with a `user.custom_tool_result`, which starts the next turn. The sandbox
never talks to the warehouse, so it needs no network access or tunnel.

How the warehouse's spans get into the agent's trace:

1. `main.py` opens `anthropic.custom_tool_use query_warehouse` under the app
   span, with the name and `gen_ai.*` attributes the SDK's own tool runners
   give a custom tool. In content mode it records the SQL
   (`gen_ai.tool.call.arguments`) and the rows (`anthropic.tool_result.content`).
2. The warehouse request runs inside that span. `opentelemetry-instrumentation-httpx`
   makes a CLIENT span and adds `traceparent` to the request. (The Claude SDK
   sends over `httpx2`, so instrumenting `httpx` doesn't touch its requests.)
3. The warehouse runs as `opentelemetry-instrument uvicorn app:app`. The
   FastAPI instrumentation reads `traceparent`, so its SERVER span joins the
   same trace, and the sqlite3 instrumentation adds a span per query.
   `opentelemetry-bootstrap -a install` (in the Dockerfile) picked those
   instrumentations from what's installed. Exporter settings are `OTEL_*`
   variables in `docker-compose.yml`, with `service.name=claude-otel-warehouse`.
   `OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST=traceparent`
   records the header it got on the span as `http.request.header.traceparent`:
   its trace id and parent span id are the caller's `POST` span.

In Oodle's Agent Observability trace view, the tree shows only GenAI spans
at first. Click **All spans** (above the duration column) to see the
warehouse's spans under the tool span.

The app adds two attributes of its own to the request span
(`warehouse.row_count`, `warehouse.truncated`) through the OpenTelemetry API;
everything else comes from auto-instrumentation.

The custom tool's span sits under the app span, between the two turns, not
under the `anthropic.session.turn` that asked for it. No session event
carries that turn's span context, and the turn has already ended
(`stop_reason=requires_action`) when the tool runs: a custom tool runs
between turns, and its result starts the next one. (Sandbox tools such as
`bash` run inside a turn, so Anthropic puts their spans in it.) The tool
span carries the same `gen_ai.conversation.id` as the turns, the session
thread id (`sthr_...`), and its `gen_ai.tool.call.id` is the tool call id in
the first turn's `gen_ai.output.messages` and the next turn's
`gen_ai.input.messages`.

The warehouse is a SQLite file of 2025 orders (`orders`, `products`), built
from a fixed seed at image build time, so seeding adds no spans. Queries are
read-only (an authorizer allows `SELECT` only), capped at 200 rows and 5
seconds. A bad query answers 400; `main.py` passes the message back with
`is_error: true` so the agent can fix its SQL, and the tool span is marked
`error.type=tool_error`.

## Run

```bash
make managed-agents-setup   # once: prints MANAGED_AGENT_ID / MANAGED_ENVIRONMENT_ID
# paste both into ../.env
make managed-agents         # starts the warehouse, then runs a session
make managed-agents-logs    # tail the warehouse

# your own task:
docker compose run --rm --build managed-agents main.py "Compute the first 20 primes and their sum"
```

`provision.py` creates a cloud environment with limited networking and an
agent (`CLAUDE_MODEL`, the built-in agent toolset, web tools off, `auto`
permission policy, and the `query_warehouse` custom tool). Agents are
persistent and versioned, so this runs once, not on every session.
Re-running it with the ids set brings the agent's system prompt and tools up
to date: an agent made before the custom tool existed gets a new version
with it, and an up-to-date one is left alone.

`main.py`:

1. Opens a span of its own and creates a session inside it.
2. Opens the event stream **before** sending the task, since the stream
   delivers only events that happen after it opens.
3. Sends the task as a `user.message`.
4. Prints the agent's messages and tool calls until the session goes idle,
   answering each `query_warehouse` call from the warehouse.

A tool call that needs approval is denied, because nobody is watching.

The run prints the `trace_id` and the session's Console URL. The Console's
session viewer shows the same session with no setup, which is useful for
comparing against the trace.

## Cleanup

Nothing is deleted automatically. To remove what the demo created:

```bash
ant beta:agents archive --agent-id "$MANAGED_AGENT_ID"
ant beta:environments archive --environment-id "$MANAGED_ENVIRONMENT_ID"
```
