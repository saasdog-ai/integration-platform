# -----------------------------------------------------------------------------
# General Configuration
# -----------------------------------------------------------------------------

variable "company_prefix" {
  description = "Company prefix for resource naming"
  type        = string
  default     = "saasdog"
}

variable "azure_location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
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

variable "shared_resource_group_name" {
  description = "Resource group name from shared infrastructure"
  type        = string
}

variable "shared_vnet_id" {
  description = "VNet ID from shared infrastructure"
  type        = string
}

variable "shared_container_apps_environment_id" {
  description = "Container Apps Environment ID from shared infrastructure"
  type        = string
}

variable "shared_postgresql_fqdn" {
  description = "PostgreSQL FQDN from shared infrastructure"
  type        = string
}

variable "shared_key_vault_id" {
  description = "Key Vault ID from shared infrastructure"
  type        = string
}

variable "shared_key_vault_uri" {
  description = "Key Vault URI from shared infrastructure"
  type        = string
}

variable "shared_postgresql_password_secret_id" {
  description = "Key Vault secret ID for PostgreSQL master password"
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
# Container App Configuration
# -----------------------------------------------------------------------------

variable "container_app_cpu" {
  description = "Container App CPU allocation"
  type        = number
  default     = 0.25
}

variable "container_app_memory" {
  description = "Container App memory allocation"
  type        = string
  default     = "0.5Gi"
}

variable "container_app_min_replicas" {
  description = "Minimum number of Container App replicas"
  type        = number
  default     = 0
}

variable "container_app_max_replicas" {
  description = "Maximum number of Container App replicas"
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
