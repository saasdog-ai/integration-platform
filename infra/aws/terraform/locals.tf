# -----------------------------------------------------------------------------
# Local Values
# -----------------------------------------------------------------------------

locals {
  # Resource naming
  name_prefix = "${var.company_prefix}-${var.app_name}"

  # Shared infrastructure references
  vpc_id                = var.shared_vpc_id
  public_subnet_ids     = var.shared_public_subnet_ids
  private_subnet_ids    = var.shared_private_subnet_ids
  ecs_cluster_arn       = var.shared_ecs_cluster_arn
  ecs_cluster_name      = var.shared_ecs_cluster_name
  rds_endpoint          = var.shared_rds_endpoint
  rds_address           = var.shared_rds_address
  rds_security_group_id = var.shared_rds_security_group_id

  # Common tags
  common_tags = {
    Project     = var.app_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Company     = var.company_prefix
  }
}
