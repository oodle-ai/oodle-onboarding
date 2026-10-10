# LiveKit trace replay

Replay a captured LiveKit voice-agent trace through an
OTel Collector into Oodle for end-to-end testing of
LiveKit trace normalization.

The collector, `.env` and `Makefile` are shared with the
live voice agent, in [`livekit-demo/`](..). Run the
commands below from there.

## Quick start

```bash
cd livekit-demo

# 1. Configure credentials
cp .env.example .env
# Edit .env with your Oodle instance and API key

# 2. Start the OTel Collector
make up

# 3. Replay the sample trace
make replay

# 4. View traces in Oodle LLM Ops
```

The replay script runs with [uv](https://docs.astral.sh/uv/).

## How it works

`replay.py` reads a Jaeger-format trace export
(`sample-trace.json`) and re-creates all 104 spans with
their original attributes (`lk.*`, `gen_ai.*`) and span
events (`gen_ai.system.message`, `gen_ai.choice`, etc.),
then exports them via OTLP/HTTP to the collector.

The collector forwards traces to Oodle where the event
receiver normalizes LiveKit-specific attributes into
standard `gen_ai.*` attributes for the LLM Ops pipeline.

## Files

| File | Purpose |
|------|---------|
| `replay.py` | Reads trace JSON, sends via OTLP |
| `sample-trace.json` | Captured LiveKit agent trace |
| `otel-collector-config.yaml` | Collector config |
| [`../docker-compose.yml`](../docker-compose.yml) | The `otel-collector` service |

## Replay options

```bash
# Custom endpoint
static-replay/replay.py static-replay/sample-trace.json --endpoint http://localhost:4319

# Generate fresh trace/span IDs (for multiple replays)
static-replay/replay.py static-replay/sample-trace.json --fresh-ids

# Replay as an agent that marks personal data
static-replay/replay.py static-replay/sample-trace.json --fresh-ids --mark-pii
```

## Agents that mark personal data

An application can mark the LiveKit fields that may hold
personal data. LiveKit then writes each of those under
`lk.pii.` instead of `lk.`, with the same value: the
prompt, the transcript, the reply, the chat context, a
tool's arguments and result, the room and the
participant. A name or a metric keeps its place.

The capture was taken with the marking off, so
`--mark-pii` renames those fields and replays the same
run as an agent with it on. Use it to check that ingest
resolves both spellings onto `gen_ai.*`: a receiver that
knows only `lk.` produces a trace with no transcript at
all, since every attribute carrying one has moved.

The [live voice agent](../voice-agent) produces the
`lk.pii.` spelling for real, and shows what an agent
sends when it withholds those fields instead.
