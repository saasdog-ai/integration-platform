# =============================================================================
# Outputs
# =============================================================================

output "mode" {
  description = "Deployment mode"
  value       = var.use_shared_infra ? "shared" : "standalone"
}

# VPC (only in standalone mode)
output "vpc_id" {
  description = "VPC ID"
  value       = local.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = local.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = local.private_subnet_ids
}

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
  description = "ECS cluster ARN"
  value       = local.ecs_cluster_arn
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.app.name
}

# RDS (only meaningful in standalone mode)
output "rds_endpoint" {
  description = "RDS endpoint"
  value       = local.rds_endpoint
}

# SQS (always project-specific)
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
  value       = local.kms_key_id
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
