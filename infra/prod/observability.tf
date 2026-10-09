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

# Garde-fou « annonces » (#118) : lignes `guardrail_metrics <statut> <ms>` écrites par
# src/ask_my_cv/guardrail.py pour chaque appel (jamais de texte soumis).
# Échecs (délai dépassé, erreur, limitation) : échec ouvert isolé, puis disjoncteur fermé.
resource "aws_cloudwatch_log_metric_filter" "guardrail_errors" {
  name           = "ask-my-cv-guardrail-errors"
  log_group_name = aws_cloudwatch_log_group.api.name
  pattern        = "[marker = \"guardrail_metrics\", status = \"error\", ms]"

  metric_transformation {
    name          = "GuardrailErrors"
    namespace     = "AskMyCv"
    value         = "1"
    default_value = "0"
  }
}

# #150 : écriture du journal des échanges échouée (au mieux, sans effet sur le visiteur) :
# lignes `exchange_log_metrics error` de src/ask_my_cv/pipeline.py.
resource "aws_cloudwatch_log_metric_filter" "exchange_log_errors" {
  name           = "ask-my-cv-exchange-log-errors"
  log_group_name = aws_cloudwatch_log_group.api.name
  pattern        = "[marker = \"exchange_log_metrics\", status = \"error\"]"

  metric_transformation {
    name          = "ExchangeLogErrors"
    namespace     = "AskMyCv"
    value         = "1"
    default_value = "0"
  }
}

# Annonces refusées par le disjoncteur ouvert (service dégradé pour les annonces).
resource "aws_cloudwatch_log_metric_filter" "guardrail_unavailable" {
  name           = "ask-my-cv-guardrail-unavailable"
  log_group_name = aws_cloudwatch_log_group.api.name
  pattern        = "[marker = \"guardrail_metrics\", status = \"unavailable\", ms]"

  metric_transformation {
    name          = "GuardrailUnavailable"
    namespace     = "AskMyCv"
    value         = "1"
    default_value = "0"
  }
}

# Latence de chaque appel au garde-fou (p95/p99 par la console ou une alarme future).
resource "aws_cloudwatch_log_metric_filter" "guardrail_latency" {
  name           = "ask-my-cv-guardrail-latency"
  log_group_name = aws_cloudwatch_log_group.api.name
  pattern        = "[marker = \"guardrail_metrics\", status = \"pass\" || status = \"block\" || status = \"error\", ms]"

  metric_transformation {
    name      = "GuardrailLatency"
    namespace = "AskMyCv"
    value     = "$ms"
    unit      = "Milliseconds"
  }
}

# Aucun sujet SNS n'existait (le budget écrit directement à alert_email) : sujet des alarmes
# d'exploitation, abonnement courriel à confirmer une fois après le premier apply.
# Clé KMS gérée par le client (environ 1 USD par mois) : une alarme CloudWatch ne peut pas
# publier vers un sujet chiffré par la clé gérée par AWS (alias/aws/sns), dont la politique
# n'autorise pas cloudwatch.amazonaws.com.
data "aws_iam_policy_document" "alerts_key" {
  statement {
    sid       = "AccountAdministration"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${local.account}:root"]
    }
  }
  statement {
    sid       = "CloudWatchAlarmsPublish"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey*"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
  }
}

resource "aws_kms_key" "alerts" {
  description             = "Chiffrement du sujet SNS des alarmes ask-my-cv"
  enable_key_rotation     = true
  deletion_window_in_days = 7
  policy                  = data.aws_iam_policy_document.alerts_key.json
}

resource "aws_kms_alias" "alerts" {
  name          = "alias/ask-my-cv-alerts"
  target_key_id = aws_kms_key.alerts.key_id
}

resource "aws_sns_topic" "alerts" {
  name              = "ask-my-cv-alerts"
  kms_master_key_id = aws_kms_key.alerts.arn
}

data "aws_iam_policy_document" "alerts_topic" {
  statement {
    sid       = "CloudWatchAlarmsPublish"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:cloudwatch:${var.region}:${local.account}:alarm:ask-my-cv-*"]
    }
  }
}

resource "aws_sns_topic_policy" "alerts" {
  arn    = aws_sns_topic.alerts.arn
  policy = data.aws_iam_policy_document.alerts_topic.json
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "guardrail_errors" {
  alarm_name          = "ask-my-cv-guardrail-errors"
  alarm_description   = "Garde-fou annonces en echec (echec ouvert puis disjoncteur ferme) : verifier Bedrock ApplyGuardrail."
  namespace           = "AskMyCv"
  metric_name         = "GuardrailErrors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}
