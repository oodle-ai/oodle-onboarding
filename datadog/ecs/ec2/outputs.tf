output "cluster_name" {
  description = "ECS cluster running the demo."
  value       = aws_ecs_cluster.main.name
}

output "agent_service_name" {
  description = "Datadog Agent daemon service name."
  value       = module.datadog_agent.service_name
}

output "app_task_definition_arn" {
  description = "ARN of the demo application task definition."
  value       = aws_ecs_task_definition.app.arn
}
