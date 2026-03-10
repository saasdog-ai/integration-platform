# Bootstrap: Terraform State Infrastructure for GCP
# Run ONCE to create the GCS bucket for state storage.
# Usage:
#   cd bootstrap
#   terraform init
#   terraform apply -var="gcp_project_id=my-project"

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
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
  bucket_name = "${var.project_name}-tfstate-${var.environment}-${var.gcp_project_id}"
}

resource "google_storage_bucket" "terraform_state" {
  name          = local.bucket_name
  location      = var.gcp_region
  force_destroy = false

  versioning {
    enabled = true
  }

  uniform_bucket_level_access = true

  labels = {
    project     = var.project_name
    environment = var.environment
    managed-by  = "terraform-bootstrap"
  }

  lifecycle {
    prevent_destroy = true
  }
}

output "state_bucket_name" {
  description = "Name of the GCS bucket for Terraform state"
  value       = google_storage_bucket.terraform_state.name
}
