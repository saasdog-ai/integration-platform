# =============================================================================
# Local values - resolve shared vs standalone resources
# =============================================================================

locals {
  # Use shared or create standalone
  use_shared = var.use_shared_infra

  # VPC & Networking
  vpc_id             = local.use_shared ? var.shared_vpc_id : aws_vpc.main[0].id
  public_subnet_ids  = local.use_shared ? var.shared_public_subnet_ids : aws_subnet.public[*].id
  private_subnet_ids = local.use_shared ? var.shared_private_subnet_ids : aws_subnet.private[*].id

  # Security Groups
  alb_security_group_id = local.use_shared ? var.shared_alb_security_group_id : aws_security_group.alb[0].id
  ecs_security_group_id = local.use_shared ? var.shared_ecs_security_group_id : aws_security_group.ecs_tasks[0].id
  rds_security_group_id = local.use_shared ? var.shared_rds_security_group_id : aws_security_group.rds[0].id

  # ECS Cluster
  ecs_cluster_arn = local.use_shared ? var.shared_ecs_cluster_arn : aws_ecs_cluster.main[0].arn

  # RDS
  rds_endpoint              = local.use_shared ? var.shared_rds_endpoint : aws_db_instance.main[0].endpoint
  db_credentials_secret_arn = local.use_shared ? var.shared_db_credentials_secret_arn : aws_secretsmanager_secret.db_password[0].arn

  # KMS
  kms_key_id = local.use_shared ? var.shared_kms_key_id : aws_kms_key.credentials[0].key_id

  # Common tags
  common_tags = {
    Project     = var.app_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
