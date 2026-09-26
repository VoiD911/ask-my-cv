terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.66" }
  }
}

variable "region" {
  type    = string
  default = "ca-central-1"
}

# Sujet OIDC immuable de GitHub (IDs numériques du compte et du dépôt) :
# `gh api repos/<propriétaire>/<dépôt>/actions/oidc/customization/sub` → sub_claim_prefix.
# Un dépôt recréé sous le même nom n'hérite donc pas du rôle.
variable "github_oidc_sub_prefix" {
  type    = string
  default = "repo:VoiD911@15268916/ask-my-cv@1387821326"
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { project = "ask-my-cv", managed-by = "terraform", stack = "bootstrap" }
  }
}

data "aws_caller_identity" "me" {}

locals {
  account       = data.aws_caller_identity.me.account_id
  function_name = "ask-my-cv-api"
}

# --- État Terraform de la racine prod ---
resource "aws_s3_bucket" "state" {
  bucket = "ask-my-cv-tfstate-${local.account}"

  # Le bucket d'état est critique : on empêche sa destruction accidentelle.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Interdit tout accès au bucket d'état qui ne serait pas chiffré en transit (TLS).
resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Sid       = "DenyInsecureTransport",
      Effect    = "Deny",
      Principal = "*",
      Action    = "s3:*",
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"],
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.state]
}

# Purge les anciennes versions et les uploads multipart abandonnés pour limiter les coûts.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "versions-anciennes"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# --- Images de l'API ---
resource "aws_ecr_repository" "api" {
  name                 = "ask-my-cv"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }

  # Le registre d'images est critique : on empêche sa destruction accidentelle.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      # Seules les images taguées (SHA git) comptent : signatures et attestations cosign sont
      # des référents OCI sans tag, supprimés par ECR avec l'image qu'ils décrivent.
      description = "garder les 10 dernières images taguées"
      selection = {
        tagStatus      = "tagged"
        tagPatternList = ["*"]
        countType      = "imageCountMoreThan"
        countNumber    = 10
      }
      action = { type = "expire" }
    }]
  })
}

# --- Déploiement depuis GitHub Actions (OIDC, sans clé longue durée) ---
# Un seul fournisseur OIDC GitHub par compte AWS : s'il existe déjà, l'importer avec
# `terraform import aws_iam_openid_connect_provider.github arn:aws:iam::<compte>:oidc-provider/token.actions.githubusercontent.com`
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "deploy_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${var.github_oidc_sub_prefix}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "ask-my-cv-deploy"
  assume_role_policy   = data.aws_iam_policy_document.deploy_trust.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart",
      "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages",
    ]
    resources = [aws_ecr_repository.api.arn]
  }
  statement {
    sid       = "LambdaDeploy"
    actions   = ["lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:GetFunctionConfiguration"]
    resources = ["arn:aws:lambda:${var.region}:${local.account}:function:${local.function_name}"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
