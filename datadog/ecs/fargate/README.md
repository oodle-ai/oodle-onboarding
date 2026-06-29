# Datadog Agent on ECS Fargate → Oodle

Runs a **single Fargate task** instrumented with the Datadog Agent, shipping all
telemetry to **[Oodle](https://oodle.ai)** (not Datadog). The
[`ecs_fargate`](https://github.com/DataDog/terraform-aws-ecs-datadog/tree/main/modules/ecs_fargate)
module injects the Datadog Agent (plus a FireLens log router) as sidecars
alongside two of Datadog's demo apps:

| Container | Image | Emits |
|-----------|-------|-------|
| `dogstatsd-app` | `ghcr.io/datadog/apps-dogstatsd:main` | Custom metrics via DogStatsD |
| `tracegen-app` | `ghcr.io/datadog/apps-tracegen:main` | APM traces |
| `datadog-agent` (injected) | `public.ecr.aws/datadog/agent` | Forwards metrics, traces, logs to Oodle |

```
┌──────────────────── ECS Fargate task ────────────────────┐
│  dogstatsd-app ─DogStatsD┐                                │
│  tracegen-app  ─APM──────┤→ datadog-agent ──→ Oodle       │
│                          └─ logs (FireLens) ──→           │
└───────────────────────────────────────────────────────────┘
```

The Agent ships only to Oodle: its **primary** metrics, logs, and traces
endpoints are overridden to point at your Oodle collectors (`DD_DD_URL`,
`DD_APM_DD_URL`, `DD_LOGS_CONFIG_LOGS_DD_URL`), and it authenticates with your
Oodle API key. No Datadog API key or account is required.

## Prerequisites

- AWS credentials and a **VPC** to deploy into (set `vpc_id`). Subnets need
  outbound internet (public, or private + NAT) to pull images and reach Oodle.
- An **Oodle** account with an ingestion **API key** and an integration's
  collector domains. Discover them with the Oodle CLI:

  ```bash
  oodle integrations list -o json   # collectorDomain, logsCollectorDomain, instance ID
  oodle api-keys list -o json       # ingestion API key
  ```

## Usage

```bash
export TF_VAR_oodle_api_key=...   # Oodle ingestion key
export TF_VAR_vpc_id=vpc-...      # VPC to deploy into

cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set oodle_instance_id, oodle_collector_domain,
# oodle_logs_collector_domain (and optionally aws_region / subnet_ids).

terraform init
terraform apply
```

Within a couple of minutes the task starts and telemetry appears in your Oodle
instance — metrics (search `custom.metric`), APM traces (service
`tracegen-app`), and logs. Confirm the integration is receiving with
`oodle integrations list` (or the Oodle UI).

## Cleanup

```bash
terraform destroy
```
