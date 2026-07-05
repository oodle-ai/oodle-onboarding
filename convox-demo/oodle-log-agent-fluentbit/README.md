# Fluent Bit log agent — per-app routing via ECS introspection

A host-local **Fluent Bit** log agent for Convox v2 (generation 2, ECS/EC2) that dual-writes
each app's logs to **CloudWatch (one log group per app)** and **Oodle**, deriving the app
identity **per record** — with **no per-app configuration** and no application code changes.

This is the auto-onboarding alternative to the OTel agent in `../oodle-log-agent/` (which
labels logs with a single hardcoded `service.name`, correct only when one app points at it).
Both can run side by side: this agent listens on host port **5141**, the OTel one on **5140**.

## The problem it solves

Convox's `LogDriver=Syslog` runs Docker's syslog driver with **no `tag`**, so the rfc5424
`APP-NAME` field carries only the **container short-id** (e.g. `02a2b9e2f2c0`), not the app
name — and there is no Convox param to set the tag. A single shared agent therefore can't tell
apps apart from the payload alone.

Fluent Bit's **`ecs` filter** resolves that short-id to the ECS task metadata (app name) by
querying the **ECS Agent introspection API**. The catch on Convox: agents run in ECS **bridge**
networking, so the introspection endpoint is NOT reachable on `127.0.0.1:51678` (the container's
own loopback). It **is** reachable on the **docker bridge gateway `172.17.0.1:51678`** (verified
on `gm-test`), which is what `ECS_Meta_Host` points at below.

## Pipeline

```
rails-demo (LogDriver=Syslog, dest tcp://localhost:5141)
   │  Docker syslog rfc5424: APP-NAME = container short-id
   ▼
Fluent Bit agent (agent: one per host, host port 5141)
   syslog input ──▶ rewrite_tag (short-id -> tag) ──▶ ecs filter (introspection @172.17.0.1:51678)
                 ──▶ lua (clean app name -> Oodle canonical `service`)
   ├─ cloudwatch_logs ──▶ /convox/<app>   (per-app group, auto-created)
   └─ http            ──▶ Oodle /ingest/v1/logs   (JSON, gzip, per Oodle's logs_fluent_bit spec)
```

### Oodle canonical field mapping

Oodle indexes a fixed set of top-level log fields. The agent emits **those names** (not custom
ones) so enrichment is directly filterable in Oodle instead of buried in the nested `log.*` blob:

| Source (ECS introspection / syslog) | Oodle canonical field |
|-------------------------------------|-----------------------|
| clean app name (from `$TaskDefinitionFamily`) | `service` |
| `$TaskDefinitionFamily`             | `task_definition`     |
| `$TaskID`                           | `task_id`             |
| `$ECSContainerName`                 | `container_name`      |
| container short-id (syslog appname) | `container_id`        |
| `$ClusterName`                      | `cluster`             |

After this, `service = rails-demo` is a first-class filter in the Oodle Logs Explorer / CLI.

## Files

- `fluent-bit.conf` — the pipeline (syslog in → rewrite_tag → ecs → lua → cloudwatch_logs + http + debug stdout).
- `parsers-convox.conf` — rfc5424 parser for Convox's Docker syslog output (names the app-name group `appname`).
- `derive_app.lua` — reduces the ECS family to a clean app name and maps to `service`/`container_id`.
- `Dockerfile` — `aws-for-fluent-bit` (has syslog/ecs/cloudwatch_logs/http built in) + the config.
- `convox.yml` — agent on host port 5141; env `OODLE_INSTANCE`, `OODLE_API_KEY`, `RACK_PREFIX`.
- `Makefile` — deploy + switch/restore rails-demo + logs/ps/down/clean.

## Usage

```sh
cp .env.example .env         # fill OODLE_INSTANCE / OODLE_API_KEY / RACK_PREFIX (never committed)
make up                      # create app, grant IAM (CloudWatch write), deploy the agent
make switch-rails            # point rails-demo's logs at this agent (port 5141)
make logs                    # watch enriched records (debug stdout output shows service/task_*)
make restore-otel            # point rails-demo back at the OTel agent (5140)
```

The Oodle host/key are passed only via `convox env` — **never committed**. The debug `stdout`
output in `fluent-bit.conf` is for validation; remove it in production to halve log volume.

## Validated end to end (2026-07-03, gm-test)

- ECS introspection reachable from a bridge-mode agent at `172.17.0.1:51678`; `/v1/tasks` is host-scoped.
- Live rails-demo traffic: container short-id `02a2b9e2f2c0` → `service=rails-demo` per record.
- CloudWatch group `/convox/rails-demo` auto-created with the enriched records.
- Oodle HTTP output `HTTP status=200`; records filterable by `service=rails-demo` via the `oodle` CLI.

## Notes / limitations

- **EC2 launch type only** — the `ecs` filter's introspection API is not available on Fargate.
- `172.17.0.1` is the Docker default bridge gateway (stable on the ECS-optimized AMI). If a rack
  uses a non-default bridge, derive the gateway at start instead of hardcoding.
- Non-rfc5424 lines (occasional Convox framing) fail the parser and are dropped — harmless.
