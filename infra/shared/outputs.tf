# =============================================================================
# VPC Outputs
# =============================================================================

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = aws_subnet.private[*].id
}

# =============================================================================
# Security Group Outputs
# =============================================================================

output "alb_security_group_id" {
  description = "ALB security group ID"
  value       = aws_security_group.alb.id
}

output "ecs_tasks_security_group_id" {
  description = "ECS tasks security group ID"
  value       = aws_security_group.ecs_tasks.id
}

output "rds_security_group_id" {
  description = "RDS security group ID"
  value       = aws_security_group.rds.id
}

# =============================================================================
# RDS Outputs
# =============================================================================

output "rds_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.main.endpoint
}

output "rds_address" {
  description = "RDS address (without port)"
  value       = aws_db_instance.main.address
}

output "rds_port" {
  description = "RDS port"
  value       = aws_db_instance.main.port
}

output "db_credentials_secret_arn" {
  description = "Database credentials secret ARN"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

# =============================================================================
# ECS Outputs
# =============================================================================

output "ecs_cluster_id" {
  description = "ECS cluster ID"
  value       = aws_ecs_cluster.main.id
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

# =============================================================================
# KMS Outputs
# =============================================================================

output "kms_key_id" {
  description = "KMS key ID"
  value       = aws_kms_key.credentials.key_id
}

output "kms_key_arn" {
  description = "KMS key ARN"
  value       = aws_kms_key.credentials.arn
}

# =============================================================================
# Helper Output (copy-paste for project tfvars)
# =============================================================================

output "project_tfvars_snippet" {
  description = "Copy this to your project's terraform.tfvars"
  value       = <<-EOT
    # Shared infrastructure configuration
    use_shared_infra = true

    shared_vpc_id                   = "${aws_vpc.main.id}"
    shared_public_subnet_ids        = ${jsonencode(aws_subnet.public[*].id)}
    shared_private_subnet_ids       = ${jsonencode(aws_subnet.private[*].id)}
    shared_alb_security_group_id    = "${aws_security_group.alb.id}"
    shared_ecs_security_group_id    = "${aws_security_group.ecs_tasks.id}"
    shared_rds_security_group_id    = "${aws_security_group.rds.id}"
    shared_ecs_cluster_arn          = "${aws_ecs_cluster.main.arn}"
    shared_rds_endpoint             = "${aws_db_instance.main.endpoint}"
    shared_db_credentials_secret_arn = "${aws_secretsmanager_secret.db_credentials.arn}"
    shared_kms_key_id               = "${aws_kms_key.credentials.key_id}"
  EOT
}
