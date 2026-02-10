# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

# ALB
output "alb_dns_name" {
  description = "ALB DNS name"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "ALB Zone ID (for Route53)"
  value       = aws_lb.main.zone_id
}

# ECR
output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.app.repository_url
}

# ECS
output "ecs_cluster_arn" {
  description = "ECS cluster ARN (from shared infrastructure)"
  value       = local.ecs_cluster_arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = local.ecs_cluster_name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.app.name
}

# SQS
output "sqs_queue_url" {
  description = "SQS queue URL"
  value       = aws_sqs_queue.sync_jobs.url
}

output "sqs_queue_arn" {
  description = "SQS queue ARN"
  value       = aws_sqs_queue.sync_jobs.arn
}

output "sqs_dlq_url" {
  description = "SQS dead letter queue URL"
  value       = aws_sqs_queue.sync_jobs_dlq.url
}

# KMS
output "kms_key_id" {
  description = "KMS key ID for credential encryption"
  value       = aws_kms_key.credentials.key_id
}

output "kms_key_arn" {
  description = "KMS key ARN"
  value       = aws_kms_key.credentials.arn
}

# IAM
output "ecs_task_execution_role_arn" {
  description = "ECS task execution role ARN"
  value       = aws_iam_role.ecs_task_execution_role.arn
}

output "ecs_task_role_arn" {
  description = "ECS task role ARN"
  value       = aws_iam_role.ecs_task_role.arn
}

# Security Groups
output "alb_security_group_id" {
  description = "ALB security group ID"
  value       = aws_security_group.alb.id
}

output "ecs_security_group_id" {
  description = "ECS tasks security group ID"
  value       = aws_security_group.ecs_tasks.id
}
