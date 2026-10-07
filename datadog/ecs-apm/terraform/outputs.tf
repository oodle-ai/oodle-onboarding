output "cluster_name" {
  description = "ECS cluster running the demo."
  value       = aws_ecs_cluster.main.name
}

output "ecr_repositories" {
  description = "ECR repository URL per service."
  value       = { for k, r in aws_ecr_repository.app : k => r.repository_url }
}

output "log_group" {
  description = "CloudWatch log group for every container."
  value       = aws_cloudwatch_log_group.main.name
}

output "oodle_dual_write" {
  description = "Whether the Agents also ship to Oodle."
  value       = var.oodle_dual_write
}
