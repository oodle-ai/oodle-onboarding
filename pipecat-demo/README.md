# Pipecat dual-write demo — Langfuse + Oodle

A [Pipecat](https://docs.pipecat.ai) voice agent whose traces land in
**both** Langfuse and Oodle, written two ways:

| `TRACING_BACKEND` | Path | File |
| --- | --- | --- |
| `otel` (default) | Two plain OpenTelemetry OTLP exporters on Pipecat's tracer provider | [`app/tracing_otel.py`](app/tracing_otel.py) |
| `langfuse-sdk` | The Langfuse Python SDK, with Oodle as a second Langfuse destination | [`app/tracing_langfuse.py`](app/tracing_langfuse.py) |

Both paths produce the same span tree in both backends. They are kept
apart because they are genuinely different: the first is
[Pipecat's documented OpenTelemetry setup](https://docs.pipecat.ai/api-reference/server/utilities/opentelemetry)
with a second exporter bolted on, and the second runs the spans through
the Langfuse SDK's own span processor, which is what you need if the app
already uses a Langfuse client for anything else.

Speech-to-text, the chat model and text-to-speech are all OpenAI and
voice activity detection runs locally, so the demo needs one API key and
no third-party voice vendor account.

## The trace

One browser session produces one trace per conversation:

```
conversation          conversation.id, conversation.type, gen_ai.agent.name
└── turn              turn.number, turn.duration_seconds, turn.was_interrupted
    ├── stt           gen_ai.provider.name, transcript, language, metrics.ttfb
    ├── llm           gen_ai.request.model, input/output, gen_ai.usage.*
    └── tts           gen_ai.request.model, voice_id, text, metrics.ttfb
```

`conversation` and `turn` come from Pipecat's turn-trace observer
(instrumentation scope `pipecat.turn`); `stt`, `llm` and `tts` come from
the service decorators (scope `pipecat`). `PipelineParams(enable_metrics=True,
enable_usage_metrics=True)` is what puts `metrics.ttfb` on the service
spans and the token counts on the LLM span.

Two things about that tree surprise a backend reading it, one of which
[`bot.py`](app/bot.py) corrects — see
[What a backend sees](#what-a-backend-sees).

## Quick start

```bash
cp .env.example .env
# Edit .env: your Langfuse keys, your Oodle instance, your OpenAI key.
make up
```

Then open <http://localhost:7860>, allow the microphone and talk to the
bot. It introduces itself as soon as you connect.

Open the same session in both backends:

- **Langfuse** — your project → Traces
- **Oodle** — Agent Observability → Traces, filtered on service
  `pipecat-demo`

To take the other path, `make up-langfuse`. Nothing else changes: same
pipeline, same span tree, same two destinations.

## Path one: plain OpenTelemetry (`TRACING_BACKEND=otel`)

Pipecat's tracing *is* OpenTelemetry. `setup_tracing()` builds a
`TracerProvider`, registers it as the process-wide one, and wraps the one
exporter it is given in a `BatchSpanProcessor`. Dual-writing is therefore
a second span processor on the same provider:

```python
setup_tracing(service_name="pipecat-demo", exporter=oodle_exporter)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(langfuse_exporter))
```

```
conversation ─┬─► Oodle      https://<instance>-otlp.collector.oodle.ai/v1/traces
└── turn      │              X-API-KEY, X-OODLE-INSTANCE
    ├── stt   │
    ├── llm   └─► Langfuse   <LANGFUSE_BASE_URL>/api/public/otel/v1/traces
    └── tts                  Authorization: Basic <public key>:<secret key>
```

Oodle's exporter is the one handed to `setup_tracing()` so that Pipecat
owns the resource and the service name. Langfuse's is added afterwards.
There is no collector in between and nothing in this path is
Langfuse-specific — its OTLP endpoint is addressed like any other OTLP
backend.

## Path two: the Langfuse SDK (`TRACING_BACKEND=langfuse-sdk`)

Take this path when the app already uses the Langfuse SDK for scores,
prompt links or `update_current_trace`, because those only exist on a
Langfuse client. Oodle then arrives as a second destination for the
client the app already has.

```python
setup_tracing(service_name="pipecat-demo", exporter=None)   # provider only
provider = trace.get_tracer_provider()

Langfuse(tracer_provider=provider, should_export_span=...)   # leg one
provider.add_span_processor(LangfuseSpanProcessor(...))      # leg two → Oodle
```

```
conversation ─┬─► Langfuse   <LANGFUSE_BASE_URL>/api/public/otel/v1/traces
└── turn      │              pk-lf-… / sk-lf-…
    ├── stt   │
    ├── llm   └─► Oodle      https://<domain>/v1/api/instance/<id>/langfuse/…
    └── tts                  default / <OODLE_API_KEY>
```

Three things make this path work.

**Pipecat keeps the tracer provider.** `setup_tracing()` runs first and
the client is handed the provider it registered. `Langfuse()` would pick
up an already-registered provider by itself — but only if it is
constructed second. Constructed first, it registers one of its own,
`setup_tracing()` then declines to replace it (OpenTelemetry allows one
provider per process and logs `Overriding of current TracerProvider is
not allowed`), and every span ends up on a resource with no
`service.name`. Passing the provider makes that ordering explicit rather
than load-order luck.

**Oodle's leg is a second `LangfuseSpanProcessor`, re-addressed by
headers.** Oodle serves the Langfuse ingest API, with the public key
`default` and the Oodle API key as the secret. A second `Langfuse()`
client does not work — the SDK refuses to trace at all once two clients
exist in a process, to stop one project's spans leaking into another — so
the processor is constructed directly, with the *app's* Langfuse public
key (that is what its project filter checks) and Oodle's credentials in
`additional_headers`, which it merges last and so replace the
`Authorization` header it built.

**The SDK's export filter is widened for Pipecat.** By default a span is
exported only if the Langfuse SDK wrote it, it carries a `gen_ai.*`
attribute, or its instrumentation scope is one of the LLM instrumentors
Langfuse knows. Pipecat is not on that list and its `turn` spans carry
only `turn.*` and `conversation.id`, so without `should_export_span` the
turn spans are dropped and the `stt`/`llm`/`tts` spans beneath them
arrive parented to a span that was never sent. Set
`LANGFUSE_EXPORT_PIPECAT_SPANS=false` to watch that happen.

`LangfuseSpanProcessor` and the default filter are not re-exported at the
package root, so they come from `langfuse._client.span_processor` and
`langfuse._client.span_filter`. The path needs Langfuse SDK v4.

## What a backend sees

Pipecat's tracing is wired up as its documentation describes, but two
things about the result surprise a backend reading it.

**The development runner's HTTP spans swallow the trace.** FastAPI traces
its own requests as soon as a tracer provider is registered, and the
Pipecat development runner is a FastAPI app. Left alone, every static
asset and signalling call becomes a trace of its own, and the session's
`conversation` span is not a root at all — it hangs under the WebRTC
offer request:

```
POST /sessions/{session_id}/{path}     ← the trace, as the backend sees it
└── fastapi.background_task
    └── conversation
        └── turn
            ├── stt  ├── llm  └── tts
```

`bot.py` turns that off with FastAPI's own `telemetry` argument, before
importing Pipecat — the runner builds its app at import time. The
`conversation` span is then the root of its own trace, and page loads
stop producing traces.

**The conversation is not in the GenAI semantic conventions.** Pipecat
records what was said under names of its own:

| span | Pipecat writes | the conventions expect |
| --- | --- | --- |
| `llm` | `input` (JSON messages), `output` (text) | `gen_ai.input.messages`, `gen_ai.output.messages` |
| `stt` | `transcript` | `gen_ai.output.messages` |
| `tts` | `text` | `gen_ai.input.messages` |

The conventional form is a list of `{"role": …, "parts": [{"type":
"text", "content": …}]}`. A backend that renders a conversation from it —
Oodle's GenAI tab among them — therefore shows a voice trace with
timings, models and token counts but no transcript. The one exception is
the system prompt, which Pipecat already writes as
`gen_ai.system_instructions`, so it appears on its own.

This demo does not paper over it. The spans go out as Pipecat writes
them, and `make verify-local` asserts exactly that, so the gap is visible
where it belongs: in the backend that reads the spans, or in Pipecat. The
Langfuse SDK path is unaffected either way — Langfuse maps `input` and
`output` itself.

## Verifying without accounts

```bash
make verify-local
```

This stands up two local OTLP receivers — one in place of Langfuse, one
in place of the Oodle collector — runs each path against them in its own
subprocess, and compares what the two sides received: the five spans,
one trace id, the parent links, `service.name` on every span, identical
span ids on both sides, and the right credentials and URL path per
destination. It also runs the Langfuse path with the default filter, to
show the dropped turn span. No Langfuse, Oodle or OpenAI account is
needed.

## Make targets

| Target | Description |
| --- | --- |
| `make up` | Start the voice bot, tracing over OpenTelemetry |
| `make up-langfuse` | Start the voice bot, tracing through the Langfuse SDK |
| `make logs` | Tail the bot's logs |
| `make verify-local` | Offline check of both paths, no accounts needed |
| `make down` | Stop the bot |
| `make clean` | Remove containers, volumes and the local image |

## Notes

- **`gen_ai.*` on the conversation span.** Pipecat writes the GenAI
  semantic conventions on the service spans but has nothing to derive
  them from for the span that wraps a session, so `bot.py` passes
  `additional_span_attributes={"gen_ai.operation.name": "invoke_agent",
  "gen_ai.agent.name": ...}`. That is what makes the session read as an
  agent run in Oodle's agent-observability views rather than as an
  untyped span.
- **`langfuse.environment` is a resource attribute here.** Normally the
  Langfuse client sets it from `LANGFUSE_TRACING_ENVIRONMENT` when it
  builds its own provider. Pipecat owns the provider on both paths, so
  the environment travels as `OTEL_RESOURCE_ATTRIBUTES=langfuse.environment=…`
  instead — see [`docker-compose.yml`](docker-compose.yml).
- **Flush, don't shut down, between sessions.** The dev runner serves
  every connection from one process, so the bot flushes after a session
  and closes the provider at exit. A provider closed after the first
  session would silently drop the second session's spans.
- **One path at a time.** Each registers the process-wide tracer
  provider, so `TRACING_BACKEND` picks exactly one.
- Transcripts, prompts and completions are on the spans. Both backends
  receive them, which is what makes a voice trace readable — and worth
  knowing before pointing this at anything real.

## Troubleshooting

**The bot never speaks, and the logs show `Error during completion:
Connection error.` from every service.** The OpenAI SDK reads
`OPENAI_BASE_URL` from the environment itself, and an empty value is not
the same as an unset one — the base URL becomes `""` and no call can
leave the process. Leave the variable out of `.env` entirely unless the
calls really go through a gateway. `docker-compose.yml` passes it through
only when it is set, and `bot.py` clears a blank one, so this needs a
deliberate `OPENAI_BASE_URL=` to reproduce.

**Spans fail to export with `Failed to resolve 'langfuse-web'`.** That
hostname only exists inside the compose project that defines it, so a
self-hosted Langfuse from another project is not reachable by its service
name. Point `LANGFUSE_BASE_URL` at `http://host.docker.internal:<its
published port>` instead — `docker port langfuse-demo-langfuse-web-1`
will say which port that is.

**The trace's root is `POST /sessions/{session_id}/{path}`, or every page
load produces its own trace.** FastAPI's built-in request tracing is on.
See [What a backend sees](#what-a-backend-sees); `bot.py` disables it
before importing Pipecat, so this returns if that is removed or if
Pipecat is imported first.

**The trace has no transcript — no user or assistant messages, only the
system prompt.** Expected, and not a misconfiguration: the backend is
reading `gen_ai.input.messages` and `gen_ai.output.messages`, and Pipecat
writes `input`, `output`, `transcript` and `text`. See
[What a backend sees](#what-a-backend-sees).

**A session produced spans but no trace appears.** The `conversation`
span covers the whole session and closes when the pipeline ends, so a
trace is only complete once the browser tab disconnects. While a session
is open its finished `stt`/`llm`/`tts` spans have already been exported
and have no root yet.

**Nothing at all is exported.** Check the line
`Tracing <service> to Oodle (…) and Langfuse (…)` in the startup logs: it
names both resolved endpoints. Its absence means `TRACING_BACKEND` is
`none`.

## Related demos

- [`langfuse-native-demo`](../langfuse-native-demo) — the Langfuse SDK's
  own exporter, dual-writing with no OpenTelemetry pipeline in the app
- [`langfuse-demo`](../langfuse-demo) — the Langfuse SDK beside a
  collector, with a self-hosted Langfuse option
- [`litellm-laminar-demo`](../litellm-laminar-demo) — the same
  two-destination pattern with Laminar as the primary SDK
- [`livekit-demo`](../livekit-demo) — voice-agent traces from LiveKit
