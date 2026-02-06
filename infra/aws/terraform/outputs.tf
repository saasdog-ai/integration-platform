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

# =============================================================================
# Shared Infrastructure Outputs
# =============================================================================
# When this project creates infrastructure in standalone mode (use_shared_infra = false),
# it can export these values for other projects to use in shared mode.

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = local.ecs_cluster_name
}

output "ecs_security_group_id" {
  description = "ECS tasks security group ID"
  value       = local.ecs_security_group_id
}

output "alb_security_group_id" {
  description = "ALB security group ID"
  value       = local.alb_security_group_id
}

output "rds_security_group_id" {
  description = "RDS security group ID"
  value       = local.rds_security_group_id
}

output "db_credentials_secret_arn" {
  description = "Database credentials secret ARN"
  value       = local.db_credentials_secret_arn
  sensitive   = true
}

output "shared_infra_tfvars" {
  description = "Copy this into another project's terraform.tfvars to use shared infrastructure"
  value       = var.use_shared_infra ? "Already using shared infrastructure" : <<-EOT
# Shared Infrastructure Configuration
# Copy these values into another project's terraform.tfvars

use_shared_infra = true
shared_project_name = "${local.infra_name}"

# VPC & Networking
shared_vpc_id = "${local.vpc_id}"
shared_public_subnet_ids = ${jsonencode(local.public_subnet_ids)}
shared_private_subnet_ids = ${jsonencode(local.private_subnet_ids)}

# Security Groups
shared_alb_security_group_id = "${local.alb_security_group_id}"
shared_ecs_security_group_id = "${local.ecs_security_group_id}"
shared_rds_security_group_id = "${local.rds_security_group_id}"

# ECS Cluster
shared_ecs_cluster_arn = "${local.ecs_cluster_arn}"

# RDS
shared_rds_endpoint = "${local.rds_endpoint}"
shared_db_credentials_secret_arn = "${local.db_credentials_secret_arn}"

# KMS (optional - other project can create its own)
shared_kms_key_id = "${local.kms_key_id}"
EOT
}
