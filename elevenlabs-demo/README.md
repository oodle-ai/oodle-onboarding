# ElevenLabs Agents Demo

ElevenLabs voice agents in Oodle Agent Observability. Every call arrives
as a trace: the agent, each LLM call with its model, tokens and cost, and
each tool call with its parameters and result.

ElevenLabs runs the agent, so there is no code to instrument. When a call
ends, ElevenLabs sends a **post-call webhook** with the call as an
OpenTelemetry trace (OTLP/JSON). The webhook goes straight to Oodle, with
the Oodle API key in its headers. Oodle maps the `elevenlabs.*` spans onto
the GenAI conventions when the trace arrives.

```
caller ──voice──► ElevenLabs agent (STT -> LLM -> TTS, tools, RAG)
                        │ call ends, analysis done
                        └─ post-call webhook, OpenTelemetry format ──► Oodle
                           https://<instance>-otlp.collector.oodle.ai/v1/otlp/traces/elevenlabs
                           X-API-KEY, X-OODLE-INSTANCE in the webhook headers
```

## What the demo agent does

"Maya" is a travel desk agent. She has:

| Feature | How | In the trace |
| --- | --- | --- |
| `lookup_booking` | A client tool: it runs in `agent/demo.py` | `execute_tool` span with parameters and result |
| `get_exchange_rate` | A webhook tool: ElevenLabs calls a public API | `execute_tool` span with parameters and result |
| Travel policy | A knowledge base, used through RAG | the retrieval query on the LLM call |

The demo's script asks about a booking, an exchange rate and the bag fee.
In a voice call, the speech-to-text sometimes mishears the booking
reference, the tool answers "No booking found", and Oodle flags the call
with the `failure.tool_error` signal.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- An ElevenLabs API key with access to ElevenAgents
- An Oodle instance and API key
- Docker, only for the forwarder path

## Quick start

```bash
cp .env.example .env    # Oodle instance and key, ElevenLabs key
make agent              # create the demo agent in your ElevenLabs workspace
make webhook            # send its post-call traces straight to Oodle
make voice              # a real voice call with a synthetic caller
```

Then open Agent Observability -> Traces in Oodle. A trace arrives about a
minute after the call ends, when ElevenLabs has analyzed it. Filter on
service `elevenlabs-convai`, or on the conversation id that `make voice`
prints (it is the session id).

To talk to the agent yourself, open the "Talk to it" link `make agent`
prints. That call is traced the same way.

## Make targets

| Target | What it does |
| --- | --- |
| `make agent` | Create the demo agent, its tools and its knowledge base |
| `make webhook` | Point the agent's post-call webhook straight at Oodle, by running `setup_webhook.py` |
| `make chat` | A short text-only conversation: no audio, lowest cost |
| `make voice` | A real voice call: the caller's lines are made with ElevenLabs text to speech and sent as the microphone, so the agent runs speech-to-text, the LLM and text-to-speech. Both sides are saved to `state/last-call.wav` |
| `make replay` | Send `sample-trace.json`, a captured voice call, as a new trace. No ElevenLabs account needed |
| `make forwarder` | Instead of `make webhook`: start a forwarder and a public tunnel on this machine, and point the webhook there |
| `make logs` | Tail the forwarder's logs |
| `make down` | Stop the forwarder and the tunnel |
| `make teardown` | Delete the demo agent, its knowledge base and its webhook |

## Two ways to send the trace

**Straight to Oodle** (`make webhook`). The webhook's URL is Oodle's
ElevenLabs endpoint, and its request headers carry the Oodle instance and
API key. Nothing to run. [`setup_webhook.py`](setup_webhook.py) is the
snippet the ElevenLabs Agents tile in Oodle shows, step for step: create
the webhook, turn on retries, attach it to the agent in the OpenTelemetry
format. The tile fills in your Oodle values; here they come from `.env`.

**Through your own service** (`make forwarder`). The webhook goes to
[`forwarder/app.py`](forwarder/app.py), which checks the webhook signature
with the ElevenLabs SDK and posts the trace to Oodle. Use this shape to
keep the Oodle key out of ElevenLabs, to redact the transcript (post to
an OpenTelemetry Collector instead), or when the agent's one post-call
webhook already goes to your service. The demo reaches your machine
through a Cloudflare quick tunnel, which needs no account; its URL
changes on each start, and `make forwarder` updates the webhook.

Both set the webhook's transcript format to **OpenTelemetry**. The
default JSON format carries a transcript and no trace.

## Files

| File | Purpose |
| --- | --- |
| `setup_webhook.py` | The Oodle tile's setup snippet: the webhook straight to Oodle |
| `agent/demo.py` | The agent, the forwarder webhook, the text and voice conversations, export and replay. Runs with `uv`; no install step |
| `forwarder/` | The webhook forwarder and its image |
| `docker-compose.yml` | The forwarder and the Cloudflare tunnel |
| `sample-trace.json` | A captured voice call, for `make replay` |
| `state/` | Ids of what the demo created in ElevenLabs, the webhook secret and the last call's audio. Not committed |

## Notes

- **Cost.** `make chat` uses only the LLM. `make voice` also uses
  ElevenLabs speech-to-text and text-to-speech for about a minute.
- **Send each call once.** ElevenLabs makes new span ids on every
  export, so a call sent by the webhook *and* by `demo.py export` shows
  every span twice in one trace. With a webhook set, `make chat` and
  `make voice` leave the sending to the webhook.
- **`.env` wins over your shell.** If your shell exports `OODLE_INSTANCE`
  or `OODLE_API_KEY`, the demo still uses the values in `.env`.
