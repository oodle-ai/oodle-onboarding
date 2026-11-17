# Codex + Oodle Observability Demo

Export [OpenAI Codex](https://openai.com/index/introducing-codex/) telemetry to
[Oodle](https://oodle.ai) via an instrumented app-server client.

## Architecture

```
┌────────────────────────────────────────────┐
│  client/index.mjs  (instrumented wrapper)  │
│                                            │
│  spawns ──► codex app-server (stdio)       │
│  intercepts JSON-RPC notifications         │
│  creates OTel spans for turns / items      │
└────────────────────┬───────────────────────┘
                     │ OTLP/HTTP
                     ▼
┌────────────────────────────────────────────┐
│  OpenTelemetry Collector                   │
│  (Docker, localhost:4318)                  │
│  otlphttp/oodle exporter                   │
└────────────────────┬───────────────────────┘
                     │ OTLP/HTTP + gzip
                     ▼
              ┌──────────────┐
              │    Oodle     │
              └──────────────┘
```

The client wraps the [Codex app-server protocol](https://learn.chatgpt.com/docs/app-server)
(JSON-RPC 2.0 over stdio). It intercepts lifecycle notifications
(`turn/started`, `item/completed`, `thread/tokenUsage/updated`, etc.)
and creates OTel spans — no server-side feature gate required.

## Prerequisites

- **Codex CLI** installed and authenticated (`codex login`)
- **Node.js** >= 18 (for the client)
- **Docker** (for the OTel collector)
- An **Oodle** instance with OTLP ingest

## Quick Start

```bash
# 1. Configure Oodle credentials
cp .env.example .env
# Edit .env: set OODLE_INSTANCE and OODLE_API_KEY

# 2. Start the collector
make collector

# 3. Install client dependencies
make install-client

# 4. Run a prompt — traces flow to Oodle
make client-test

# Or with a custom prompt:
cd client && node index.mjs "Explain the architecture of this repo"
```

## What Gets Traced

The client creates a span tree for each Codex session:

```
codex.session                                   # root span for the entire run
  └── codex.thread                              # session lifecycle
        └── codex.turn                          # one user prompt → agent response cycle
              ├── codex.item.userMessage        # the prompt
              ├── codex.item.reasoning          # model reasoning step
              ├── codex.item.agentMessage       # agent's response text
              ├── codex.item.commandExecution   # tool call (shell, apply_patch, etc.)
              │     attributes: command, exit_code, duration_ms
              ├── codex.item.fileChange         # file modifications
              │     attributes: paths, status
              ├── codex.item.mcpToolCall        # MCP server tool invocations
              │     attributes: server, tool, status
              ├── codex.item.subAgentActivity   # sub-agent lifecycle events
              │     attributes: kind, path, model
              └── codex.item.agentMessage       # agent's final response
```

### Span Attributes

| Attribute | Description |
|---|---|
| `codex.thread.id` | Session/conversation ID |
| `codex.turn.id` | Turn ID within the session |
| `codex.turn.status` | `completed`, `interrupted`, or `failed` |
| `codex.model` | Model used (e.g. `gpt-6-astra`) |
| `codex.item.type` | `userMessage`, `agentMessage`, `commandExecution`, `fileChange`, `mcpToolCall`, `subAgentActivity`, `reasoning` |
| `codex.command` | Shell command executed |
| `codex.command.exit_code` | Command exit code |
| `codex.tokens.input` | Input tokens consumed |
| `codex.tokens.output` | Output tokens produced |
| `codex.tokens.cached_input` | Cached input tokens |
| `codex.command.duration_ms` | Command execution duration |
| `codex.mcp.server` | MCP server name |
| `codex.mcp.tool` | MCP tool name |
| `codex.sub_agent.kind` | `started`, `interacted`, `interrupted`, `completed` |
| `codex.turn.duration_ms` | Turn wall-clock duration |

## Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CODEX_MODEL` | `gpt-6-astra` | Model to use |
| `CODEX_CWD` | current directory | Working directory for the agent |
| `CODEX_SANDBOX` | `read-only` | Sandbox mode (`read-only`, `workspace-write`, `danger-full-access`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | OTLP HTTP endpoint |

### Approval Policy

The demo client auto-approves all tool calls (`approvalPolicy: "never"`).
For production use, implement proper approval handling by responding to
`item/commandExecution/requestApproval` and `item/fileChange/requestApproval`
server requests in the JSON-RPC stream.

## Native OTel Export (Optional)

Codex also has built-in OTel export via `config.toml`. Run `make enable-codex-otel`
to configure it. This requires the Codex desktop app to be restarted.

```toml
[otel]
environment = "demo"

[otel.trace_exporter.otlp-http]
protocol = "binary"
endpoint = "http://localhost:4318"

[otel.metrics_exporter.otlp-http]
protocol = "binary"
endpoint = "http://localhost:4318"
```

> **Note**: Native export availability may vary by account. The app-server
> client approach works regardless.

## Commands

| Command | Description |
|---|---|
| `make setup` | Create `.env` from template |
| `make collector` | Start the OTel collector |
| `make stop` | Stop the collector |
| `make install-client` | Install client Node.js dependencies |
| `make client-test` | Run the instrumented client with a test prompt |
| `make smoke-test` | Run a one-shot `codex exec` (no instrumentation) |
| `make enable-codex-otel` | Enable native OTel in `~/.codex/config.toml` |
| `make clean` | Remove collector and volumes |

## Security

- Oodle credentials are in `.env` (gitignored) — never committed
- The client auto-approves tool calls for demo purposes only
- The smoke test uses a disposable `workspace/` directory
