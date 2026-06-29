# Oodle on Amazon ECS

Minimal Terraform demos that run a **single ECS task** instrumented with the
Datadog Agent, using the official
[`terraform-aws-ecs-datadog`](https://github.com/DataDog/terraform-aws-ecs-datadog)
module — in both ECS launch types. The Agent ships telemetry **only to Oodle**
(not Datadog): its primary metrics, logs, and traces endpoints are overridden to
point at your Oodle collectors, and it authenticates with your Oodle API key.

| Directory | What it does |
|-----------|--------------|
| [`fargate/`](./fargate) | Single **Fargate** task; the module injects the Datadog Agent as a sidecar. |
| [`ec2/`](./ec2) | **EC2** launch type; the Agent runs as a daemon and apps reach it over a Unix socket. |

Each task runs Datadog's prebuilt demo apps (`apps-dogstatsd`, `apps-tracegen`),
so metrics, traces, and logs flow with no application code to build.

The two flavors are independent — run either or both.

## Defaults

- **Networking:** deploys into the VPC you supply via `vpc_id` (e.g.
  `export TF_VAR_vpc_id=vpc-...`); subnets default to all subnets in that VPC and
  must have outbound internet. Applies to `fargate/` and `ec2/`.
- **Region:** `us-east-1` (override `aws_region`).

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5
- AWS credentials with permission to manage ECS, EC2, and IAM
- An Oodle account with an ingestion **API key** and an integration's collector
  domains (`oodle integrations list -o json`, `oodle api-keys list -o json`).

See each subdirectory's README for step-by-step usage and cleanup.
