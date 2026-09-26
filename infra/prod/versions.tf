terraform {
  required_version = ">= 1.10"
  required_providers {
    aws   = { source = "hashicorp/aws", version = "~> 6.66" }
    awscc = { source = "hashicorp/awscc", version = "~> 1.103" }
  }
  # bucket fourni à l'init : -backend-config="bucket=ask-my-cv-tfstate-<compte>"
  backend "s3" {
    key          = "prod/terraform.tfstate"
    region       = "ca-central-1"
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { project = "ask-my-cv", managed-by = "terraform", stack = "prod" }
  }
}

provider "awscc" {
  region = var.region
}

data "aws_caller_identity" "me" {}
