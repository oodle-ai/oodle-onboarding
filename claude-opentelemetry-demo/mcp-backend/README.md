# MCP backend (a production-shaped Java app around Managed Agents)

A copy of how a real proposal-writing backend uses Claude Managed Agents,
with its tracing gaps kept **on purpose**. Use it to reproduce, on an
instance you control, the traces such a customer sends, and to test
Oodle-side fixes against them.

The app is an AEC (architecture, engineering, construction) proposal tool.
A user asks for a go/no-go plan on a bid. The backend starts an agent
session. The agent reads the firm's data through the firm's own MCP server
and writes the plan in its sandbox.

It copies the reference backend's stack, because the spans come from that
stack: Java 21, Spring Boot, the OpenTelemetry Java agent (2.32.0), MariaDB
over JDBC, OkHttp for the Claude API, `java.net.http` for its own MCP
calls, and a hand-traced model wrapper.

```
driver ──► mcp-app (claude-otel-mcp-app) ──── Claude API (OkHttp) ──► Anthropic
             │  create agent, session,                                  │
             │  mount files, send task,                                 │ MCP connector
             │  poll until done                                         │ (Claude-User)
             │                                                          ▼
             └─ in-house chat ── JSON-RPC ──► mcp-web ◄──── tunnel ◄────┘
                (java.net.http)             (claude-otel-mcp-web)
                                             POST /mcp ──► MariaDB
```

| Service | Plays the part of | Tracing |
|---|---|---|
| `mcp-app` | The backend that starts and polls sessions, and the in-house chat | Java agent, plus the hand-traced model wrapper |
| `mcp-web` | The web tier that serves the firm's MCP server | Java agent only |
| `mcp-mariadb` | The firm database (`fed_db`, `meta_db`, `conv_db`) | Seeded by `db/init.sql`, so seeding adds no spans |
| `mcp-tunnel` | The public hostname | cloudflared quick tunnel, not traced |
| `claude-platform` | The agent's turns, model requests and tool calls | API tracing ([destination](../README.md#api-tracing-destination)) |

The Claude API is called over plain OkHttp, with no Claude SDK. So the
backend's own spans for those calls are bare okhttp `GET`/`POST` client
spans, and every `anthropic.*` span comes from Anthropic's API tracing.

## The gaps it keeps

Each one is deliberate. Don't "fix" them here. They are what this
sub-demo is for.

| Gap | Where | What you see in Oodle |
|---|---|---|
| MCP server spans are bare `POST /mcp` | `McpController` | No JSON-RPC method, tool name, MCP session id or request id. Nothing joins a server span to the agent's `anthropic.mcp_tool_use` span |
| Failed MCP requests answer 500 from a caught exception | `McpController` | `http.response.status_code=500`, no exception event, no cause |
| Every MCP request reads each org's props table | `FirmDb` | `SELECT fed_db.actors_list`, `SELECT fed_db.orgs_list`, then one `SELECT meta_db.org_<n>_props` per org (60) under every `POST /mcp` |
| One agent per session, named `<org>_<random>_<timestamp>_<email>` | `ManagedAgentsController` | Every run is a new "agent" in the agent graph; the email is in the agent name; no `user.id` |
| MCP server name is new per session (`mcp-ShortId__<id>`) | `ManagedAgentsController` | `anthropic.mcp.server.name` can't group runs by server |
| The session is polled, not streamed | `ManagedAgentsController` | okhttp `GET`s and `INSERT conv_db.c_54_facet` every few seconds, in the session's trace |
| The model wrapper records no prompt, response, agent or conversation | `GenAi` | `chat <model>` spans with tokens only, not tied to any agent |
| The in-house chat calls MCP over raw JSON-RPC | `ChatController` | A bare `POST` client span (`Java-http-client`) and no `execute_tool` span, so Oodle counts zero tool calls on that path |

Some gaps come from Anthropic's side and show up on their own: tool output
is in `anthropic.tool_result.content`, not `gen_ai.tool.call.result`;
`anthropic.model_request` spans carry no agent name; and `claude-platform`
spans have no environment, so Oodle files them under `unset`.

## Run

```bash
make mcp-backend-setup   # once: prints MCP_ENVIRONMENT_ID, paste it into ../.env
make mcp-backend         # start MariaDB, the servers and the tunnel, then run one scenario
make mcp-backend-logs    # tail mcp-app, mcp-web and the tunnel
make down                # stop everything, the tunnel too
```

The first build downloads the Maven dependencies and takes a few minutes.

The driver prints the agent's name, the session id, the tunnel's MCP URL,
and a `trace_id` for each of the two scenarios:

1. **go/no-go session**: `POST /api/managedagents/rfpgonogo/create`, then
   the poller in the same trace until the agent is idle. The agent is
   archived when the session ends, so runs don't pile up agents.
2. **in-house chat**: `POST /api/chatsession/ask`, a Messages API tool loop
   on the model wrapper that calls the MCP server directly.

`make mcp-backend-setup` creates its own environment: the managed-agents
sub-demo's environment has MCP egress off (`allow_mcp_servers`), and a
session there fails with `mcp_egress_blocked_error`.

One jar plays every part. `DEMO_ROLE` picks it: `web`, `app`, `driver` or
`provision`. Compose turns on the Java agent (`JAVA_TOOL_OPTIONS`) for the
two servers only.

### The tunnel

Anthropic's MCP connector calls the agent's MCP server from Anthropic's
network, so `mcp-web` needs a public HTTPS URL. `mcp-tunnel` opens a
cloudflared quick tunnel: no account, a new `*.trycloudflare.com` hostname
each time it starts, and the server is reachable from the internet while it
runs. The MCP server has no authentication and serves only the seeded demo
data. Stop it with `make down` when you're done.

To use a URL of your own instead (ngrok, a deployed host), set
`MCP_PUBLIC_URL=https://<host>/mcp` in `../.env`.

## Fixes to try

Two switches, both off by default so the gaps above stay. Together they
are the fix a backend like the reference one can make on its own side.

```bash
MCP_TRACE_CONTEXT_IN_URL=true MCP_SERVER_SPAN_ATTRIBUTES=true make mcp-backend
```

### The session's trace context in the MCP URL (`MCP_TRACE_CONTEXT_IN_URL`)

With it on, the MCP server's spans join the session's trace, under the
`POST /api/managedagents/rfpgonogo/create` span, instead of the
connector's own trace.

Why it is needed: Anthropic's MCP connector sends the MCP server a
`traceparent` from its own connection trace, not from the session. The
server span then has a remote parent that is never exported, and nothing
joins it to the agent's `anthropic.mcp_tool_use` span.

How it works, in two parts that a backend like the reference one can copy:

1. **The app** (`ManagedAgentsController.withTraceContext`) adds the create
   request's traceparent to the MCP URL as `?tp=…` when it makes the agent.
   This works because the agent is made for one session.
2. **The MCP server** loads a small Java agent extension
   (`propagator/`, `-Dotel.javaagent.extensions`). It registers an `mcpurl`
   propagator that reads `tp` from the query string. It is listed last in
   `OTEL_PROPAGATORS=tracecontext,baggage,mcpurl`, so `tp` replaces the
   connector's parent. A request without `tp` keeps the header's parent.

Limits:

- The server spans become children of the create request, not of the
  tool call that caused them: the URL is fixed before any tool runs. The
  next switch names each call, so the calls can be told apart.
- The URL holds a trace id and a span id, and Anthropic stores it with the
  agent. Neither is a secret.
- It needs an agent per session. A shared agent has one URL for all
  sessions.

### Named calls on the server span (`MCP_SERVER_SPAN_ATTRIBUTES`)

With it on, each `POST /mcp` span carries the JSON-RPC call, in the MCP
semantic conventions: `mcp.method.name`, `jsonrpc.request.id`,
`mcp.session.id` (when the request has an `Mcp-Session-Id` header) and,
for `tools/call`, `gen_ai.tool.name`.

Without them, every request is a bare `POST /mcp`. With them, the
connector's requests read as they are:

| Request | `mcp.method.name` |
|---|---|
| A probe before the handshake; this server answers it with "method not found" | `server/discover` |
| The handshake | `initialize`, `notifications/initialized`, `tools/list` |
| One per tool the agent calls | `tools/call`, with `gen_ai.tool.name` |

Within one session trace, the tool name and the time pair each server
span with the agent's `anthropic.mcp_tool_use` span.

## Cost

One go/no-go run is a full agent session on `CLAUDE_MODEL` with a few dozen
model requests. The chat path and the MCP server's model calls use
`CHAT_MODEL` / `SEARCH_MODEL` (Haiku by default).
