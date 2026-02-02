variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "app_name" {
  description = "Application name"
  type        = string
  default     = "integration-platform"
}

# =============================================================================
# Shared Infrastructure Mode
# =============================================================================

variable "use_shared_infra" {
  description = "Use shared infrastructure (VPC, RDS, ECS cluster) instead of creating standalone"
  type        = bool
  default     = false
}

# Shared infra variables (required when use_shared_infra = true)
variable "shared_vpc_id" {
  description = "Shared VPC ID"
  type        = string
  default     = ""
}

variable "shared_public_subnet_ids" {
  description = "Shared public subnet IDs"
  type        = list(string)
  default     = []
}

variable "shared_private_subnet_ids" {
  description = "Shared private subnet IDs"
  type        = list(string)
  default     = []
}

variable "shared_alb_security_group_id" {
  description = "Shared ALB security group ID"
  type        = string
  default     = ""
}

variable "shared_ecs_security_group_id" {
  description = "Shared ECS tasks security group ID"
  type        = string
  default     = ""
}

variable "shared_rds_security_group_id" {
  description = "Shared RDS security group ID"
  type        = string
  default     = ""
}

variable "shared_ecs_cluster_arn" {
  description = "Shared ECS cluster ARN"
  type        = string
  default     = ""
}

variable "shared_rds_endpoint" {
  description = "Shared RDS endpoint"
  type        = string
  default     = ""
}

variable "shared_db_credentials_secret_arn" {
  description = "Shared DB credentials secret ARN"
  type        = string
  default     = ""
}

variable "shared_kms_key_id" {
  description = "Shared KMS key ID"
  type        = string
  default     = ""
}

# =============================================================================
# Standalone Infrastructure (used when use_shared_infra = false)
# =============================================================================

variable "vpc_cidr" {
  description = "CIDR block for VPC (standalone mode)"
  type        = string
  default     = "10.1.0.0/16" # Different from shared to avoid conflicts
}

variable "availability_zones" {
  description = "Availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "db_instance_class" {
  description = "RDS instance class (standalone mode)"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB (standalone mode)"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "integration_platform"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "postgres"
  sensitive   = true
}

# =============================================================================
# ECS Configuration
# =============================================================================

variable "ecs_task_cpu" {
  description = "ECS task CPU units"
  type        = number
  default     = 256
}

variable "ecs_task_memory" {
  description = "ECS task memory in MB"
  type        = number
  default     = 512
}

variable "ecs_desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 1
}

variable "container_port" {
  description = "Container port"
  type        = number
  default     = 8000
}

variable "enable_deletion_protection" {
  description = "Enable deletion protection for RDS and KMS"
  type        = bool
  default     = false
}

# =============================================================================
# CI/CD Configuration
# =============================================================================

variable "github_repository" {
  description = "GitHub repository (format: owner/repo) for OIDC trust policy"
  type        = string
  default     = ""
}
