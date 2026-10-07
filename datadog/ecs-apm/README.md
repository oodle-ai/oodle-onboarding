# Datadog APM on ECS Fargate, with dual-write to Oodle

This demo runs three instrumented services on Amazon ECS Fargate in `us-east-1`.
Each task has a Datadog Agent sidecar, as Datadog documents for
[ECS Fargate](https://docs.datadoghq.com/integrations/ecs_fargate/).
In phase 1 the Agents send to Datadog only. In phase 2 the same Agents also send
metrics and APM data to Oodle. The application code does not change.

```
loadgen ──> storefront ──> orders ──> inventory ──> inventory-db (span)
            Python         Node.js     Go
            ddtrace        dd-trace    dd-trace-go v2
              │              │            │
              └── datadog-agent sidecar in every task (localhost:8126)
                        │
                        ├──> Datadog (us5.datadoghq.com)
                        └──> Oodle   (phase 2: additional endpoints)
```

| Service | Language | What it does |
|---|---|---|
| `storefront` | Python, Flask, `ddtrace-run` | Entry service. `POST /checkout` calls orders. A `loadgen` container in the same task sends about one checkout per second. |
| `orders` | Node.js, Express, `dd-trace` | `POST /orders` calls inventory. About 5% of orders fail with a simulated payment error. |
| `inventory` | Go, `dd-trace-go` v2 | `GET /inventory/{sku}` with a manual `inventory-db` span. An unknown SKU returns 404. |

The services find each other through Cloud Map DNS (`orders.ecs-apm.local`,
`inventory.ecs-apm.local`).

## Layout

| Path | Contents |
|---|---|
| `apps/` | The three services and their Dockerfiles. |
| `terraform/` | VPC, ECR, Cloud Map, IAM, SSM parameters, ECS cluster, task definitions, services. |
| `scripts/tf-env.sh` | Prints the `TF_VAR_*` values for Terraform from the Datadog `.env` file and the oodle CLI. |
| `Makefile` | `datadog`, `dual-write`, `status`, `logs`, `destroy`. |

## Prerequisites

- Terraform 1.5 or later, the AWS CLI, and Docker with `linux/arm64` builds.
- AWS credentials that can manage VPC, ECS, ECR, IAM, SSM, Cloud Map, and CloudWatch Logs.
- A Datadog API key. The Makefile reads `DD_API_KEY` and `DD_SITE` from
  `../single-write/.env`. Set `DD_ENV_FILE` to use a different file.
- For phase 2, an oodle CLI that you configured with `oodle configure`.

## Phase 1: Datadog only

```bash
make datadog
```

This target does three things:

1. It creates the ECR repositories.
2. It builds the three images for `linux/arm64` and pushes them. The tasks run on Graviton.
3. It applies the rest of the stack with `oodle_dual_write=false`.

Terraform starts `orders` and `inventory` first and waits until they are steady.
Then it starts `storefront`. If `storefront` starts before the other services
register in Cloud Map, its first DNS lookups fail and the failure can last for minutes.

The Agent sidecar gets these settings, as the Datadog Fargate guide describes:

| Variable | Value |
|---|---|
| `DD_API_KEY` | ECS secret from SSM Parameter Store |
| `DD_SITE` | `us5.datadoghq.com` |
| `ECS_FARGATE` | `true` |
| `DD_APM_ENABLED` | `true` |

Each app container gets `DD_SERVICE`, `DD_ENV`, `DD_VERSION`, and the matching
`com.datadoghq.tags.*` Docker labels. Datadog calls this Unified Service Tagging.
The apps do not set `DD_AGENT_HOST`. Containers in an `awsvpc` task share one
network namespace, so the tracers reach the Agent on `localhost:8126`.

To see the result in Datadog, open APM in `us5.datadoghq.com` and filter on `env:demo`.
Allow a few minutes for the services to appear in the Software Catalog. The Traces
explorer shows them sooner.

## Phase 2: dual-write to Oodle

```bash
make dual-write
```

`scripts/tf-env.sh` reads three Oodle values from the CLI:

| Value | Source |
|---|---|
| Instance ID | `instance` in `~/.oodle/config.yaml` |
| Collector domain | `collectorDomain` of the `DATADOG` entry in `oodle integrations list -o json` |
| API key | The key named `Ingestion API Key` in `oodle api-keys list -o json` |

You can override each value with `OODLE_INSTANCE`, `OODLE_COLLECTOR_DOMAIN`, or `OODLE_API_KEY`.

With `oodle_dual_write=true`, Terraform adds these settings to every Agent sidecar.
This follows `oodle integrations get-setup-spec datadog`:

| Variable | Value |
|---|---|
| `DD_ADDITIONAL_ENDPOINTS` | `{"https://<collector>/v1/datadog/<instance>":["<key>"]}` |
| `DD_APM_ADDITIONAL_ENDPOINTS` | `{"https://<collector>/v1/datadog_traces/<instance>":["<key>"]}` |
| `DD_USE_V3_API_SERIES_ENABLED` | `false` |

The two endpoint values contain the Oodle API key. Terraform stores them as SSM
SecureString parameters and passes them to the Agent as ECS secrets.

The sidecar also skips the `data-plane` service and sets
`DD_DATA_PLANE_PREFLIGHT_MODE=false`. In Agent 7.84, that process cannot parse
`DD_ADDITIONAL_ENDPOINTS` from an environment variable. It restarts in a loop and
writes the value, with the Oodle API key, to the container log. This step keeps the
key out of the logs.

To return to Datadog only, run `make datadog` again.

### What reaches Oodle

| Signal | Where to find it in Oodle |
|---|---|
| Agent and container metrics | Metrics with `ecs_cluster_name="ecs-apm"`, for example `container_cpu_usage` and `datadog_trace_agent_*`. |
| Spans | Traces explorer. One checkout gives one trace across `storefront`, `requests`, `orders`, `inventory`, and `inventory-db`. |
| APM stats | `dd_trace_stats_*` metrics per `service` and `resource`. These feed the Oodle Service Catalog. |

The stats arrive on the traces endpoint. The Agent has no separate stats setting.

Use these commands to make sure that the data arrives:

```bash
oodle integrations list -o json | jq '.[] | select(.type=="DATADOG") | .statusPerSignal'
oodle metrics query --query 'sum by (service) (rate(dd_trace_stats_hits{env="demo"}[5m]))'
oodle metrics query --query 'count(container_cpu_usage{ecs_cluster_name="ecs-apm"})'
oodle traces list --service inventory --start -5m --end now --limit 5
```

The first command shows `METRICS` and `TRACES` as `RECEIVING`. The second shows one
series per service: `storefront`, `requests` (the HTTP client span in storefront),
`orders`, `inventory`, and `inventory-db`. The last command returns traces.

## Operations

```bash
make status    # running and desired count per service
make logs      # tail all containers from CloudWatch Logs
```

## Cost and cleanup

The demo runs three Fargate tasks with 0.5 vCPU and 1 GB each on ARM64. It has no
NAT gateway and no load balancer. Logs are kept for one day.

To delete every resource, including the ECR images and the SSM parameters, run:

```bash
make destroy
```
