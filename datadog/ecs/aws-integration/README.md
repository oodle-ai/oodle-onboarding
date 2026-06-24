# Datadog AWS Integration (account-level)

Connects your AWS account to Datadog so it can pull CloudWatch metrics, resource
metadata, and ECS data. This is **account-level** — apply it **once per AWS
account**, independent of how many ECS demos you run.

Implements the official guide for the **US5** site:
<https://docs.datadoghq.com/integrations/guide/aws-terraform-setup/?tab=awscommercialcloud&site=us5>

## What it creates

- `datadog_integration_aws_iam_permissions` — Datadog's canonical permission list.
- IAM role `DatadogIntegrationRole` trusting Datadog's AWS account, scoped by an
  external ID, with the permission list attached as size-bounded managed policies
  plus the AWS-managed `SecurityAudit` policy.
- `datadog_integration_aws_account` — registers the role with Datadog.

## Prerequisites

- A Datadog **API key** and **Application key**
  (<https://app.datadoghq.com/organization-settings/api-keys>).
- AWS credentials with permission to manage IAM.

## Usage

```bash
export DD_API_KEY=...   # Datadog API key
export DD_APP_KEY=...   # Datadog application key

cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set aws_account_id (and aws_region)

terraform init
terraform apply
```

To target a different Datadog site, override `dd_site` and `dd_api_url` (see
`terraform.tfvars.example`).

## Cleanup

```bash
terraform destroy
```
