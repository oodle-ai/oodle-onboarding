# oodle-log-agent — dual-write Convox logs to CloudWatch + Oodle

Ships `rails-demo`'s logs to **both CloudWatch and Oodle** with **no application code
changes**, using a host-local OpenTelemetry Collector as the fan-out point.

## Why this shape

Convox v2's default `LogDriver=CloudWatch` makes CloudWatch the source of truth — anything
downstream (Firehose, subscription filters, an OTel `awscloudwatch` receiver) keeps
CloudWatch permanently load-bearing. Instead we make the **collector** the fan-out:

```
each EC2 instance in the rack:
  rails-demo containers' stdout/stderr
     │  Convox APP param on rails-demo only: LogDriver=Syslog, SyslogDestination=tcp://localhost:5140
     ▼
  OTel Collector  (Convox agent — agent.enabled:true → one per host, binds host port 5140)
     ├─ exporter awscloudwatchlogs ─▶ CloudWatch   ← delete this to drop CloudWatch later
     └─ exporter otlphttp/oodle ────▶ Oodle  /ingest/otel/v1/logs
```

- **No app changes** — logs leave via Convox's per-app Syslog log driver (a param), not the app.
- **Collector owns fan-out** — CloudWatch is one exporter. Remove it + redeploy and CloudWatch
  is out of the *ingestion path* entirely; Oodle keeps flowing.
- **Host-local** — the driver targets `localhost:5140`, delivered to the agent on the same
  host. No TLS, no cross-host endpoint, no rack-wide dependency.

## Scope & tradeoff

The syslog driver is set as a **per-app parameter on `rails-demo`** (not rack-wide), so:
- Only `rails-demo`'s logs redirect to the collector.
- **`convox logs -a rails-demo` stops working** (its logs go via syslog now).
- Every other app on the rack — and the agent itself — keeps CloudWatch and `convox logs`.

## Files

| File | Purpose |
|------|---------|
| `otel-collector-config.yaml` | syslog receiver (rfc5424) → `awscloudwatchlogs` + `otlphttp/oodle` |
| `convox.yml` | Convox agent (`agent.enabled: true` + nested `ports`) binding host port 5140 |
| `Dockerfile` | `otel/opentelemetry-collector-contrib` + baked config |
| `Makefile` | `up` / `enable-syslog` / `disable-syslog` / `down` / `clean` |
| `.env.example` | `OODLE_INSTANCE`, `OODLE_API_KEY`, `RACK`, `APP` |

## Deploy

```bash
cd convox-demo/oodle-log-agent
cp .env.example .env          # fill in OODLE_INSTANCE / OODLE_API_KEY
make up                       # create app, grant IAM, deploy agent, switch rails-demo to syslog
```

`make up` runs, in order:
1. `convox apps create` + `convox env set OODLE_INSTANCE/OODLE_API_KEY`
2. `convox apps params set IamPolicy=…CloudWatchAgentServerPolicy` — task role for the CW exporter
3. `convox deploy` — **agent must be running before logs redirect**
4. `convox apps params set LogDriver=Syslog SyslogDestination=tcp://localhost:5140 … -a rails-demo`

## Verify

```bash
make ps                                   # one collector per rack instance, all running
curl https://<rails-demo-endpoint>/       # generate traffic
oodle logs query --query 'rails-demo' ... # logs appear in Oodle
aws logs tail "$CW_LOG_GROUP" --region us-east-1          # same raw logs in CloudWatch
```

## Drop CloudWatch later

Remove the `awscloudwatchlogs` exporter (and its entry in the `logs` pipeline) from
`otel-collector-config.yaml`, then `make deploy`. Oodle keeps receiving; CloudWatch stops.
No app changes, no rack changes.

## Roll back

```bash
make disable-syslog   # rails-demo → LogDriver=CloudWatch, restores `convox logs -a rails-demo`
make clean            # also delete the agent app
```

## CloudWatch group & format parity

The collector writes the CloudWatch copy to the **same group name the native Convox `awslogs`
driver used** (set via `CW_LOG_GROUP`, e.g. `gm-test-rails-demo-LogGroup-…`), in the **same raw
format** — a `transform` processor drops the syslog envelope so each event is the original Rails
stdout line (not OTel JSON). So existing dashboards / metric filters / queries keep working.

Because **this exporter owns the group (not Convox CloudFormation)**, it is **not deleted when
the app toggles `LogDriver`** — unlike Convox's native per-app group. It's created never-expire,
so history is retained.

> ⚠️ **One-time caveat:** switching an app *off* the native CloudWatch driver makes Convox delete
> **its** managed group (`gm-test-<app>-LogGroup-…`) and the logs in it — CloudWatch deletion is
> irreversible. For a real migration, **export/snapshot the native group first** (e.g. to S3), then
> switch. After the switch, this collector-owned group persists across toggles.
>
> Note: `convox logs -a <app>` still won't work once the app is on Syslog (Convox has no group for
> it); use `aws logs tail "$CW_LOG_GROUP"` or the Oodle UI instead.

## Migrating an existing app without losing history

Switching a Convox app off the CloudWatch driver **deletes its Convox-managed LogGroup and all
its history** by default — verified: both `LogDriver=""` and `LogDriver=Syslog` delete it.

### Recommended: logical retain (no copy) — verified

Set `DeletionPolicy: Retain` on the managed LogGroup **before** switching. CloudFormation then
**skips the delete** (`DELETE_SKIPPED LogGroup`) and *orphans* the group — it stays in place with
the **same name, all history, and retention**, just no longer Convox-managed. No log data is
moved. Point the collector at that same group and it appends new logs to it.

```bash
# 1. Retain the app's managed LogGroup (one-time CFN update; stack name is "<rack>-<app>").
./retain-loggroup.sh gm-test-rails-demo us-east-1
#    or:  make retain-loggroup STACK=gm-test-rails-demo

# 2. Point the collector at the SAME group name and deploy.
convox env set CW_LOG_GROUP=<that-managed-group-name> -a oodle-log-agent -r <rack>
make deploy

# 3. Switch the app to syslog. CloudFormation retains (orphans) the group; the collector
#    now appends new logs to it. History + new logs stay unified in one group.
make enable-syslog
```

Verified on a real Convox stack: after the switch the group survived (CFN logged
`DELETE_SKIPPED LogGroup`), kept its historical events, name, and retention, and was orphaned from
the stack (so it also survives all future `LogDriver` toggles).

### Alternative: copy/export the history out (when you can't touch the stack)

If you'd rather not modify the app's CloudFormation stack, copy history into a separate persistent
group before switching (then set `CW_LOG_GROUP` to it):

```bash
./preserve-history.sh <managed-group> <persistent-group> us-east-1   # recent logs (< 14 days)
```

`PutLogEvents` rejects events older than 14 days, so for older/large archives export the whole
group to S3 instead (no age limit, no CloudWatch group):

```bash
aws logs create-export-task --log-group-name <managed-group> --from 0 --to $(date +%s)000 \
  --destination <s3-bucket> --destination-prefix <managed-group>
```

## Notes

- **Gen-2 agent port syntax gotcha:** host ports must be declared under the `agent:` map
  (`agent: {enabled: true, ports: [5140/tcp]}`). The `agent: true` boolean with a top-level
  `ports:` is silently ignored on gen-2 ECS (no host port is published), so the syslog driver
  gets `connection refused` and rails-demo tasks fail to start.
- The syslog driver connects at container start; the **agent must already be listening** or
  the rails-demo tasks won't start. Deploy order in `make up` handles this.
- Convox's `rfc5424` syslog output parses cleanly with the OTel `syslog` receiver
  (`protocol: rfc5424`) — verified end-to-end. If a future format changes that, adjust
  `protocol` / `enable_octet_counting` in `otel-collector-config.yaml`.

## Verified

rails-demo → `LogDriver=Syslog` (`tcp://localhost:5140`) → host-local OTel agent → fan-out:
- **CloudWatch** — the original group (`$CW_LOG_GROUP`) receives the **raw Rails log lines**
  (same format as the native awslogs driver), never-expire retention.
- **Oodle** OTLP logs endpoint returns 200 and the collector reports no export errors.
- Port 5140 is bound host-local and reachable only within the VPC (`10.0.0.0/16`), not public.
