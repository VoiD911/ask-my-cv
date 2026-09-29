locals {
  account       = data.aws_caller_identity.me.account_id
  function_name = "ask-my-cv-api"
  ssm_prefix    = "/ask-my-cv"
  ecr_url       = "${local.account}.dkr.ecr.${var.region}.amazonaws.com/ask-my-cv"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = 14
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = "ask-my-cv-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "api" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }
  statement {
    sid     = "ClaudeViaUsProfile"
    actions = ["bedrock:InvokeModelWithResponseStream"] # ConverseStream
    resources = concat(
      ["arn:aws:bedrock:${var.region}:${local.account}:inference-profile/us.${var.llm_model_arn_suffix}"],
      [for r in var.llm_destination_regions : "arn:aws:bedrock:${r}::foundation-model/${var.llm_model_arn_suffix}"],
    )
  }
  statement {
    sid       = "TitanEmbeddings"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/amazon.titan-embed-text-v2:0"]
  }
  statement {
    sid       = "GuardrailAnnonces" # #118 : pas encore appelé par le service
    actions   = ["bedrock:ApplyGuardrail"]
    resources = [aws_bedrock_guardrail.annonces.guardrail_arn]
  }
  statement {
    sid       = "VectorSearch"
    actions   = ["dynamodb:SearchVectors"]
    resources = [awscc_dynamodb_table.chunks.arn, "${awscc_dynamodb_table.chunks.arn}/index/*"]
  }
  statement {
    sid       = "Ledger"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.ledger.arn]
  }
  statement {
    sid       = "Traces"
    actions   = ["xray:PutSpans", "xray:PutSpansForIndexing", "xray:PutTraceSegments"] # OTLP : PutTraceSegments exigé (403 sans, vérifié en production)
    resources = ["*"]
  }
  statement {
    sid     = "Secrets"
    actions = ["ssm:GetParametersByPath"]
    resources = [
      "arn:aws:ssm:${var.region}:${local.account}:parameter${local.ssm_prefix}",
    ]
  }
}

resource "aws_iam_role_policy" "api" {
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

resource "aws_lambda_function" "api" {
  function_name                  = local.function_name
  role                           = aws_iam_role.api.arn
  package_type                   = "Image"
  image_uri                      = "${local.ecr_url}:${var.image_tag}"
  architectures                  = ["x86_64"]
  memory_size                    = 1024
  timeout                        = 60
  reserved_concurrent_executions = var.reserved_concurrency

  environment {
    variables = {
      ASK_SETTINGS   = "settings.aws.yaml"
      ASK_SSM_PREFIX = "${local.ssm_prefix}/"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.api.name
  }

  # Après la création, la CI déploie les nouvelles images (update-function-code).
  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [aws_iam_role_policy.api]
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "AWS_IAM" # seul CloudFront (OAC) peut l'appeler
  invoke_mode        = "RESPONSE_STREAM"
}
