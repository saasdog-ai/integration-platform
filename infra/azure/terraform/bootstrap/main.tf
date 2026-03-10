# Bootstrap: Terraform State Infrastructure for Azure
# Run ONCE to create the Storage Account for state.
# Usage:
#   cd bootstrap
#   terraform init
#   terraform apply

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

variable "azure_location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "integration-platform"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

locals {
  # Azure storage account names: lowercase, no hyphens, max 24 chars
  storage_account_name = substr(replace("intplatformtfstate${var.environment}", "-", ""), 0, 24)
  rg_name              = "${var.project_name}-tfstate-${var.environment}"
}

resource "azurerm_resource_group" "terraform_state" {
  name     = local.rg_name
  location = var.azure_location

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform-bootstrap"
  }
}

resource "azurerm_storage_account" "terraform_state" {
  name                     = local.storage_account_name
  resource_group_name      = azurerm_resource_group.terraform_state.name
  location                 = azurerm_resource_group.terraform_state.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  blob_properties {
    versioning_enabled = true
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform-bootstrap"
  }
}

resource "azurerm_storage_container" "terraform_state" {
  name                  = "tfstate"
  storage_account_name  = azurerm_storage_account.terraform_state.name
  container_access_type = "private"
}

output "storage_account_name" {
  description = "Storage account for Terraform state"
  value       = azurerm_storage_account.terraform_state.name
}

output "container_name" {
  description = "Blob container for Terraform state"
  value       = azurerm_storage_container.terraform_state.name
}

output "resource_group_name" {
  description = "Resource group for Terraform state"
  value       = azurerm_resource_group.terraform_state.name
}
