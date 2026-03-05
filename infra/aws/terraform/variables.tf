# -----------------------------------------------------------------------------
# General Configuration
# -----------------------------------------------------------------------------

variable "company_prefix" {
  description = "Company prefix for resource naming"
  type        = string
  default     = "saasdog"
}

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

# -----------------------------------------------------------------------------
# Shared Infrastructure References (from shared-infrastructure project)
# -----------------------------------------------------------------------------

variable "shared_vpc_id" {
  description = "VPC ID from shared infrastructure"
  type        = string
}

variable "shared_public_subnet_ids" {
  description = "Public subnet IDs from shared infrastructure"
  type        = list(string)
}

variable "shared_private_subnet_ids" {
  description = "Private subnet IDs from shared infrastructure"
  type        = list(string)
}

variable "shared_ecs_cluster_arn" {
  description = "ECS cluster ARN from shared infrastructure"
  type        = string
}

variable "shared_ecs_cluster_name" {
  description = "ECS cluster name from shared infrastructure"
  type        = string
}

variable "shared_rds_endpoint" {
  description = "RDS endpoint from shared infrastructure"
  type        = string
}

variable "shared_rds_address" {
  description = "RDS address (hostname) from shared infrastructure"
  type        = string
}

variable "shared_rds_security_group_id" {
  description = "RDS security group ID from shared infrastructure"
  type        = string
}

variable "shared_rds_master_password_secret_arn" {
  description = "ARN of secret containing RDS master password"
  type        = string
}

# -----------------------------------------------------------------------------
# Database Configuration
# -----------------------------------------------------------------------------

variable "db_name" {
  description = "Database name for this application"
  type        = string
  default     = "integration_platform"
}

variable "db_username" {
  description = "Database username for this application"
  type        = string
  default     = "integration_platform"
}

# -----------------------------------------------------------------------------
# ECS Configuration
# -----------------------------------------------------------------------------

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

variable "image_tag" {
  description = "Docker image tag to deploy (set by CI/CD to git SHA)"
  type        = string
  default     = "latest"
}

# -----------------------------------------------------------------------------
# CI/CD Configuration
# -----------------------------------------------------------------------------

variable "github_repository" {
  description = "GitHub repository (format: owner/repo) for OIDC trust policy"
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Feature Flags
# -----------------------------------------------------------------------------

variable "enable_deletion_protection" {
  description = "Enable deletion protection for critical resources"
  type        = bool
  default     = false
}

