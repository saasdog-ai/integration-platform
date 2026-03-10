# -----------------------------------------------------------------------------
# General Configuration
# -----------------------------------------------------------------------------

variable "company_prefix" {
  description = "Company prefix for resource naming"
  type        = string
  default     = "saasdog"
}

variable "gcp_project_id" {
  description = "GCP project ID"
  type        = string
}

variable "gcp_region" {
  description = "GCP region"
  type        = string
  default     = "us-east1"
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

variable "shared_vpc_connector_id" {
  description = "VPC Connector ID from shared infrastructure"
  type        = string
}

variable "shared_cloud_sql_connection_name" {
  description = "Cloud SQL connection name from shared infrastructure"
  type        = string
}

variable "shared_cloud_sql_private_ip" {
  description = "Cloud SQL private IP from shared infrastructure"
  type        = string
}

variable "shared_cloud_sql_master_password_secret_id" {
  description = "Secret Manager secret ID for Cloud SQL master password"
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

# -----------------------------------------------------------------------------
# Cloud Run Configuration
# -----------------------------------------------------------------------------

variable "cloud_run_cpu" {
  description = "Cloud Run CPU allocation (e.g., '1' for 1 vCPU)"
  type        = string
  default     = "1"
}

variable "cloud_run_memory" {
  description = "Cloud Run memory allocation"
  type        = string
  default     = "512Mi"
}

variable "cloud_run_min_instances" {
  description = "Minimum number of Cloud Run instances"
  type        = number
  default     = 0
}

variable "cloud_run_max_instances" {
  description = "Maximum number of Cloud Run instances"
  type        = number
  default     = 4
}

variable "container_port" {
  description = "Container port"
  type        = number
  default     = 8000
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

# -----------------------------------------------------------------------------
# Feature Flags
# -----------------------------------------------------------------------------

variable "enable_deletion_protection" {
  description = "Enable deletion protection for critical resources"
  type        = bool
  default     = false
}
