# Datadog on ECS (EC2 launch type)

Runs the Datadog Agent as a **daemon** on an EC2-backed ECS cluster and a
**single application task** that sends telemetry to it over a Unix Domain
Socket. Uses the
[`ecs_ec2`](https://github.com/DataDog/terraform-aws-ecs-datadog/tree/main/modules/ecs_ec2)
module.

| Component | Image | Role |
|-----------|-------|------|
| `datadog-agent` (daemon) | `public.ecr.aws/datadog/agent` | One per instance; forwards metrics, traces, logs |
| `dogstatsd-app` | `ghcr.io/datadog/apps-dogstatsd:main` | Custom metrics via DogStatsD (UDS) |
| `tracegen-app` | `ghcr.io/datadog/apps-tracegen:main` | APM traces (UDS) |

```
┌──────────────── EC2 container instance ────────────────┐
│  app task: dogstatsd-app ─┐                            │
│            tracegen-app  ─┤ (UDS socket volume)        │
│                           ▼                            │
│  datadog-agent (daemon) ──────────────→ Datadog US5    │
└─────────────────────────────────────────────────────────┘
```

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
  ECS, pull images, and reach Datadog.
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

It takes a few minutes for the EC2 instance to join the cluster and for the
agent daemon + app task to start. Then:

- **APM**: <https://us5.datadoghq.com/apm/traces> — service `tracegen-app`
- **Metrics**: <https://us5.datadoghq.com/metric/explorer> — search `custom.metric`
- **Infrastructure / Containers**: filter by `team:demo`

## Cleanup

```bash
terraform destroy
```
