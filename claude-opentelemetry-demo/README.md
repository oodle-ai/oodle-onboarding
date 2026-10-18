# Claude OpenTelemetry Demo

Claude's built-in OpenTelemetry tracing, sent to Oodle. Four sub-demos
share one `.env`:

| Sub-demo | What it calls | Where its spans come from |
|---|---|---|
| [messages-api](./messages-api) | `POST /v1/messages` with plain `httpx`, no SDK | **API tracing**: Anthropic sends them |
| [claude-sdk](./claude-sdk) | The Python SDK: create, stream, tool runner, count tokens, a conversation | **SDK tracing**: the app sends them, plus API tracing when it's on |
| [managed-agents](./managed-agents) | A Claude Managed Agents session that queries a custom tool's Python service and runs code in its sandbox | **Both**: the SDK sends the request spans, and Anthropic sends the turns and sandbox tools. The custom tool's service is traced by OpenTelemetry zero-code auto-instrumentation, in the same trace |
| [mcp-backend](./mcp-backend) | A production-shaped backend: one agent per session that reads the firm's data through the app's own MCP server, plus an in-house chat that calls the same server | **API tracing**, plus the OpenTelemetry Java agent on a Spring Boot backend and MCP server (no Claude SDK). Keeps a real customer's tracing gaps on purpose |

The first three use no third-party instrumentation for Claude itself
(managed-agents' warehouse service uses OpenTelemetry's FastAPI and sqlite3
auto-instrumentation). The spans follow the
OpenTelemetry GenAI conventions (`gen_ai.*`). mcp-backend adds the
OpenTelemetry Java agent, the way the production app it copies has it.

## Two sources of spans

Claude has two independent ways of emitting spans. Each works on its own.
With both on, they form one trace.

| | SDK tracing | API tracing |
|---|---|---|
| Emitted by | The Claude SDK, in your process | Anthropic's API, server side |
| Setup | Register a tracer provider before the first call | An org admin adds an OTLP destination (here, Oodle) |
| Exported through | Your OTel pipeline (this demo's collector) | Directly from Anthropic to Oodle's OTLP endpoint |
| `service.name` | Yours (`claude-otel-*`) | `claude-platform` |
| Span kind | `CLIENT` | `SERVER` |
| Covers | Every SDK request, the tool runner, your custom tools | Messages and Sessions requests from any client |
| Model requests inside one call | No | `anthropic.model_request` |
| Server tools (web search, code execution) | No | `anthropic.tool_use <tool>` |
| Managed Agents turns and sandbox tools | No | `anthropic.session.turn`, `anthropic.tool_use <tool>` |

The two are joined by the W3C `traceparent` header. The SDK sends it
automatically, and the Messages API demo injects it by hand. When Anthropic
gets a request with that header, it makes its `SERVER` span a child of the
caller's span. The client span and the server span of one request have the
same name (`anthropic.messages.create`). Tell them apart by kind or by
`service.name`.

```
demo.tool_runner                               claude-otel-sdk
└─ anthropic.messages.tool_runner              claude-otel-sdk
   ├─ anthropic.messages.create  [CLIENT]      claude-otel-sdk
   │  └─ anthropic.messages.create  [SERVER]   claude-platform    (API tracing)
   │     └─ anthropic.model_request            claude-platform
   ├─ anthropic.custom_tool_use get_weather    claude-otel-sdk
   │  └─ weather.lookup                        claude-otel-sdk
   └─ anthropic.messages.create  [CLIENT]      claude-otel-sdk
      └─ anthropic.messages.create  [SERVER]   claude-platform
         └─ anthropic.model_request            claude-platform
```

## Architecture

```
                 ┌───────────── SDK tracing (OTLP) ──────────────┐
claude-sdk ──────┤                                                ▼
managed-agents ──┤                        OTel Collector (:4318) ──► Oodle
messages-api ────┘                                                ▲
      │ HTTPS + traceparent                                       │
      ▼                                                           │
api.anthropic.com ─────── API tracing (OTLP/HTTP, server side) ───┘
```

mcp-backend's two servers send their spans through the same collector. Its
[README](./mcp-backend/README.md) has its own diagram.

## Prerequisites

- Docker and Docker Compose
- An [Oodle](https://oodle.ai) account (instance ID and API key)
- An [Anthropic API key](https://platform.claude.com/settings/keys)
- For API tracing, an organization **admin** (or owner) to add the destination once,
  plus the [`ant` CLI](https://docs.claude.com/en/api/sdks/cli) (`brew install anthropics/tap/ant`) and `jq`.
  Without one, only the SDK half of the demo works.

## Quick start

```bash
cp .env.example .env          # fill in the Oodle and Anthropic values
make help

make up                       # start the collector
make sdk                      # works right away: SDK tracing only

make destination-create       # once, as an org admin: add Oodle as an API tracing destination
make destination-list         # wait for last_success_at to be set
make messages-api             # spans arrive from Anthropic's side

make managed-agents-setup     # once: create the agent and environment, paste the ids into .env
make managed-agents

make mcp-backend-setup        # once: an environment that allows MCP egress, paste the id into .env
make mcp-backend              # opens a public quick tunnel to the demo MCP server while it runs
```

Each run prints a `trace_id` for every scenario, which you can use to look
the trace up in Oodle. The collector also prints each span it forwards
(`make logs-collector`).

## Shared variables (`.env`)

| Variable | Used by | Meaning |
|---|---|---|
| `OODLE_INSTANCE`, `OODLE_API_KEY` | collector, destination script | Where spans go |
| `ANTHROPIC_API_KEY` | all sub-demos | Anthropic credentials |
| `CLAUDE_MODEL` | all sub-demos | Defaults to `claude-opus-5-5` |
| `ANTHROPIC_WORKSPACE_ID` | all sub-demos | Sent as `anthropic-workspace-id`. Required when the API key isn't scoped to a workspace. The destination must cover this workspace |
| `ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE` | claude-sdk, managed-agents | `metadata_only` (the SDK default) or `content` (prompts and responses on spans). The SDK reads it directly |
| `DESTINATION_CONTENT_MODE` | destination script | The same choice, for the spans Anthropic sends |
| `DESTINATION_WORKSPACES` | destination script | `all`, or comma-separated `wrkspc_...` ids |
| `MANAGED_AGENT_ID`, `MANAGED_ENVIRONMENT_ID` | managed-agents | Printed by `make managed-agents-setup` |
| `MCP_ENVIRONMENT_ID` | mcp-backend | Printed by `make mcp-backend-setup` |
| `MCP_PUBLIC_URL` | mcp-backend | Optional. Your own public URL for the MCP server, instead of the quick tunnel |
| `CHAT_MODEL`, `SEARCH_MODEL` | mcp-backend | Models of the in-house chat and of the MCP server's search step. Default `claude-haiku-4-5` |

## API tracing destination

Adding a destination makes Anthropic send traces of the **whole
organization's** Claude Platform activity (in the workspaces it covers) to
Oodle. Once delivered, the data is held under Oodle's retention and access
controls.

The destination settings:

| Field | Value |
|---|---|
| Endpoint URL | `https://<OODLE_INSTANCE>-otlp.collector.oodle.ai` (base URL, without `/v1/traces`: Anthropic appends it) |
| Headers | `X-OODLE-INSTANCE: <OODLE_INSTANCE>`, `X-API-KEY: <OODLE_API_KEY>` |
| Maximum content size | `750000` bytes |
| Content mode | `metadata_only` or `content` |

### With the script

```bash
ant auth login --profile admin --scope "org:admin"   # once; approve in the browser
make destination-create
make destination-list
ant auth logout --profile admin                      # when done
```

`scripts/create-destination.sh` shows the organization, endpoint, content
mode and workspaces, and asks before creating anything. It reads the Oodle
key from `.env` into the request body, so the key never appears on a
command line. Anthropic never returns header values; reads list only
`header_names`.

### In the Console

Go to **Settings → OpenTelemetry**
(`https://platform.claude.com/settings/telemetry-destinations`) → **Add
destination** → **Custom**, and enter the values above. The **Delivery**
column shows **Healthy** once spans arrive.

### Content mode

`content` adds prompts and responses to the spans. It's needed to read
conversations in Oodle, but Oodle then stores that text. Images and
documents are exported as their type only. For organizations with a
HIPAA, FERPA or K-12 arrangement with Anthropic, destinations export
metadata only whatever this is set to.

## Verifying in Oodle

- `service.name = claude-otel-sdk`: `anthropic.messages.create`,
  `anthropic.messages.tool_runner`, `anthropic.custom_tool_use get_weather`,
  `anthropic.messages.count_tokens`.
- `service.name = claude-otel-warehouse`: the managed-agents custom tool's
  service (`POST /query`, `SELECT`), in the session's trace under
  `anthropic.custom_tool_use query_warehouse`.
- `service.name = claude-platform`: Anthropic's spans. Each one shares a
  trace ID with the app span whose `traceparent` it received.
- For token counts, sum `gen_ai.usage.*` on `anthropic.model_request` spans when
  API tracing is on, or on the SDK's `anthropic.messages.create` spans when it's
  off. Don't add the two together, or each token is counted twice.
- With both sources on, Oodle's GenAI view currently counts an SDK request
  twice: once for the SDK's `CLIENT` span and once for Anthropic's `SERVER`
  span (generations, tokens and cost all doubled; reported to Oodle). Until
  that's fixed, read totals with the GenAI view filtered to
  `service.name = claude-platform`. Messages API and Managed Agents traces
  aren't affected: their only `chat` spans come from Anthropic.

## Troubleshooting

| Symptom | Check |
|---|---|
| `400 ... must include the anthropic-workspace-id header` | The API key isn't scoped to a workspace. Set `ANTHROPIC_WORKSPACE_ID` in `.env` |
| No SDK spans | The collector is up (`make up`); the tracer provider is registered before the first call; `ANTHROPIC_OPEN_TELEMETRY` is not `false` |
| No `claude-platform` spans | `make destination-list`: the destination must be `enabled` and cover the workspace of `ANTHROPIC_API_KEY`. Allow about a minute after creating it |
| Destination `Failing` with 401/403 | Wrong `X-API-KEY` / `X-OODLE-INSTANCE` |
| API spans in their own traces | The request had no `traceparent`, or its sampled flag was off |
| Each request appears twice | That's the `CLIENT` span and the `SERVER` span of the same request (see above). If a third-party Anthropic instrumentor is also installed, set `ANTHROPIC_OPEN_TELEMETRY=false` |

OpenTelemetry export from Claude is in beta. Span names and attributes can
change, so `anthropic` is pinned to an exact version in each
`requirements.txt`. Bump it on purpose.
