################################################################################
# Datadog on ECS (EC2 launch type).
#
# The ecs_ec2 module runs the Datadog Agent as a DAEMON service (one per
# instance) and exposes it to app containers over a Unix Domain Socket. We
# provide the cluster, a single EC2 container instance, and an app task that
# talks to the agent via the module's socket/env-var outputs.
################################################################################

provider "aws" {
  region = var.aws_region
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Latest ECS-optimized Amazon Linux 2 AMI.
data "aws_ssm_parameter" "ecs_ami" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2/recommended/image_id"
}

resource "aws_ecs_cluster" "main" {
  name = var.name_prefix
}

################################################################################
# EC2 capacity: one instance registered to the cluster via an ASG.
################################################################################

resource "aws_iam_role" "instance" {
  name = "${var.name_prefix}-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "instance" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.name_prefix}-instance-profile"
  role = aws_iam_role.instance.name
}

resource "aws_security_group" "instance" {
  name_prefix = "${var.name_prefix}-"
  description = "Egress for Datadog ECS EC2 demo instances"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_launch_template" "instance" {
  name_prefix   = "${var.name_prefix}-"
  image_id      = data.aws_ssm_parameter.ecs_ami.value
  instance_type = var.instance_type

  iam_instance_profile {
    arn = aws_iam_instance_profile.instance.arn
  }

  vpc_security_group_ids = [aws_security_group.instance.id]

  # Register the instance with our cluster.
  user_data = base64encode(<<-EOF
    #!/bin/bash
    echo "ECS_CLUSTER=${aws_ecs_cluster.main.name}" >> /etc/ecs/ecs.config
  EOF
  )
}

resource "aws_autoscaling_group" "instance" {
  name_prefix         = "${var.name_prefix}-"
  vpc_zone_identifier = data.aws_subnets.default.ids
  min_size            = 1
  max_size            = 1
  desired_capacity    = 1

  launch_template {
    id      = aws_launch_template.instance.id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "${var.name_prefix}-instance"
    propagate_at_launch = true
  }
}

################################################################################
# Datadog Agent daemon service (provided by the module).
################################################################################

module "datadog_agent" {
  # ecs_ec2 is not yet in a stable registry release (1.0.x ships ecs_fargate
  # only), so pin to the tag that introduced it.
  source = "git::https://github.com/DataDog/terraform-aws-ecs-datadog.git//modules/ecs_ec2?ref=v1.1.0-beta"

  dd_api_key = var.dd_api_key
  dd_site    = var.dd_site
  dd_tags    = "team:demo, owner:oodle-onboarding"

  dd_dogstatsd = {
    enabled                  = true
    origin_detection_enabled = true
  }
  dd_apm = {
    enabled = true
  }
  dd_log_collection = {
    enabled               = true
    container_collect_all = true
  }
  dd_orchestrator_explorer = {
    enabled = true
  }

  family       = "${var.name_prefix}-agent"
  network_mode = "bridge"

  create_service = true
  cluster_arn    = aws_ecs_cluster.main.arn
  service_name   = "${var.name_prefix}-agent"
}

################################################################################
# Application task: Datadog demo apps talking to the agent over UDS.
################################################################################

resource "aws_ecs_task_definition" "app" {
  family       = "${var.name_prefix}-app"
  network_mode = "bridge"

  container_definitions = jsonencode([
    {
      name      = "dogstatsd-app"
      image     = "ghcr.io/datadog/apps-dogstatsd:main"
      essential = true
      memory    = 256
      cpu       = 256
      environment = concat(
        module.datadog_agent.dogstatsd_env_vars,
        [
          { name = "DD_SERVICE", value = "dogstatsd-app" },
          { name = "DD_ENV", value = var.dd_env },
          { name = "DD_VERSION", value = "1.0.0" },
        ],
      )
      mountPoints = module.datadog_agent.app_dd_sockets_mount
    },
    {
      name      = "tracegen-app"
      image     = "ghcr.io/datadog/apps-tracegen:main"
      essential = true
      memory    = 256
      cpu       = 256
      environment = concat(
        module.datadog_agent.apm_env_vars,
        [
          { name = "DD_SERVICE", value = "tracegen-app" },
          { name = "DD_ENV", value = var.dd_env },
          { name = "DD_VERSION", value = "1.0.0" },
        ],
      )
      mountPoints = module.datadog_agent.app_dd_sockets_mount
    },
  ])

  # Shared UDS socket volume so the apps can reach the agent daemon.
  dynamic "volume" {
    for_each = module.datadog_agent.app_dd_sockets_volume
    content {
      name      = volume.value.name
      host_path = volume.value.host_path
    }
  }
}

resource "aws_ecs_service" "app" {
  name            = "${var.name_prefix}-app"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 1
  launch_type     = "EC2"

  # Make sure the agent daemon is scheduled before the app.
  depends_on = [module.datadog_agent, aws_autoscaling_group.instance]
}
