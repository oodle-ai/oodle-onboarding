# LiveKit Voice Agent Trace Demo

LiveKit Agents voice traces in Oodle, two ways:

| Folder | What it does |
| --- | --- |
| [`static-replay/`](static-replay) | Replays a captured LiveKit voice-agent trace through an OTel Collector into Oodle, for end-to-end testing of LiveKit trace normalization. With `--mark-pii`, replays it as an agent that marks personal data. |
| [`voice-agent/`](voice-agent) | A live LiveKit voice agent you talk to in the browser, with each call traced straight to Oodle either with its personal data or without it. |

Both share this directory's `docker-compose.yml`, `.env` and
`Makefile`. Each folder's README explains how it works.

## Prerequisites

- Docker and docker-compose
- [uv](https://docs.astral.sh/uv/) (for the replay script)
- An Oodle instance with an API key
- An OpenAI API key (for the voice agent only)

## Quick start

```bash
# 1. Configure credentials
cp .env.example .env
# Edit .env with your Oodle instance and API key, and your
# OpenAI key for the voice agent

# 2a. Replay: start the OTel Collector and replay the sample trace
make up
make replay

# 2b. Live: start LiveKit, the voice agent and its page
make voice
# Open http://localhost:7870, pick a PII mode and start a call

# 3. View traces in Oodle LLM Ops
```

The replay needs only the collector, and `make up` starts only that.
The voice services sit behind the compose profile `voice`, so `make
voice` is what builds and starts them. `make down` stops everything.

## Make targets

| Target | Description |
| --- | --- |
| `make up` | Start the OTel Collector for the replay |
| `make replay` | Replay the sample trace via OTLP |
| `make replay-pii` | Replay it as an agent that marks personal data |
| `make logs` | View collector logs |
| `make voice` | Start LiveKit, the voice agent and its web page |
| `make voice-logs` | Tail the voice agent's logs |
| `make verify-local` | Offline check of the voice agent's two PII modes, no accounts needed |
| `make status` | Show service status |
| `make down` | Stop everything |
| `make clean` | Stop everything, remove volumes and the voice agent image |

## Files

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | OTel Collector for the replay; LiveKit server, voice agent and web page under the `voice` profile |
| `.env.example` | Oodle credentials for both, and the voice agent's OpenAI and model settings |
| `Makefile` | The targets above |
| `static-replay/` | `replay.py`, the captured `sample-trace.json` and the collector config |
| `voice-agent/` | The agent, its tracing, the web page and the image they run in |
