# Codex + Oodle Observability Demo

Export [OpenAI Codex](https://openai.com/index/introducing-codex/) telemetry to
[Oodle](https://oodle.ai) using Codex's built-in OpenTelemetry support.

No custom instrumentation — this demo uses only the native `[otel]` exporter
that ships with the Codex CLI.

## Architecture

```
┌────────────────────────────────┐
│ Codex CLI / Desktop / IDE      │
│                                │
│ Built-in [otel] exporter ──────┤
└────────────────┬───────────────┘
                 │ OTLP/HTTP
                 ▼
┌────────────────────────────────┐
│  OpenTelemetry Collector       │
│  (Docker, localhost:4318)      │
│  otlphttp/oodle exporter       │
└────────────────┬───────────────┘
                 │ OTLP/HTTP + gzip
                 ▼
        ┌──────────────┐
        │    Oodle     │
        └──────────────┘
```

## Prerequisites

- **Codex CLI** ≥ 0.167.0 installed and authenticated (`codex login`)
- **Docker** (for the OTel collector)
- An **Oodle** instance with OTLP ingest

## Quick Start

```bash
# 1. Configure Oodle credentials
cp .env.example .env
# Edit .env: set OODLE_INSTANCE and OODLE_API_KEY

# 2. Start the collector
make collector

# 3. Enable Codex's built-in OTel export
make enable-codex-otel

# 4. Restart Codex (new sessions pick up the config change)

# 5. Run a task — telemetry flows automatically
make smoke-test
```

## What Codex Emits

When `[otel]` is enabled, Codex exports metrics and events via OTLP. The
signals it produces (discovered from `codex features list` and the
[advanced config docs](https://learn.chatgpt.com/docs/config-file/config-advanced)):

### Metrics (counters + duration histograms)

| Metric | Labels | Description |
|---|---|---|
| `codex.api_request` | `status`, `model` | API calls to OpenAI |
| `codex.api_request.duration_ms` | `status`, `model` | API call latency |
| `codex.tool.call` | `tool`, `kind` | Tool executions (shell, apply_patch, etc.) |
| `codex.tool.call.duration_ms` | `tool`, `kind` | Tool call latency |
| `codex.sse_event` | `status` | Server-sent event processing |
| `codex.websocket_request` | `status` | WebSocket request events |
| `codex.websocket_event` | `status` | WebSocket stream events |

### Events / log-style traces

| Event | Description |
|---|---|
| `codex.conversation_starts` | Session starts, with `auth_mode`, `model`, `app.version` |
| `codex.user_prompt` | User prompt text (only when `log_user_prompt = true`) |
| `codex.agent_response` | Agent response text (only when `log_agent_responses = true`) |
| `codex.guardian_assessment` | Guardian/approval decisions (only when `log_guardian_assessments = true`) |
| `codex.tool_decision` | Tool invocation decisions |
| `codex.tool_result` | Tool execution results |

### Default resource attributes

All signals carry: `auth_mode`, `originator`, `session_source`, `model`, `app.version`.

## Configuration

### Codex `[otel]` section (`~/.codex/config.toml`)

`make enable-codex-otel` appends this minimal config:

```toml
[otel]
environment = "demo"

[otel.exporter.otlp-http]
protocol = "binary"
endpoint = "http://localhost:4318"
```

Full options under `[otel]`:

| Key | Values | Default | Notes |
|---|---|---|---|
| `environment` | any string | `"dev"` | Sets `deployment.environment` |
| `log_user_prompt` | `true` / `false` | `false` | Capture prompt text in events |
| `log_agent_responses` | `true` / `false` | `false` | Capture response text in events |
| `log_guardian_assessments` | `true` / `false` | `false` | Capture guardian decisions |

The exporter is configured under `[otel.exporter.<transport>]` where transport is `otlp-http` or `otlp-grpc`. Each takes `protocol` (`"binary"` or `"json"`) and `endpoint`. Omit `[otel.exporter.*]` to disable export.

> **Note**: `[otel]` can only be set in the user config (`~/.codex/config.toml`),
> not in project-level configs.

### Content capture (disabled by default)

Prompts, responses, and tool content are **not recorded** unless you explicitly
enable `log_user_prompt`, `log_agent_responses`, etc. This is intentional —
workspaces may contain sensitive code.

## Sub-Agent and Tier Tracking

**Context from customer feedback**: When a Codex skill spawns sub-agents, the
main conversation's service tier (standard, fast, ultrafast) is inherited by
children. OAI confirmed that children do not currently expose their tier
independently.

What the native telemetry provides for this use case:

| Need | Available? | How |
|---|---|---|
| Identify conversations | ✅ | `session_id` on all events/metrics |
| Token usage per API call | ✅ | `codex.api_request` metric with `model` label |
| Model per call | ✅ | `model` label on metrics |
| Tool calls per turn | ✅ | `codex.tool.call` metric |
| Service tier per sub-agent | ❌ | Not exposed by Codex native OTel. The tier is set on the main conversation and inherited. |
| Parent/child turn lineage | ❌ | Native OTel does not emit `parentTurnId` / `rootTurnId`. These are only in the app-server protocol. |
| Sub-agent spawn events | ❌ | Not in native OTel. Would need app-server protocol or hooks. |

**Gap**: To get the full conversation tree with per-turn tier and parent/child
relationships, a client wrapping the app-server protocol is needed (the
`parentTurnId` / `rootTurnId` fields exist in the JSON-RPC protocol but are
not part of the native OTel export). A future version of this demo will add
that layer.

## Limitations

> **Important**: As of Codex CLI 0.167.2, the `[otel]` config section is parsed
> and validated, but the actual OTLP export pipeline is gated behind an OpenAI
> server-side feature flag. The config in this demo is correct and will activate
> when OAI enables the gate. Until then, Codex telemetry flows only to OpenAI's
> internal backend.

| Required for Agent Observability | Available? | Notes |
|---|---|---|
| OTLP export to custom endpoint | ⏳ Gated | Config accepted but export is server-side gated by OAI |
| `gen_ai.operation.name` | ❌ | Codex native spans do not set GenAI semantic conventions |
| Prompt/response content | Opt-in | Enable `log_user_prompt` / `log_agent_responses` |
| Cost per turn | ❌ | Not exposed. Use token counts × model pricing. |
| Trace context (W3C traceparent) | ❌ | Native OTel emits independent metrics/events, not linked traces |
| Per-sub-agent tier | ❌ | Inherited from parent; not exposed per child (OAI limitation) |

## Commands

| Command | Description |
|---|---|
| `make setup` | Create `.env` from template |
| `make collector` | Start the OTel collector |
| `make stop` | Stop the collector |
| `make smoke-test` | Run a one-shot Codex task against the workspace |
| `make enable-codex-otel` | Enable Codex native OTel in `~/.codex/config.toml` |
| `make clean` | Remove collector and volumes |

## Security

- Oodle credentials are in `.env` (gitignored) — never committed
- Content capture is **off by default**
- The smoke test uses `--sandbox read-only` and a disposable `workspace/`

## Troubleshooting

**No telemetry after enabling**: Restart Codex. The `[otel]` config is read at
startup — existing sessions won't pick it up.

**Collector not receiving data**: Check `docker compose logs otel-collector` and
verify health: `curl http://localhost:13133`.

**No data in Oodle**: Verify `OODLE_INSTANCE` and `OODLE_API_KEY` in `.env`.

## Supported Versions

| Component | Version |
|---|---|
| Codex CLI | ≥ 0.167.0 |
| OTel Collector | 0.114.0 (contrib) |
