# LiveKit voice agent: personal data in or out of the trace

A [LiveKit Agents](https://docs.livekit.io/agents/) voice agent that
traces every call to Oodle. You pick, per call, whether the trace carries
the conversation:

| PII mode | What Oodle receives | `set_tracer_provider(...)` |
| --- | --- | --- |
| `allow` | The full call: `lk.pii.*` transcripts, replies, tool arguments and results, the room and participant, plus `gen_ai.input/output.messages` and the GenAI message events | `allow_pii=True` (LiveKit's default) |
| `withhold` | The same span tree with timings, models, token counts, tool names and agent labels, but none of the text | `allow_pii=False` |

The agent books home valuations, so a call is full of personal data: the
caller's name, phone number and address. That makes the difference
between the two traces easy to see.

Where [`../static-replay`](../static-replay) replays one captured trace,
this is the real framework producing both shapes live. Its setup mirrors
a production LiveKit deployment that sends its traces to Oodle:

- a `voice_agent` that can hand the call to a `transfer_agent`, traced as
  `lk.agent_label`
- the LLM behind a `FallbackAdapter`, which adds an `llm_fallback_adapter`
  span above each `llm_request`
- per-call metadata on every span: `agent.id`, `job.id`, `session.id`,
  `user.id`, `langfuse.session.id`, `langfuse.user.id`, `langfuse.tags`
- a `TracerProvider` built per call and handed to LiveKit with
  `set_tracer_provider(provider, metadata=..., allow_pii=...)`, exporting
  straight to Oodle's OTLP endpoint

Speech-to-text, the LLM and text-to-speech are all OpenAI, voice activity
detection runs locally, and the LiveKit server runs in Docker. The demo
needs an OpenAI key and an Oodle instance, and no LiveKit Cloud project.

## Quick start

The replay and this agent share one `docker-compose.yml`, `.env` and
`Makefile`, in [`livekit-demo/`](..). Run these from there:

```bash
cd livekit-demo
cp .env.example .env
# Edit .env: your Oodle instance and API key, your OpenAI key.
make voice
```

Open <http://localhost:7870>, choose a PII mode, start a call and allow
the microphone. Max greets you. Book a valuation by giving a name, a
phone number and an address, or ask for a person to see the handoff.

The page shows the call's `session.id`. In Oodle, open Agent Observability
→ Traces and filter on it, or on service `livekit-voice-worker`. A trace
is complete once you end the call. Run one call in each mode to compare
them.

## How it works

```
browser ──POST /api/token {pii_mode}──► web.py
   │                                      │ token for a new room, with an agent
   │                                      │ dispatch whose metadata holds
   │                                      │ pii_mode, call_id and contact_id
   └──── WebRTC ────► livekit-server ──dispatch──► agent.py (one process per call)
                                                    │ tracing.init(metadata, allow_pii)
                                                    └──► Oodle  <instance>-otlp.collector.oodle.ai/v1/traces
```

**The mode travels with the call.** [`web.py`](web.py) puts an
agent dispatch in the token's room configuration, so the room is created
with the agent already sent for, and the dispatch metadata carries the
mode. The agent reads it as `ctx.job.metadata`.

**A tracer provider per call.** [`agent.py`](agent.py) builds the
provider in the job's entrypoint, before the session starts, as LiveKit's
Langfuse example does. Each call runs in its own job process, so its
metadata and its `allow_pii` affect that call alone. The provider is
flushed in a shutdown callback, after the `agent_session` span has ended.

**LiveKit does the filtering.** `set_tracer_provider` puts a span
processor ahead of every exporter already on the provider. With
`allow_pii=False` that processor drops:

- every attribute with a `pii` segment in its key, such as
  `lk.pii.user_transcript`, `lk.pii.response.text`,
  `lk.pii.function_tool.arguments`, `lk.pii.input_text`,
  `lk.pii.room_name` and `lk.pii.participant_identity`
- the GenAI content attributes, whose names are fixed by the conventions:
  `gen_ai.input.messages`, `gen_ai.output.messages`,
  `gen_ai.system_instructions`, `gen_ai.tool.call.arguments` and the rest
- the GenAI message events: `gen_ai.user.message`, `gen_ai.choice` and
  the others

A dropped attribute is removed whole, not masked. The filter works on
field names, not values, so it removes the text whether or not it is
personal. With PII withheld, even `check_availability("Tuesday")` loses
its arguments.

## What stays in a withheld trace

The span tree is unchanged: `agent_session`, `agent_turn`, `user_turn`,
`llm_node`, `llm_fallback_adapter`, `llm_request`, `function_tool`,
`tts_node`, `tts_request` and the rest. These stay too:

- latency: `lk.response.ttft`, `lk.response.ttfb`,
  `lk.end_of_turn_delay`, `lk.transcription_delay`
- models and usage: `gen_ai.request.model`, `gen_ai.provider.name`,
  `gen_ai.usage.*`, `lk.llm_metrics`, `lk.tts_metrics`
- behaviour: `lk.function_tool.name`, `lk.function_tool.is_error`,
  `lk.agent_label`, `lk.interrupted`, `lk.participant_kind`
- your metadata, on every span

**The metadata is never filtered.** LiveKit treats it as your attribution
and stamps it on every span in both modes. Put pseudonymous ids in it, as
this demo does with a random `contact_id`, and never a name or a phone
number. A `langfuse.user.id` holding an email address would reach Oodle
even with PII withheld.

## Verifying without accounts

```bash
make verify-local
```

This starts a local OTLP receiver in place of Oodle. For each mode it
records one booking turn through LiveKit's own tracer and attribute names,
in its own subprocess, and checks what arrived. In both modes it checks
the span tree, the service name, the metadata on every span and Oodle's
headers. With PII allowed it checks that the transcript, the tool
arguments and the GenAI messages are there. With PII withheld it checks
that the name, number and address appear nowhere, while the model, token
counts, tool name and agent label remain. No Oodle, LiveKit or OpenAI
account is needed.

## Make targets

Run from [`livekit-demo/`](..).

| Target | Description |
| --- | --- |
| `make voice` | Start LiveKit, the agent and the web page |
| `make voice-logs` | Tail the agent's logs |
| `make verify-local` | Offline check of both PII modes, no accounts needed |
| `make down` | Stop everything, the replay's collector included |
| `make clean` | Also remove volumes and the local image |

## Files

| File | Purpose |
| --- | --- |
| [`agent.py`](agent.py) | The agent server: `voice_agent`, `transfer_agent`, tools, per-call tracing |
| [`tracing.py`](tracing.py) | The per-call tracer provider, Oodle's endpoint and the PII mode |
| [`web.py`](web.py) | The page and the token endpoint that dispatches the agent |
| [`static/index.html`](static/index.html) | Mode picker, call button and live transcript |
| [`verify_local.py`](verify_local.py) | Offline check of both modes |
| [`Dockerfile`](Dockerfile) | The image the agent and the web page both run |
| [`../docker-compose.yml`](../docker-compose.yml) | LiveKit server, agent and web page under the `voice` profile, beside the replay's collector |

## Notes

- **`LIVEKIT_TELEMETRY_ALLOW_PII`** sets the same switch for an app that
  lets LiveKit adopt an OpenTelemetry provider it never passes to
  `set_tracer_provider`. Here `allow_pii` is always passed explicitly, so
  the variable has no effect.
- **LiveKit Cloud is a different setting.** If the agent ran against a
  LiveKit Cloud project, Cloud's own observability would receive what the
  project's dashboard setting allows, whatever `allow_pii` says. If the
  project mandates redaction, PII is stripped for every exporter, Oodle's
  included, and `allow_pii=True` cannot override it.
- **The media is local only.** The LiveKit server advertises `127.0.0.1`
  for WebRTC, so the browser has to be on the machine running Docker. The
  agent shares the server container's network namespace for the same
  reason.
- **One idle process.** `num_idle_processes=1` keeps the worker light.
  Production's default is 14 prewarmed processes.

## Troubleshooting

**The agent never joins the call.** Run `docker compose --profile
voice logs livekit` in `livekit-demo/` and look for `worker registered` with `agentName: livekit-demo-agent`.
The token dispatches by that name, so `AGENT_NAME` must match between
the `agent` and `web` services.

**The call connects but there is no audio either way.** WebRTC media
uses UDP 7882 and falls back to TCP 7881. Make sure nothing else on the
machine holds those ports.

**Max never speaks, and the logs show `all LLMs failed`.** Check
`OPENAI_API_KEY`. If you use a gateway, set `OPENAI_BASE_URL` to it, and
otherwise leave it out of `.env` completely: an empty value breaks every
OpenAI call.

**A withheld trace still shows a transcript.** Check the line
`Tracing livekit-voice-worker to Oodle (…), personal data withheld` in
`make voice-logs` for that call. If it says `included`, the page asked for
`allow`. The page sends the selected mode when you start a call.

## Related demos

- [`../static-replay`](../static-replay) replays a captured LiveKit
  trace, with `--mark-pii` to rename its fields to the `lk.pii.*` spelling
- [`pipecat-demo`](../../pipecat-demo) is the same browser voice-agent
  setup on Pipecat, dual-writing to Langfuse and Oodle
