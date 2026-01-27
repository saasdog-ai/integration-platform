terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  # Uncomment to use S3 backend for state
  # backend "s3" {
  #   bucket         = "your-terraform-state-bucket"
  #   key            = "integration-platform/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "terraform-locks"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "integration-platform"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
