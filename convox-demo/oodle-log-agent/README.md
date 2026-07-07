# Fluent Bit log agent — per-app routing via ECS introspection

A host-local **Fluent Bit** log agent for Convox v2 (generation 2, ECS/EC2) that ships each
app's logs to **Oodle** — and, during migration, **dual-writes** to CloudWatch too — deriving
the app identity **per record** with **no per-app configuration** and **no application code
changes**.

## Migration path

The agent is designed around a two-phase migration off CloudWatch:

| Phase | Outputs | CloudWatch role |
|-------|---------|-----------------|
| **1 — Dual-write** (default in this repo) | `cloudwatch_logs` **+** Oodle `http` | still written (one group per app), so nothing downstream breaks while you validate Oodle |
| **2 — Single-write** | Oodle `http` only | dropped from the ingestion path entirely |

**Why an agent, not CloudWatch subscription/pull:** the agent is the fan-out point, so
CloudWatch is a *removable output*, not the source of truth. Removing it fully removes CloudWatch
from the path (not just downstream) — the goal of getting off CloudWatch.

### Phase 0 — protect the app's EXISTING CloudWatch history (do this BEFORE the first switch)

⚠️ **Switching an app off Convox's native CloudWatch driver DELETES its Convox-managed LogGroup
and all its history** (verified — true for `LogDriver=Syslog` and `LogDriver=""`; Convox owns that
group and tears it down on the switch). So before `make enable-syslog` on an app that has history
worth keeping, delete-protect its group first (no copy — nothing is moved):

```sh
make retain-loggroup STACK=<rack>-<app>      # e.g. STACK=gm-test-rails-demo
```

This sets `DeletionPolicy: Retain` on the app's managed LogGroup via a one-time CloudFormation
update, so the switch **orphans** the group (kept in place, same name, all history) instead of
deleting it — CloudFormation logs `DELETE_SKIPPED LogGroup`, zero data moved. Afterward the
original group remains as a historical archive and the agent writes new logs to `/convox/<app>`.

Helper: `retain-loggroup.sh` — agent-agnostic (pure AWS), run once per app before you flip it to syslog.

### Phase 1 → Phase 2 (single-write)

1. Delete the `cloudwatch_logs` `[OUTPUT]` block in `fluent-bit.conf` (clearly fenced with a
   `DUAL-WRITE ONLY` banner).
2. Drop the agent's CloudWatch IAM: `convox apps params set IamPolicy="" -a oodle-log-agent -r <rack>`.
3. `make deploy`.

Oodle keeps flowing throughout; no app is touched. To cut a *specific* app over first, only its
`LogDriver` is changed (`make enable-syslog TARGET_APP=<app>`), so the switch is per-app and reversible.

## The problem it solves

Convox's `LogDriver=Syslog` runs Docker's syslog driver with **no `tag`**, so the rfc5424
`APP-NAME` field carries only the **container short-id** (e.g. `02a2b9e2f2c0`), not the app
name — and there is no Convox param to set the tag. A single shared agent therefore can't tell
apps apart from the payload alone.

Fluent Bit's **`ecs` filter** resolves that short-id to ECS task metadata (the app name) by
querying the **ECS Agent introspection API**. The catch on Convox: agents run in ECS **bridge**
networking, so the introspection endpoint is NOT reachable on `127.0.0.1:51678` (the container's
own loopback). It **is** reachable on the **docker bridge gateway `172.17.0.1:51678`** (verified
on `gm-test`), which is what `ECS_Meta_Host` points at.

## Pipeline

```
app (LogDriver=Syslog, dest tcp://localhost:5140)
   │  Docker syslog rfc5424: APP-NAME = container short-id
   ▼
Fluent Bit agent (agent: one per host, host port 5140)
   syslog input ──▶ rewrite_tag (short-id -> tag) ──▶ ecs filter (introspection @172.17.0.1:51678)
                 ──▶ lua (clean app name -> Oodle canonical `service`)
   ├─ cloudwatch_logs ──▶ /convox/<app>            (Phase 1 only — one group per app, auto-created)
   └─ http            ──▶ Oodle /ingest/v1/logs    (JSON, gzip, per Oodle's logs_fluent_bit spec)
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

After this, `service = <app>` is a first-class filter in the Oodle Logs Explorer / CLI.

## Files

- `fluent-bit.conf` — the pipeline (syslog in → rewrite_tag → ecs → lua → cloudwatch_logs + http + debug stdout).
- `parsers-convox.conf` — rfc5424 parser for Convox's Docker syslog output (names the app-name group `appname`).
- `derive_app.lua` — reduces the ECS family to a clean app name and maps to `service`/`container_id`.
- `Dockerfile` — `aws-for-fluent-bit` (has syslog/ecs/cloudwatch_logs/http built in) + the config.
- `convox.yml` — agent on host port 5140; env `OODLE_INSTANCE`, `OODLE_API_KEY`, `RACK_PREFIX`.
- `Makefile` — deploy + enable/disable an app's syslog + logs/ps/down/clean.

## Usage

```sh
cp .env.example .env               # fill OODLE_INSTANCE / OODLE_API_KEY / RACK_PREFIX (never committed)
make up                            # create app, grant IAM (CloudWatch write), deploy the agent
make enable-syslog                 # point rails-demo's logs at this agent (add TARGET_APP=<app> for others)
make logs                          # watch enriched records (debug stdout shows service/task_*)
make disable-syslog                # revert the app to native CloudWatch
```

Deploy the agent **before** enabling syslog on any app (the app's syslog driver needs something
listening on the host port, or its containers fail to start). Oodle host/key are passed only via
`convox env` — **never committed**. The debug `stdout` output in `fluent-bit.conf` is optional;
remove it in production to halve the agent's own log volume.

## Validated end to end (gm-test)

- ECS introspection reachable from a bridge-mode agent at `172.17.0.1:51678`; `/v1/tasks` is host-scoped.
- Live rails-demo traffic: container short-id `02a2b9e2f2c0` → `service=rails-demo` per record.
- CloudWatch group `/convox/rails-demo` auto-created with the enriched records (Phase 1).
- Oodle HTTP output `HTTP status=200`; records filterable by `service=rails-demo` via the `oodle` CLI.

## Notes / limitations

- **EC2 launch type only** — the `ecs` filter's introspection API is not available on Fargate.
- `172.17.0.1` is the Docker default bridge gateway (stable on the ECS-optimized AMI). If a rack
  uses a non-default bridge, derive the gateway at start instead of hardcoding.
- `convox scale collector --count 0` does NOT stop an agent (DaemonSet) — use `make down` (which
  deletes the app) to actually stop it.
- Non-rfc5424 lines (occasional Convox framing) fail the parser and are dropped — harmless.
