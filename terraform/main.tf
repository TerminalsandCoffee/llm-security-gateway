terraform {
  required_version = ">= 1.12.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Local state for development. Switch to S3 backend for production:
  # backend "s3" {
  #   bucket = "your-terraform-state-bucket"
  #   key    = "llm-security-gateway/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "llm-security-gateway"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
