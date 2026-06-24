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

- AWS credentials, and a **default VPC** in the target region (the demo uses it).
- A Datadog **API key**.
- (Recommended) Apply [`../aws-integration`](../aws-integration) once so AWS
  infrastructure metrics show up in Datadog too.

## Usage

```bash
export TF_VAR_dd_api_key=...      # Datadog API key

cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars (aws_region, dd_site if not US5)

terraform init
terraform apply
```

Within a couple of minutes the task starts and telemetry appears in Datadog:

- **APM**: <https://us5.datadoghq.com/apm/traces> — service `tracegen-app`
- **Metrics**: <https://us5.datadoghq.com/metric/explorer> — search `custom.metric`
- **Infrastructure / Containers**: filter by `team:demo`

## Cleanup

```bash
terraform destroy
```
