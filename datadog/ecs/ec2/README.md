# Datadog Agent on ECS (EC2 launch type) → Oodle

Runs the Datadog Agent as a **daemon** on an EC2-backed ECS cluster and a
**single application task** that sends telemetry to it over a Unix Domain
Socket. The Agent ships all telemetry to **[Oodle](https://oodle.ai)** (not
Datadog). Uses the
[`ecs_ec2`](https://github.com/DataDog/terraform-aws-ecs-datadog/tree/main/modules/ecs_ec2)
module.

| Component | Image | Role |
|-----------|-------|------|
| `datadog-agent` (daemon) | `public.ecr.aws/datadog/agent` | One per instance; forwards metrics, traces, logs to Oodle |
| `dogstatsd-app` | `ghcr.io/datadog/apps-dogstatsd:main` | Custom metrics via DogStatsD (UDS) |
| `tracegen-app` | `ghcr.io/datadog/apps-tracegen:main` | APM traces (UDS) |

```
┌──────────────── EC2 container instance ────────────────┐
│  app task: dogstatsd-app ─┐                            │
│            tracegen-app  ─┤ (UDS socket volume)        │
│                           ▼                            │
│  datadog-agent (daemon) ──────────────→ Oodle          │
└─────────────────────────────────────────────────────────┘
```

The Agent ships only to Oodle: its **primary** metrics, logs, and traces
endpoints are overridden to point at your Oodle collectors (`DD_DD_URL`,
`DD_APM_DD_URL`, `DD_LOGS_CONFIG_LOGS_DD_URL`), and it authenticates with your
Oodle API key. No Datadog API key or account is required. (Orchestrator Explorer is
left off, since it ships to Datadog's process intake, which can't be redirected
to Oodle.)

## What it creates

- An ECS cluster plus **one EC2 instance** (ECS-optimized AMI) registered via an
  Auto Scaling Group in your `vpc_id`, with an instance profile for the ECS agent.
- The Datadog Agent daemon service (from the module).
- An application task definition + service (`desired_count = 1`) wired to the
  agent through the module's `dogstatsd_env_vars` / `apm_env_vars` outputs and
  the shared socket volume.

## Prerequisites

- AWS credentials and a **VPC** to deploy into (set `vpc_id`). Subnets need
  outbound internet (public, or private + NAT) so the instance can register with
  ECS, pull images, and reach Oodle.
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
# oodle_logs_collector_domain (and optionally aws_region / subnet_ids / instance_type).

terraform init
terraform apply
```

It takes a few minutes for the EC2 instance to join the cluster and for the
agent daemon + app task to start. Then telemetry appears in your Oodle instance
— metrics (search `custom.metric`), APM traces (service `tracegen-app`), and
logs. Confirm the integration is receiving with `oodle integrations list` (or
the Oodle UI).

## Cleanup

```bash
terraform destroy
```
