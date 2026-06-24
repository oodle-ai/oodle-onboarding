# Datadog on Amazon ECS

Minimal Terraform demos that run a **single ECS task** instrumented with Datadog,
using the official
[`terraform-aws-ecs-datadog`](https://github.com/DataDog/terraform-aws-ecs-datadog)
module — in both ECS launch types.

| Directory | What it does |
|-----------|--------------|
| [`aws-integration/`](./aws-integration) | Account-level AWS↔Datadog integration (IAM role + `datadog_integration_aws_account`). Apply **once per AWS account**. |
| [`fargate/`](./fargate) | Single **Fargate** task; the module injects the Datadog Agent as a sidecar. |
| [`ec2/`](./ec2) | **EC2** launch type; the Agent runs as a daemon and apps reach it over a Unix socket. |

Each task runs Datadog's prebuilt demo apps (`apps-dogstatsd`, `apps-tracegen`),
so metrics, traces, and logs flow with no application code to build.

## Apply order

1. **`aws-integration/`** (recommended, once per account) — gives Datadog the
   CloudWatch + ECS metrics and resource metadata. Needs `DD_API_KEY` + `DD_APP_KEY`.
2. **`fargate/`** and/or **`ec2/`** — the actual ECS workloads. Each needs only a
   Datadog `DD_API_KEY` (passed as `TF_VAR_dd_api_key`).

The two flavors are independent — run either or both.

## Defaults

- **Datadog site:** US5 (`us5.datadoghq.com`). Override `dd_site` (and `dd_api_url`
  in `aws-integration/`) for other sites.
- **Networking:** uses the account's **default VPC** to stay minimal.
- **Region:** `us-east-1` (override `aws_region`).

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5
- AWS credentials with permission to manage ECS, EC2, and IAM
- A Datadog account with an **API key** (and an **Application key** for the
  integration step)

See each subdirectory's README for step-by-step usage and cleanup.
