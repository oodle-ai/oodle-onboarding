# Datadog Agent — host-local APM daemon for Convox v2 (ECS/EC2)

Runs the official **Datadog Agent** (`gcr.io/datadoghq/agent:7`) as a Convox
generation-2 **agent** — one instance per rack host (DaemonSet-style) — collecting
**APM traces**, **DogStatsD custom metrics**, host/process metrics, and container
metadata, and shipping them to Datadog (`us5.datadoghq.com`) **and dual-writing metrics
and traces to Oodle** (a copy of each, alongside Datadog — no app changes).

## Why an agent (not a normal service)

An `agent:` runs on every rack instance and can **publish host ports**. The Agent
publishes:

| Port | Proto | Purpose |
|------|-------|---------|
| `8126` | tcp | APM trace receiver |
| `8125` | udp | DogStatsD custom metrics |

App containers run in ECS **bridge** networking, so `localhost` inside an app is the
app's own loopback — not the host. The host (where the agent publishes 8126/8125) is
reachable from a bridge container at the **docker bridge gateway `172.17.0.1`**. So the
Rails app's tracer is pointed at `DD_AGENT_HOST=172.17.0.1`. (Same gateway the Fluent
Bit log agent uses to reach ECS introspection at `172.17.0.1:51678`.)

```
rails-demo (bridge container)
   │  ddtrace -> DD_AGENT_HOST=172.17.0.1:8126
   ▼
Datadog Agent (agent: one per host, publishes host 8126/tcp, 8125/udp)
   ├─ APM traces ──▶ Datadog (us5)  +  Oodle   [service:rails-demo, env:sales]
   ├─ DogStatsD   ──▶ Datadog (us5)
   └─ host/process/container metrics ▶ Datadog (us5)  +  Oodle
```

`DD_APM_NON_LOCAL_TRAFFIC=true` / `DD_DOGSTATSD_NON_LOCAL_TRAFFIC=true` are **required**
— without them the receivers bind `127.0.0.1` inside the agent container and reject the
cross-container traffic.

## Dual-write to Oodle (metrics + traces)

The Agent natively **dual-ships** — it forwards a copy of everything to extra endpoints
alongside Datadog, no app changes. Two env vars carry the Oodle endpoints (JSON with the
Oodle API key, so injected via `convox env`, declared in `convox.yml`):

| Signal | Env var | Oodle endpoint |
|--------|---------|----------------|
| Metrics | `DD_ADDITIONAL_ENDPOINTS` | `https://<collector>/v1/datadog/<instance>` |
| Traces  | `DD_APM_ADDITIONAL_ENDPOINTS` | `https://<collector>/v1/datadog_traces/<instance>` |

Logs are **not** dual-written (`DD_LOGS_ENABLED=false`). See
[Datadog dual-shipping docs](https://docs.datadoghq.com/agent/configuration/dual-shipping/).

**Verify in Oodle** (CLI configured for the same instance):

```sh
# metrics — DD-origin names appear (datadog_*, dd_trace_stats_*)
oodle metrics names --start -15m -o json | jq -r '.[]' | grep -E 'datadog|dd_trace_stats'
oodle metrics query --query 'sum by (service,env) (dd_trace_stats_hits)' -o json
# traces — rails-demo spans land in Oodle
oodle traces list --service rails-demo --start -15m --end now -o json
```

Verified flowing: `dd_trace_stats_hits{service="rails-demo",env="sales"}` and
`oodle traces list --service rails-demo` returning `rack.request` spans.

## Files

- `convox.yml` — the agent manifest (image, `agent:` host ports, privileged, volumes, DD + dual-write env).
- `.env` / `.env.example` — `DD_API_KEY`/`DD_SITE` + `OODLE_API_KEY`/`OODLE_COLLECTOR_DOMAIN`/`OODLE_INSTANCE_ID` (secrets; injected via `convox env`, never committed).
- `Makefile` — create/deploy the agent, instrument the app, verify.

## Usage

```sh
cp .env.example .env      # fill DD_API_KEY / DD_SITE  (already populated from datadog/dual-write/.env)

make up                   # create the agent app, set secrets, deploy the daemon
make deploy-app           # rebuild rails-demo (gem + tracer env from convox.yml), from repo root
make status               # `agent status` inside the agent — confirm APM receiver is up
```

Deploy the agent **before** the app sends traces (the app just drops spans if nothing is
listening — non-fatal, unlike the syslog agent). The Rails side needs the `datadog` gem
(repo `Gemfile`, wired in `config/initializers/datadog.rb`) **and** the tracer env.

> ⚠️ **The tracer env lives in the repo-root `convox.yml` `environment:` block**, not in
> `convox env set`. Convox only injects env vars that a service's **manifest declares** — vars
> set only via `convox env set` are stored but **never reach the container**. Setting
> `DD_AGENT_HOST` etc. via `convox env` alone leaves the tracer on its `127.0.0.1:8126`
> default, so it silently drops every span (no agent in the app's own container). The demo
> declares `DD_AGENT_HOST=172.17.0.1`, `DD_TRACE_AGENT_PORT=8126`, `DD_SERVICE=rails-demo`,
> `DD_ENV=sales`, `DD_VERSION=1.0.0` in `convox.yml`. To retarget, edit that file and
> `make deploy-app`.

**Verify traces reach the agent** (with the agent at `DD_LOG_LEVEL=debug` temporarily):
`convox logs -a datadog-agent -r <rack> | grep 'service:rails-demo'` should show
`traces received: N` lines from the trace-agent.

## DD_APM_ANALYZED_SPANS

`DD_APM_ANALYZED_SPANS=rails-demo|rack.request=1`

Format is a comma-separated list of `<service>|<operation_name>=<sample_rate>`. It marks
those spans as **analyzed spans** (a.k.a. "App Analytics" / Trace Search) — the Agent tags
each matching span so it is **indexed and searchable/aggregatable in Trace Analytics at the
given rate** (`1` = 100%), independent of head-based trace sampling. Here it targets the top
web span of the Rails app: service `rails-demo`, operation `rack.request`, 100% retained.

The original example (`rental-application|rack.request=1,scheduler|rack.request=1,rently|rack.request=1`)
listed three services; this demo has a single app, so it collapses to one entry. To analyze
another service's web spans, add `,<service>|rack.request=1`. Note this is a **legacy** knob —
modern setups prefer tag-based retention filters — but it still works and is what was requested.
