################################################################################
# Datadog on ECS Fargate — single task running Datadog's demo apps.
#
# The ecs_fargate module wraps an aws_ecs_task_definition and injects the
# Datadog Agent (and a FireLens log router) as sidecars. We add the cluster,
# networking, and a one-task service to actually run it.
################################################################################

provider "aws" {
  region = var.aws_region
}

# Deploy into the provided VPC. If subnet_ids is empty, use all subnets in it.
data "aws_subnets" "selected" {
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }
}

locals {
  subnet_ids = length(var.subnet_ids) > 0 ? var.subnet_ids : data.aws_subnets.selected.ids

  # Oodle dual-write: extra Datadog Agent env vars that fan metrics, logs, and
  # traces out to Oodle's collectors alongside Datadog. See the datadog setup
  # spec: `oodle integrations get-setup-spec datadog`.
  oodle_dual_write_env = var.oodle_dual_write ? [
    {
      name  = "DD_ADDITIONAL_ENDPOINTS"
      value = jsonencode({ "https://${var.oodle_collector_domain}/v1/datadog/${var.oodle_instance_id}" = [var.oodle_api_key] })
    },
    {
      name  = "DD_LOGS_CONFIG_ADDITIONAL_ENDPOINTS"
      value = jsonencode([{ api_key = var.oodle_api_key, Host = var.oodle_logs_collector_domain, Port = 443, is_reliable = false }])
    },
    {
      name  = "DD_LOGS_CONFIG_FORCE_USE_HTTP"
      value = "true"
    },
    {
      name  = "DD_APM_ADDITIONAL_ENDPOINTS"
      value = jsonencode({ "https://${var.oodle_collector_domain}/v1/datadog_traces/${var.oodle_instance_id}" = [var.oodle_api_key] })
    },
  ] : []
}

resource "aws_ecs_cluster" "main" {
  name = var.name_prefix
}

# Egress-only security group; tasks pull images and reach Datadog over the internet.
resource "aws_security_group" "task" {
  name_prefix = "${var.name_prefix}-"
  description = "Egress for Datadog Fargate demo tasks"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

################################################################################
# Task definition (Datadog Agent injected by the module)
################################################################################

module "datadog_ecs_fargate_task" {
  source  = "DataDog/ecs-datadog/aws//modules/ecs_fargate"
  version = "~> 1.0"

  # Datadog configuration
  dd_api_key = var.dd_api_key
  dd_site    = var.dd_site
  dd_tags    = "team:demo, owner:oodle-onboarding"

  dd_service = var.name_prefix
  dd_env     = var.dd_env
  dd_version = "1.0.0"

  # Make sure the agent is up before the apps emit telemetry.
  dd_essential                     = true
  dd_is_datadog_dependency_enabled = true

  dd_dogstatsd = {
    enabled                  = true
    origin_detection_enabled = true
  }
  dd_apm = {
    enabled = true
  }
  dd_log_collection = {
    enabled = true
  }

  # Dual-write to Oodle (empty unless oodle_dual_write = true).
  dd_environment = local.oodle_dual_write_env

  # Task definition
  family                   = "${var.name_prefix}-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024

  container_definitions = jsonencode([
    {
      name      = "dogstatsd-app"
      image     = "ghcr.io/datadog/apps-dogstatsd:main"
      essential = false
    },
    {
      name      = "tracegen-app"
      image     = "ghcr.io/datadog/apps-tracegen:main"
      essential = false
    },
  ])
}

################################################################################
# Service — run a single task
################################################################################

resource "aws_ecs_service" "demo" {
  name            = "${var.name_prefix}-svc"
  cluster         = aws_ecs_cluster.main.id
  task_definition = module.datadog_ecs_fargate_task.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.subnet_ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = true
  }
}
