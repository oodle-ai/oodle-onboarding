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
from a fixed seed at image build time, so seeding adds no spans. APAC's orders
are in the `apac-orders` service, which the warehouse fetches them from on
each query. Queries are
read-only (an authorizer allows `SELECT` only), capped at 200 rows and 5
seconds. A bad query answers 400; `main.py` passes the message back with
`is_error: true` so the agent can fix its SQL, and the tool span is marked
`error.type=tool_error`.

## Run

```bash
make managed-agents-setup   # once: prints MANAGED_AGENT_ID / MANAGED_ENVIRONMENT_ID
# paste both into ../.env
make managed-agents         # starts the warehouse, then runs a session
make managed-agents-logs    # tail the warehouse and apac-orders

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

### Adding the MCP server

To give the agent `mcp-backend`'s MCP tools as well, start `mcp-web` with a
public URL, set `MCP_ENVIRONMENT_ID` (`make mcp-backend-setup`), and update the
agent:

```bash
docker compose run --rm --no-deps -e MCP_PUBLIC_URL=https://<host>/mcp managed-agents provision.py
```

`main.py` uses `MCP_ENVIRONMENT_ID` when it's set, because the managed-agents
environment blocks MCP egress. The agent keeps that URL, so a quick tunnel's
new hostname needs this update again.

The run prints the `trace_id` and the session's Console URL. The Console's
session viewer shows the same session with no setup, which is useful for
comparing against the trace.

## The incident: a wrong answer with nothing red

The agent can be wrong while every step of its session succeeds:

```bash
make managed-agents-incident   # drop an index on apac-orders, then run a session
make managed-agents-fix        # put the index back
```

APAC's orders aren't in the warehouse. They live in `apac-orders`, a separate
service the warehouse calls on each query. The incident is one schema change:
`migrate.py` drops the index on `order_events(order_id)`. There's no injected
delay or fake error. The query really does get slow:

1. `apac-orders` now scans `order_events` once per order and takes about 14
   seconds instead of a few tens of milliseconds.
2. The warehouse's 8 second timeout fires. Its bug: it logs the failure and
   answers **200 without APAC**, with nothing in the body saying so.
3. `query_warehouse` returns a normal result with three regions, and the agent
   reports EMEA as the fastest growing region (+21.4%). The right answer is
   APAC (+86.3%).

From the session's side this is a successful tool call with a plausible
result: `is_error` is false and the session ends normally. The Console shows
the symptom, a `query_warehouse` call of about 8 seconds where a healthy one
takes about half a second, but no error and no reason. The cause is in a
service the session knows nothing about. The trace has the whole chain:

```
anthropic.custom_tool_use query_warehouse  8.0s  OK     claude-otel-managed-agents
└─ POST                                    8.0s  200
   └─ POST /query                          8.0s  200    claude-otel-warehouse
      ├─ GET apac-orders/orders            8.0s  ERROR  httpx.ReadTimeout
      │  └─ GET /orders                    ~14s  200    claude-otel-apac-orders
      │     └─ SELECT ... NOT EXISTS       ~14s         the slow query
      └─ SELECT region, ...                2ms          ran without APAC
```

To find it in Oodle, open the `trace_id=` value the run prints and follow the
error under the green tool span. A filter on `span::anthropic.session.id` also
matches the API requests that read the session, so it can show those first.
Compare the `SELECT` with a healthy run's, where the same statement takes a few
tens of milliseconds.

The agent's MCP server goes through the tunnel. If the tunnel is down or
reconnecting when the session starts, the Console shows a red
`mcp_connection_failed_error` that has nothing to do with this incident.

The database is in the container, so anything that recreates `apac-orders`
also undoes the incident. That includes `make managed-agents`.

## The MCP incident: an error that points the wrong way

The incident above hides the failure. This one shows it, with no cause:

```bash
make managed-agents-mcp-incident   # rename a column, then run a session that needs it
make managed-agents-mcp-fix        # rename it back
```

It needs the tunnel, an agent that uses its URL (see
[Adding the MCP server](#adding-the-mcp-server)), and `MCP_TRACE_CONTEXT=true` in
`.env`, so that the tool's spans join the agent's trace (see
[Joining the agent's trace](../mcp-backend/README.md#joining-the-agents-trace)).

A migration renames `role` to `job_title` in `meta_db.org_54_employees`, and
`FirmDb.employees()` still selects `role`. There's no injected error. Only
`getEmployeeList` breaks, and the other tools still work:

1. `mcp-web` catches the SQL error and answers 500.
2. Anthropic's connector gives the agent `upstream server error (HTTP 502)`.
3. A 502 looks like a network or gateway fault, so the agent retries and then
   reports an outage. The server is up, and retrying can't help.

The Console shows the failed calls and that 502, and nothing else. The cause is
in the trace, on the failed tool call:

```
anthropic.mcp_tool_use getEmployeeList      claude-platform
└─ tools/call getEmployeeList        ERROR  claude-otel-mcp-web
   └─ SELECT ... org_54_employees    ERROR  Unknown column 'role'
```

To find it in Oodle, open the `trace_id=` value the run prints and go to a failed
`tools/call getEmployeeList`. Each MCP request reads every org's props, so a
session that retries has hundreds of spans. Filter on errors first. How often the
agent retries changes from run to run.

## Cleanup

Nothing is deleted automatically. To remove what the demo created:

```bash
ant beta:agents archive --agent-id "$MANAGED_AGENT_ID"
ant beta:environments archive --environment-id "$MANAGED_ENVIRONMENT_ID"
```
