variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "vpc_id" {
  description = "VPC to deploy into. Pass via TF_VAR_vpc_id."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets for the task. Leave empty to use all subnets in vpc_id. Tasks need outbound internet (public subnets, or private + NAT) to pull images and reach Datadog."
  type        = list(string)
  default     = []
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

################################################################################
# Oodle — the Datadog Agent ships metrics, logs, and traces only to Oodle.
################################################################################

variable "oodle_instance_id" {
  description = "Oodle instance ID (e.g. inst-...). From `oodle integrations list -o json`."
  type        = string
}

variable "oodle_collector_domain" {
  description = "Oodle metrics/traces collector domain. From `oodle integrations list -o json`."
  type        = string
}

variable "oodle_logs_collector_domain" {
  description = "Oodle logs collector domain. From `oodle integrations list -o json`."
  type        = string
}

variable "oodle_api_key" {
  description = "Oodle ingestion API key. Pass via TF_VAR_oodle_api_key rather than committing it."
  type        = string
  sensitive   = true
}
