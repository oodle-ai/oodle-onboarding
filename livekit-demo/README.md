# LiveKit Voice Agent Trace Demo

Replay a captured LiveKit voice-agent trace through an
OTel Collector into Oodle for end-to-end testing of
LiveKit trace normalization.

## Prerequisites

- Docker and docker-compose
- [uv](https://docs.astral.sh/uv/) (for the replay script)
- An Oodle instance with an API key

## Quick start

```bash
# 1. Configure credentials
cp .env.example .env
# Edit .env with your Oodle instance and API key

# 2. Start the OTel Collector
make up

# 3. Replay the sample trace
make replay

# 4. View traces in Oodle LLM Ops
```

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
| `docker-compose.yml` | OTel Collector service |
| `otel-collector-config.yaml` | Collector config |

## Replay options

```bash
# Custom endpoint
./replay.py sample-trace.json --endpoint http://localhost:4319

# Generate fresh trace/span IDs (for multiple replays)
./replay.py sample-trace.json --fresh-ids
```
