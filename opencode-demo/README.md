# OpenCode Demo: sessions traced into Oodle

Runs the real [OpenCode](https://opencode.ai) CLI with the
[Langfuse OpenCode plugin](https://langfuse.com/integrations/developer-tools/opencode)
pointed at Oodle's Langfuse-compatible endpoint. This is exactly the
setup the **OpenCode** tile on the Oodle Integrations page ships:
same `opencode.json`, same environment variables.

Nothing here is simulated: OpenCode calls a real model, the plugin
rebuilds each turn from OpenCode's own events, and every attribute on
the spans is written by `@langfuse/opencode-observability-plugin`.

The demo also keeps OpenCode's **native** OTLP export as a second
profile, because it is the path most people try first and it is why
this integration uses the plugin instead. See
[The repro](#the-repro-opencodes-native-otlp-export).

## What you get in Oodle

One trace per user message, under service `opencode`:

| Span | Observation type | Carries |
|---|---|---|
| `opencode.turn` | `agent` (root) | the user message, the final reply, the agent that ran it, `session.id`, `user.id` |
| `opencode.generation` | `generation` | model, the messages sent, the reply (reasoning included), `usage_details` with input / output / reasoning / cache read / cache write, `cost_details` |
| `<tool name>` (`read`, `bash`, `task`, ...) | `tool` | the tool's arguments and its result |
| `opencode.message.user` | `event` | the prompt as sent |
| `opencode.generation.retry`, `opencode.generation.compaction` | `event` | the retry error or the compaction text |
| `opencode.generation.failed` | `generation`, status ERROR | the error of a step that did not complete |

A sub-agent (the `task` tool) runs in a session of its own, and the
plugin parents its `opencode.turn` under the parent session's step, so
it lands in the same trace with its own agent name.

- **Traces**: one per turn, with the transcript and the tool calls.
- **Sessions**: one per OpenCode session; `make ask ... CONTINUE=1`
  adds a turn to the last one.
- **Agent Graph**: the agent (`opencode.turn`, `build`, `general`,
  ...) calling its model and its tools.
- **Tokens and cost**: from the plugin's `usage_details` and
  `cost_details`. Cost is what OpenCode computed from its own model
  list; a model OpenCode does not price arrives at zero and Oodle
  prices it from its own list.

## Prerequisites

- Docker and Docker Compose
- An [Oodle](https://oodle.ai) account (instance ID + API key + API
  domain, all on the OpenCode tile)
- A [Google Gemini](https://aistudio.google.com/apikey) API key, or
  edit `docker-compose.yml` for another provider OpenCode supports

## Quick start

```bash
cp .env.example .env
# Edit .env with your Oodle credentials and Gemini key

make up
make heartbeat        # one turn, no tools
make tools            # a turn that reads a file
make ask MESSAGE="..." CONTINUE=1   # another turn in the same session
```

Every turn is a one-shot `opencode run`. The plugin flushes on
`session.idle`, before the process exits, so nothing is lost.

`workspace/` is mounted into the container as the agent's working
directory, so a turn that edits files edits it here; `git checkout
workspace` puts the fixtures back.

## The setup, piece by piece

`opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "experimental": {
    "openTelemetry": true
  },
  "plugin": ["@langfuse/opencode-observability-plugin@latest"]
}
```

OpenCode installs the plugin from npm on its first start. Keep
`experimental.openTelemetry` on: it is the plugin's documented setup
and the plugin warns `[Tracing disabled]` without it.

The credentials, as environment variables (`docker-compose.yml`):

```bash
LANGFUSE_BASE_URL=https://<API_DOMAIN>/v1/api/instance/<OODLE_INSTANCE>/langfuse
LANGFUSE_PUBLIC_KEY=default
LANGFUSE_SECRET_KEY=<OODLE_API_KEY>
LANGFUSE_SERVICE_NAME=opencode
LANGFUSE_ENVIRONMENT=development
LANGFUSE_USER_ID=demo-user
```

The public key is always `default`; the secret key is the Oodle API
key. `LANGFUSE_SERVICE_NAME` is where the traces are filed (without it:
`unknown_service:opencode`). `LANGFUSE_USER_ID` is what the Users page
groups on. The plugin also reads
`~/.config/opencode/opencode-langfuse.json` with the same fields
(`publicKey`, `secretKey`, `baseUrl`, `serviceName`, `environment`,
`userId`) when the two key variables are not set.

## Verifying in Oodle

1. **Agent Observability > Traces**, filter service `opencode`. Each
   `make ask` is one trace.
2. Open one. **Transcript** shows the prompt and the reply; the tree
   shows `opencode.generation` per model step with model, tokens and
   cost, and one span per tool call named after the tool.
3. **Sessions** lists the session; turns sent with `CONTINUE=1` are
   inside it.
4. **Agent Graph** draws `opencode.turn` calling `chat` calling the
   tools, and `general` under the `task` tool when a sub-agent ran.

```bash
make logs   # OpenCode's log: "OTEL tracing initialized -> <base url>" means the plugin is on
```

## The repro: OpenCode's native OTLP export

OpenCode can export its own spans when `experimental.openTelemetry`
is on and `OTEL_EXPORTER_OTLP_ENDPOINT` is set. The `native` profile
runs that through a collector whose debug exporter prints every span:

```bash
make native-up
make native-ask MESSAGE="Use the read tool to read /workspace/hello.txt, then reply with the secret word in uppercase."
make native-spans
make native-down
```

What one turn produces on OpenCode 1.18.31:

- **~1,000 spans**, nearly all Effect-runtime internals (`sql.execute`,
  `Config.get`, `Plugin.load`, `ToolRegistry.register`, ...), and
  **7 AI SDK spans**: `ai.streamText` / `ai.streamText.doStream` for
  each model step *and* for the session-title generation.
- All of them, across every turn and every session, in **one trace**
  whose root (`SessionHttpApi.prompt`'s ancestor) never ends and never
  arrives.
- **No tool-call span.** OpenCode runs tools outside the AI SDK, so the
  `read` above leaves no trace.
- The session id only on `session.id` / `ai.telemetry.metadata.sessionId`.
- `make native-ask` attaches to a long-lived `opencode serve` on
  purpose: a one-shot `opencode run` exits before the batch processor
  flushes, and only full 512-span batches leave. The model calls are
  in the remainder.

The AI SDK spans themselves are the AI SDK 6 `ai.*` shape, which Oodle
resolves (transcript, tokens, model), so the numbers are right. It is
the structure that is not usable, which is what the plugin fixes.

## Troubleshooting

- No trace: `make logs`. The plugin logs `OTEL tracing initialized`
  when it started and `Missing langfuse credentials` when it did not
  find both keys.
- Empty reply from the model: `gemini-2.5-flash` returned empty
  replies on tool-calling turns during this demo's development;
  `OPENCODE_MODEL` defaults to `google/gemini-2.5-pro`.
- Traces under `unknown_service:opencode`: `LANGFUSE_SERVICE_NAME` is
  not reaching the container.
