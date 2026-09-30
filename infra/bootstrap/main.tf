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
  default = "repo:VoiD911@15268916/ask-my-cv@1389934708"
}

# ARN de la distribution CloudFront (sortie distribution_arn de infra/prod). La distribution est
# créée par la racine prod, appliquée après l'amorçage : son ARN n'est pas connu au premier
# apply. Sans valeur, l'invalidation est limitée aux distributions du compte (préfixe
# arn:aws:cloudfront::<compte>:distribution/*, le compte n'en héberge qu'une) ; renseigner
# la variable puis réappliquer pour la restreindre à la seule distribution du site.
# Pas de source de données : elle échouerait tant que prod n'existe pas (dépendance circulaire).
variable "site_distribution_arn" {
  type     = string
  default  = null
  nullable = true
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
  # Même nom que aws_s3_bucket.site dans infra/prod/site.tf.
  site_bucket_arn = "arn:aws:s3:::ask-my-cv-site-${data.aws_caller_identity.me.account_id}"
  site_distribution_arn = coalesce(
    var.site_distribution_arn,
    "arn:aws:cloudfront::${data.aws_caller_identity.me.account_id}:distribution/*",
  )
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

# Confiance OIDC par environnement GitHub protégé (limité à main) : le rôle de déploiement
# n'accepte que `environment:production`, le rôle de nuit que `environment:nightly`.
locals {
  github_oidc_subjects = {
    deploy  = ["${var.github_oidc_sub_prefix}:environment:production"]
    nightly = ["${var.github_oidc_sub_prefix}:environment:nightly"]
  }
}

data "aws_iam_policy_document" "github_trust" {
  for_each = local.github_oidc_subjects
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
      values   = each.value
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "ask-my-cv-deploy"
  assume_role_policy   = data.aws_iam_policy_document.github_trust["deploy"].json
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
  # aws s3 sync --delete : liste le bucket, écrit et supprime les objets.
  statement {
    sid       = "SiteList"
    actions   = ["s3:ListBucket"]
    resources = [local.site_bucket_arn]
  }
  statement {
    sid       = "SiteWrite"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.site_bucket_arn}/*"]
  }
  # Invalidation après publication ; GetInvalidation pour `aws cloudfront wait invalidation-completed`.
  statement {
    sid       = "SiteInvalidate"
    actions   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
    resources = [local.site_distribution_arn]
  }
}

resource "aws_iam_role_policy" "deploy" {
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

# --- Nuit (red team + dérive) depuis GitHub Actions : CloudWatch Logs Insights (lecture), juge Bedrock ---
# Confiance distincte : environnement `nightly` (le rôle de déploiement n'accepte que `production`).
resource "aws_iam_role" "nightly" {
  name                 = "ask-my-cv-nightly"
  assume_role_policy   = data.aws_iam_policy_document.github_trust["nightly"].json
  max_session_duration = 3600
}

# Référence d'autorisation IAM (service CloudWatch Logs) : `logs:StartQuery` accepte le type de
# ressource `log-group` (ARN restreint à `aws/spans`) ; `logs:GetQueryResults` et `logs:StopQuery`
# ne définissent aucun type de ressource et n'acceptent donc que `*`.
data "aws_iam_policy_document" "nightly" {
  statement {
    sid       = "LogsInsightsStart"
    actions   = ["logs:StartQuery"]
    resources = ["arn:aws:logs:${var.region}:${local.account}:log-group:aws/spans:*"]
  }
  statement {
    sid       = "LogsInsightsResults"
    actions   = ["logs:GetQueryResults", "logs:StopQuery"]
    resources = ["*"]
  }
  # #122 : juge LLM de la suite de nuit (evals/judge.js), InvokeModel sans flux. Un profil
  # d'inférence inter-régions exige l'autorisation sur le profil ET sur le modèle de fondation
  # dans chaque région de destination ; le second énoncé n'accepte le modèle qu'à travers ce
  # profil (clé de condition bedrock:InferenceProfileArn), jamais en appel direct.
  statement {
    sid       = "JudgeViaUsProfile"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.judge_profile_arn]
  }
  statement {
    sid       = "JudgeModelThroughProfile"
    actions   = ["bedrock:InvokeModel"]
    resources = [for r in local.judge_destination_regions : "arn:aws:bedrock:${r}::foundation-model/${local.judge_model}"]
    condition {
      test     = "StringEquals"
      variable = "bedrock:InferenceProfileArn"
      values   = [local.judge_profile_arn]
    }
  }
}

# Juge : Claude Haiku 4.5, profil géographique US appelé depuis ca-central-1 (pas de profil
# `ca.` pour ce modèle ; `global.` pourrait router hors d'Amérique du Nord). Destinations du
# profil depuis ca-central-1 (fiche du modèle, documentation Bedrock) : ca-central-1,
# us-east-1, us-east-2, us-west-2.
locals {
  judge_model               = "anthropic.claude-haiku-4-5-20251001-v1:0"
  judge_profile_arn         = "arn:aws:bedrock:${var.region}:${local.account}:inference-profile/us.${local.judge_model}"
  judge_destination_regions = ["ca-central-1", "us-east-1", "us-east-2", "us-west-2"]
}

resource "aws_iam_role_policy" "nightly" {
  role   = aws_iam_role.nightly.id
  policy = data.aws_iam_policy_document.nightly.json
}
