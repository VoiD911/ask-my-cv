# Transaction Search : X-Ray écrit les spans dans CloudWatch Logs (activation : script dédié).
data "aws_iam_policy_document" "xray_to_logs" {
  statement {
    sid     = "TransactionSearchXRayAccess"
    actions = ["logs:PutLogEvents"]
    principals {
      type        = "Service"
      identifiers = ["xray.amazonaws.com"]
    }
    resources = [
      "arn:aws:logs:${var.region}:${local.account}:log-group:aws/spans:*",
      "arn:aws:logs:${var.region}:${local.account}:log-group:/aws/application-signals/data:*",
    ]
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:xray:${var.region}:${local.account}:*"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
  }
}

resource "aws_cloudwatch_log_resource_policy" "xray" {
  policy_name     = "ask-my-cv-transaction-search"
  policy_document = data.aws_iam_policy_document.xray_to_logs.json
}

# Filet de sécurité : le plafond applicatif (daily_cap_usd) reste la première barrière.
resource "aws_budgets_budget" "monthly" {
  name         = "ask-my-cv-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Hors crédits : sinon les crédits masquent la consommation réelle.
  cost_types {
    include_credit = false
    include_refund = false
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }

  # Alerte réelle (non prévisionnelle) : la consommation a effectivement dépassé le budget.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}

# Échecs du garde-fou « annonces » (#118) : délai dépassé ou erreur, le service garde alors la
# décision du classifieur (échec ouvert). Ligne `guardrail_status=error` écrite par pipeline.py.
resource "aws_cloudwatch_log_metric_filter" "guardrail_errors" {
  name           = "ask-my-cv-guardrail-errors"
  log_group_name = aws_cloudwatch_log_group.api.name
  pattern        = "\"guardrail_status=error\""

  metric_transformation {
    name          = "GuardrailErrors"
    namespace     = "AskMyCv"
    value         = "1"
    default_value = "0"
  }
}
