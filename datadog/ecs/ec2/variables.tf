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
  description = "Subnets for the EC2 instance. Leave empty to use all subnets in vpc_id. The instance needs outbound internet (public subnets, or private + NAT) to register with ECS, pull images, and reach Datadog."
  type        = list(string)
  default     = []
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
  default     = "dd-ecs-ec2-demo"
}

variable "dd_env" {
  description = "Datadog environment tag (UST)."
  type        = string
  default     = "demo"
}

variable "instance_type" {
  description = "EC2 instance type backing the ECS cluster."
  type        = string
  default     = "t3.medium"
}
