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
aws logs tail /oodle-demo/rails-demo --region us-east-1   # same logs in CloudWatch
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
- **CloudWatch** `/oodle-demo/rails-demo` receives the parsed logs (structured + resource tags).
- **Oodle** OTLP logs endpoint returns 200 and the collector reports no export errors.
- Port 5140 is bound host-local and reachable only within the VPC (`10.0.0.0/16`), not public.
