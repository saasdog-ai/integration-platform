terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  backend "gcs" {}
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region

  default_labels = {
    project     = "integration-platform"
    environment = var.environment
    managed-by  = "terraform"
    company     = var.company_prefix
  }
}
