# Datadog on ECS Fargate

Runs a **single Fargate task** instrumented with Datadog. The
[`ecs_fargate`](https://github.com/DataDog/terraform-aws-ecs-datadog/tree/main/modules/ecs_fargate)
module injects the Datadog Agent (plus a FireLens log router) as sidecars
alongside two of Datadog's demo apps:

| Container | Image | Emits |
|-----------|-------|-------|
| `dogstatsd-app` | `ghcr.io/datadog/apps-dogstatsd:main` | Custom metrics via DogStatsD |
| `tracegen-app` | `ghcr.io/datadog/apps-tracegen:main` | APM traces |
| `datadog-agent` (injected) | `public.ecr.aws/datadog/agent` | Forwards metrics, traces, logs to Datadog |

```
┌──────────────────── ECS Fargate task ────────────────────┐
│  dogstatsd-app ─DogStatsD┐                                │
│  tracegen-app  ─APM──────┤→ datadog-agent ──→ Datadog US5 │
│                          └─ logs (FireLens) ──→           │
└───────────────────────────────────────────────────────────┘
```

## Prerequisites

- AWS credentials and a **VPC** to deploy into (set `vpc_id`). Subnets need
  outbound internet (public, or private + NAT) to pull images and reach Datadog.
- A Datadog **API key**.
- (Recommended) Apply [`../aws-integration`](../aws-integration) once so AWS
  infrastructure metrics show up in Datadog too.

## Usage

```bash
export TF_VAR_dd_api_key=...      # Datadog API key
export TF_VAR_vpc_id=vpc-...      # VPC to deploy into

cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars (aws_region, dd_site if not US5, optional subnet_ids)

terraform init
terraform apply
```

Within a couple of minutes the task starts and telemetry appears in Datadog:

- **APM**: <https://us5.datadoghq.com/apm/traces> — service `tracegen-app`
- **Metrics**: <https://us5.datadoghq.com/metric/explorer> — search `custom.metric`
- **Infrastructure / Containers**: filter by `team:demo`

## Dual-write to Oodle (optional)

The injected Datadog Agent can ship the same metrics, logs, and traces to
[Oodle](https://oodle.ai) at the same time, using Datadog's native
`DD_ADDITIONAL_ENDPOINTS` / `DD_LOGS_CONFIG_ADDITIONAL_ENDPOINTS` /
`DD_APM_ADDITIONAL_ENDPOINTS` support — no app changes. Set `oodle_dual_write =
true` and supply your instance's collector domains + an ingestion API key.

Discover the values with the Oodle CLI:

```bash
oodle integrations list -o json   # collectorDomain, logsCollectorDomain, instance ID
oodle api-keys list -o json       # ingestion API key
```

Then:

```bash
export TF_VAR_dd_api_key=...
export TF_VAR_vpc_id=vpc-...
export TF_VAR_oodle_api_key=...   # Oodle ingestion key

terraform apply \
  -var="oodle_dual_write=true" \
  -var="oodle_instance_id=inst-xxxxxxxx" \
  -var="oodle_collector_domain=inst-xxxxxxxx.collector.oodle.ai" \
  -var="oodle_logs_collector_domain=inst-xxxxxxxx-logs.collector.oodle.ai"
```

The same telemetry then appears in both Datadog and your Oodle instance. Check
the Oodle side with `oodle integrations list` (or the Oodle UI).

## Cleanup

```bash
terraform destroy
```
