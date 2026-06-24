variable "aws_region" {
  description = "AWS region to operate in."
  type        = string
  default     = "us-east-1"
}

variable "aws_account_id" {
  description = "The AWS account ID to connect to Datadog."
  type        = string
}

variable "dd_site" {
  description = "Datadog site. Defaults to US5 to match the integration setup guide."
  type        = string
  default     = "us5.datadoghq.com"
}

variable "dd_api_url" {
  description = "Datadog API URL for the configured site (US5 by default)."
  type        = string
  default     = "https://api.us5.datadoghq.com"
}

# Datadog account that Datadog uses to assume the integration IAM role.
# This principal is shared across the commercial sites (app/us3/us5).
variable "datadog_aws_account_principal" {
  description = "Datadog's AWS account principal used in the assume-role trust policy."
  type        = string
  default     = "arn:aws:iam::464622532012:root"
}
