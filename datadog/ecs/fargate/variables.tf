variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "dd_api_key" {
  description = "Datadog API key. Pass via TF_VAR_dd_api_key rather than committing it."
  type        = string
  sensitive   = true
}

variable "dd_site" {
  description = "Datadog site. Defaults to US5 to match the integration setup."
  type        = string
  default     = "us5.datadoghq.com"
}

variable "name_prefix" {
  description = "Name prefix for the demo resources."
  type        = string
  default     = "dd-ecs-fargate-demo"
}

variable "dd_env" {
  description = "Datadog environment tag (UST)."
  type        = string
  default     = "demo"
}
