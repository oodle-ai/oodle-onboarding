variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Name prefix for every resource in the demo."
  type        = string
  default     = "ecs-apm"
}

variable "image_tag" {
  description = "Tag of the app images in ECR. Also sent as DD_VERSION."
  type        = string
  default     = "v1"
}

variable "dd_env" {
  description = "Datadog env tag (Unified Service Tagging)."
  type        = string
  default     = "demo"
}

################################################################################
# Datadog
################################################################################

variable "dd_api_key" {
  description = "Datadog API key. Pass via TF_VAR_dd_api_key."
  type        = string
  sensitive   = true
}

variable "dd_site" {
  description = "Datadog site, for example us5.datadoghq.com."
  type        = string
  default     = "us5.datadoghq.com"
}

variable "dd_agent_image" {
  description = "Datadog Agent image for the sidecar."
  type        = string
  default     = "public.ecr.aws/datadog/agent:7.84.1"
}

################################################################################
# Oodle dual-write. Off by default: phase 1 ships to Datadog only.
################################################################################

variable "oodle_dual_write" {
  description = "If true, the Datadog Agent also ships metrics and traces to Oodle."
  type        = bool
  default     = false
}

variable "oodle_instance_id" {
  description = "Oodle instance ID (inst-...). From `oodle integrations list -o json`."
  type        = string
  default     = ""
}

variable "oodle_collector_domain" {
  description = "Oodle collector domain. From `oodle integrations list -o json`."
  type        = string
  default     = ""
}

variable "oodle_api_key" {
  description = "Oodle ingestion API key. Pass via TF_VAR_oodle_api_key."
  type        = string
  default     = ""
  sensitive   = true
}
