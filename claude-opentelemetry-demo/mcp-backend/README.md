# MCP backend (a production-shaped app around Managed Agents)

A copy of how a real proposal-writing backend uses Claude Managed Agents,
with its tracing gaps kept **on purpose**. Use it to reproduce, on an
instance you control, the traces such a customer sends, and to test
Oodle-side fixes against them.

The app is an AEC (architecture, engineering, construction) proposal tool.
A user asks for a go/no-go plan on a bid. The backend starts an agent
session. The agent reads the firm's data through the firm's own MCP server
and writes the plan in its sandbox.

```
run.py ──► mcp-app (claude-otel-mcp-app) ──── Sessions API ────► Anthropic
             │  create agent, session,                              │
             │  mount files, send task,                             │ MCP connector
             │  poll until done                                     │ (Claude-User)
             │                                                      ▼
             └─ in-house chat ── JSON-RPC ──► mcp-web ◄── tunnel ◄──┘
                                            (claude-otel-mcp-web)
                                             POST /mcp, SQLite
```

| Service | Plays the part of | Tracing |
|---|---|---|
| `mcp-app` | The backend that starts and polls sessions, and the in-house chat | `opentelemetry-instrument` (zero-code) + the Claude SDK's spans |
| `mcp-web` | The web tier that serves the firm's MCP server | `opentelemetry-instrument` (zero-code), nothing by hand |
| `mcp-tunnel` | The public hostname | cloudflared quick tunnel, not traced |
| `claude-platform` | The agent's turns, model requests and tool calls | API tracing ([destination](../README.md#api-tracing-destination)) |

## The gaps it keeps

Each one is deliberate. Don't "fix" them here. They are what this
sub-demo is for.

| Gap | Where | What you see in Oodle |
|---|---|---|
| MCP server spans are bare `POST /mcp` | `web.py` | No JSON-RPC method, tool name, MCP session id or request id. Nothing joins a server span to the agent's `anthropic.mcp_tool_use` span |
| Failed MCP requests answer 500 from a caught exception | `web.py` | `http.response.status_code=500`, no exception event, no cause |
| Every MCP request reads each org's props table | `web.py` | One `SELECT` per org (60) under every `POST /mcp` |
| One agent per session, named `<org>_<random>_<timestamp>_<email>` | `app.py` | Every run is a new "agent" in the agent graph; the email is in the agent name; no `user.id` |
| MCP server name is new per session (`mcp-ShortId__<id>`) | `app.py` | `anthropic.mcp.server.name` can't group runs by server |
| The in-house chat calls MCP over raw JSON-RPC | `app.py` | Bare `POST` client spans and no `execute_tool` span, so Oodle counts zero tool calls on that path |
| The session is polled, not streamed | `app.py` | Many `anthropic.sessions.retrieve` / `events.list` spans in the session's trace |

Some gaps come from Anthropic's side and show up on their own: tool output
is in `anthropic.tool_result.content`, not `gen_ai.tool.call.result`;
`anthropic.model_request` spans carry no agent name; and `claude-platform`
spans have no environment, so Oodle files them under `unset`.

## Run

```bash
make mcp-backend-setup   # once: prints MCP_ENVIRONMENT_ID, paste it into ../.env
make mcp-backend         # start the servers and the tunnel, then run one scenario
make mcp-backend-logs    # tail mcp-app, mcp-web and the tunnel
make down                # stop everything, the tunnel too
```

`run.py` prints the agent's name, the session id, the tunnel's MCP URL, and
a `trace_id` for each of the two scenarios:

1. **go/no-go session**: `POST /api/managedagents/rfpgonogo/create`, then
   the poller in the same trace until the agent is idle. The agent is
   archived when the session ends, so runs don't pile up agents.
2. **in-house chat**: `POST /api/chatsession/ask`, a Messages API tool loop
   that calls the MCP server directly.

`make mcp-backend-setup` creates its own environment: the managed-agents
sub-demo's environment has MCP egress off (`allow_mcp_servers`), and a
session there fails with `mcp_egress_blocked_error`.

### The tunnel

Anthropic's MCP connector calls the agent's MCP server from Anthropic's
network, so `mcp-web` needs a public HTTPS URL. `mcp-tunnel` opens a
cloudflared quick tunnel: no account, a new `*.trycloudflare.com` hostname
each time it starts, and the server is reachable from the internet while it
runs. The MCP server has no authentication and serves only the seeded demo
data. Stop it with `make down` when you're done.

To use a URL of your own instead (ngrok, a deployed host), set
`MCP_PUBLIC_URL=https://<host>/mcp` in `../.env`.

## Cost

One go/no-go run is a full agent session on `CLAUDE_MODEL` with a few dozen
model requests. The chat path and the MCP server's search step use
`CHAT_MODEL` / `SEARCH_MODEL` (Haiku by default).
