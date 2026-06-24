output "integration_role_arn" {
  description = "ARN of the IAM role Datadog assumes for the AWS integration."
  value       = aws_iam_role.datadog.arn
}

output "external_id" {
  description = "External ID tying the IAM role trust to this Datadog integration."
  value       = datadog_integration_aws_account.main.auth_config.aws_auth_config_role.external_id
  sensitive   = true
}

output "aws_account_id" {
  description = "AWS account connected to Datadog."
  value       = datadog_integration_aws_account.main.aws_account_id
}
