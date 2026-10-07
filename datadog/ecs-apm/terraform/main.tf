################################################################################
# Three-service APM demo on ECS Fargate.
#
#   loadgen -> storefront (Python) -> orders (Node.js) -> inventory (Go) -> inventory-db (span)
#
# Every task runs its app next to a Datadog Agent sidecar, as Datadog documents
# for Fargate: https://docs.datadoghq.com/integrations/ecs_fargate/
# The tracers send to localhost:8126 because containers in an awsvpc task share
# one network namespace. With oodle_dual_write = true the same Agent also ships
# metrics and traces to Oodle through its additional-endpoints settings.
################################################################################

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project = var.name_prefix
      Owner   = "oodle-onboarding"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  services = {
    storefront = { port = 8080, registry = false }
    orders     = { port = 8080, registry = true }
    inventory  = { port = 8080, registry = true }
  }

  app_env = {
    storefront = [{ name = "ORDERS_URL", value = "http://orders.${var.name_prefix}.local:8080" }]
    orders     = [{ name = "INVENTORY_URL", value = "http://inventory.${var.name_prefix}.local:8080" }]
    inventory  = []
  }
}

################################################################################
# Network: a small VPC with two public subnets. No NAT gateway, tasks get
# public IPs so they can pull images and reach Datadog and Oodle.
################################################################################

resource "aws_vpc" "main" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = var.name_prefix }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = var.name_prefix }
}

resource "aws_subnet" "public" {
  count                   = length(local.azs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.name_prefix}-public-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Tasks talk to each other on 8080 and to the internet. Nothing is exposed publicly.
resource "aws_security_group" "tasks" {
  name_prefix = "${var.name_prefix}-"
  description = "ECS APM demo tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Service-to-service HTTP"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

################################################################################
# Service discovery: orders.<prefix>.local and inventory.<prefix>.local
################################################################################

resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "${var.name_prefix}.local"
  vpc  = aws_vpc.main.id
}

resource "aws_service_discovery_service" "svc" {
  for_each = { for k, v in local.services : k => v if v.registry }
  name     = each.key

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records {
      type = "A"
      ttl  = 10
    }
    routing_policy = "MULTIVALUE"
  }

}

################################################################################
# Images, logs, secrets, IAM
################################################################################

resource "aws_ecr_repository" "app" {
  for_each     = local.services
  name         = "${var.name_prefix}/${each.key}"
  force_delete = true
}

resource "aws_cloudwatch_log_group" "main" {
  name              = "/ecs/${var.name_prefix}"
  retention_in_days = 1
}

# Keys reach the Agent as ECS secrets, so they never appear in the task definition.
resource "aws_ssm_parameter" "dd_api_key" {
  name  = "/${var.name_prefix}/dd-api-key"
  type  = "SecureString"
  value = var.dd_api_key
}

# The additional-endpoints values embed the Oodle API key, so the whole JSON is a secret.
resource "aws_ssm_parameter" "oodle_metrics_endpoints" {
  count = var.oodle_dual_write ? 1 : 0
  name  = "/${var.name_prefix}/dd-additional-endpoints"
  type  = "SecureString"
  value = jsonencode({
    "https://${var.oodle_collector_domain}/v1/datadog/${var.oodle_instance_id}" = [var.oodle_api_key]
  })

  lifecycle {
    precondition {
      condition     = var.oodle_instance_id != "" && var.oodle_collector_domain != "" && var.oodle_api_key != ""
      error_message = "oodle_dual_write needs oodle_instance_id, oodle_collector_domain and oodle_api_key."
    }
  }
}

resource "aws_ssm_parameter" "oodle_traces_endpoints" {
  count = var.oodle_dual_write ? 1 : 0
  name  = "/${var.name_prefix}/dd-apm-additional-endpoints"
  type  = "SecureString"
  value = jsonencode({
    "https://${var.oodle_collector_domain}/v1/datadog_traces/${var.oodle_instance_id}" = [var.oodle_api_key]
  })
}

resource "aws_iam_role" "execution" {
  name_prefix = "${var.name_prefix}-exec-"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_ssm" {
  name = "read-agent-secrets"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameters"]
      Resource = "arn:aws:ssm:${var.aws_region}:*:parameter/${var.name_prefix}/*"
    }]
  })
}

################################################################################
# Datadog Agent sidecar
################################################################################

locals {
  agent_env = concat(
    [
      { name = "DD_SITE", value = var.dd_site },
      { name = "ECS_FARGATE", value = "true" },
      { name = "DD_APM_ENABLED", value = "true" },
      { name = "DD_ENV", value = var.dd_env },
    ],
    var.oodle_dual_write ? [
      # Oodle reads the v2 series API. Without this, Agent 7.81+ sends v3 and
      # Oodle rejects the metric payloads.
      { name = "DD_USE_V3_API_SERIES_ENABLED", value = "false" },
      # See agent_command below.
      { name = "DD_DATA_PLANE_PREFLIGHT_MODE", value = "false" },
    ] : [],
  )

  # Agent 7.84 bundles agent-data-plane, which cannot parse DD_ADDITIONAL_ENDPOINTS
  # when it comes from an environment variable ("invalid type: string, expected a
  # map"). It restarts in a loop and prints the value, including the Oodle API key,
  # to the log. The core Agent parses it correctly and dual-ships. With
  # additional endpoints set, skip the data-plane service. Nothing in this demo
  # uses it: the core Agent still serves DogStatsD.
  agent_command = var.oodle_dual_write ? [
    "sh", "-c", "rm -rf /etc/services.d/data-plane && exec /bin/entrypoint.sh",
  ] : null

  agent_secrets = concat(
    [{ name = "DD_API_KEY", valueFrom = aws_ssm_parameter.dd_api_key.arn }],
    var.oodle_dual_write ? [
      { name = "DD_ADDITIONAL_ENDPOINTS", valueFrom = aws_ssm_parameter.oodle_metrics_endpoints[0].arn },
      { name = "DD_APM_ADDITIONAL_ENDPOINTS", valueFrom = aws_ssm_parameter.oodle_traces_endpoints[0].arn },
    ] : [],
  )

  agent_container = {
    name        = "datadog-agent"
    image       = var.dd_agent_image
    essential   = true
    command     = local.agent_command
    environment = local.agent_env
    secrets     = local.agent_secrets
    portMappings = [
      { containerPort = 8126, protocol = "tcp" },
      { containerPort = 8125, protocol = "udp" },
    ]
    healthCheck = {
      command     = ["CMD-SHELL", "agent health"]
      interval    = 10
      timeout     = 5
      retries     = 3
      startPeriod = 15
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.main.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "datadog-agent"
      }
    }
  }
}

################################################################################
# Task definitions and services
################################################################################

locals {
  # Sends a checkout every second and a catalog read every third second.
  loadgen_container = {
    name       = "loadgen"
    image      = "public.ecr.aws/docker/library/busybox:stable"
    essential  = false
    entryPoint = ["sh", "-c"]
    command = [<<-EOT
      i=0
      while true; do
        wget -q -O /dev/null --post-data '' http://localhost:8080/checkout 2>/dev/null
        [ $((i % 3)) -eq 0 ] && wget -q -O /dev/null http://localhost:8080/catalog
        i=$((i + 1))
        sleep 1
      done
    EOT
    ]
    dependsOn = [{ containerName = "storefront", condition = "START" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.main.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "loadgen"
      }
    }
  }
}

resource "aws_ecs_cluster" "main" {
  name = var.name_prefix
}

resource "aws_ecs_task_definition" "app" {
  for_each                 = local.services
  family                   = "${var.name_prefix}-${each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn

  # The images are built on Apple silicon; run them on Graviton.
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode(concat(
    [
      local.agent_container,
      {
        name      = each.key
        image     = "${aws_ecr_repository.app[each.key].repository_url}:${var.image_tag}"
        essential = true
        portMappings = [
          { containerPort = each.value.port, protocol = "tcp" },
        ]
        # Unified Service Tagging: env vars for the tracer, labels for the Agent.
        environment = concat(
          [
            { name = "DD_SERVICE", value = each.key },
            { name = "DD_ENV", value = var.dd_env },
            { name = "DD_VERSION", value = var.image_tag },
            { name = "DD_LOGS_INJECTION", value = "true" },
          ],
          local.app_env[each.key],
        )
        dockerLabels = {
          "com.datadoghq.tags.service" = each.key
          "com.datadoghq.tags.env"     = var.dd_env
          "com.datadoghq.tags.version" = var.image_tag
        }
        # Start the app only after the Agent is ready to accept traces.
        dependsOn = [{ containerName = "datadog-agent", condition = "HEALTHY" }]
        logConfiguration = {
          logDriver = "awslogs"
          options = {
            awslogs-group         = aws_cloudwatch_log_group.main.name
            awslogs-region        = var.aws_region
            awslogs-stream-prefix = each.key
          }
        }
      },
    ],
    each.key == "storefront" ? [local.loadgen_container] : [],
  ))
}

# orders and inventory start first. Terraform waits until their tasks run and are
# registered in Cloud Map, so storefront never caches a failed DNS lookup.
resource "aws_ecs_service" "backend" {
  for_each              = { for k, v in local.services : k => v if v.registry }
  name                  = each.key
  cluster               = aws_ecs_cluster.main.id
  task_definition       = aws_ecs_task_definition.app[each.key].arn
  desired_count         = 1
  launch_type           = "FARGATE"
  wait_for_steady_state = true

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }

  service_registries {
    registry_arn = aws_service_discovery_service.svc[each.key].arn
  }
}

resource "aws_ecs_service" "storefront" {
  name            = "storefront"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app["storefront"].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }

  depends_on = [aws_ecs_service.backend]
}

moved {
  from = aws_ecs_service.app["orders"]
  to   = aws_ecs_service.backend["orders"]
}

moved {
  from = aws_ecs_service.app["inventory"]
  to   = aws_ecs_service.backend["inventory"]
}

moved {
  from = aws_ecs_service.app["storefront"]
  to   = aws_ecs_service.storefront
}
