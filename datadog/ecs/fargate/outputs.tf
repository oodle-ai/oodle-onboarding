output "cluster_name" {
  description = "ECS cluster running the demo."
  value       = aws_ecs_cluster.main.name
}

output "task_definition_arn" {
  description = "ARN of the Datadog-instrumented task definition."
  value       = module.datadog_ecs_fargate_task.arn
}

output "service_name" {
  description = "ECS service running the single demo task."
  value       = aws_ecs_service.demo.name
}
