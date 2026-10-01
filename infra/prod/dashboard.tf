# Tableau de bord privé de l'usage réel (#143) : requêtes Logs Insights sur les spans racine
# `ask` (aws/spans, Transaction Search), trafic public seulement (`xops.traffic`, posé par
# src/ask_my_cv/pipeline.py ; évaluations, tests de fumée et propriétaire sont `internal`).
# Aucun texte soumis : uniquement des attributs xops.* (longueur, langue, issue, coût).
# Coût : tableau de bord gratuit (3 premiers du compte, sinon 3 USD/mois) ; chaque
# rafraîchissement analyse aws/spans (quelques Mo, rétention 14 jours) à environ 0,005 USD/Go.
locals {
  dashboard_public = "SOURCE 'aws/spans' | filter name = \"ask\" and `attributes.xops.traffic` = \"public\""

  dashboard_log_widgets = [
    {
      title = "Requêtes et visiteurs distincts par jour (public)"
      view  = "bar"
      # deux agrégations : décompte exact (count_distinct est approximatif)
      query = <<-EOT
        ${local.dashboard_public}
        | stats count(*) as n by bin(1d) as jour, `attributes.xops.visitor` as visiteur
        | stats sum(n) as requetes, count(*) as visiteurs by jour
        | sort jour asc
      EOT
    },
    {
      title = "Questions et annonces collées par jour (annonce : guardrail_min_chars caractères ou plus)"
      view  = "timeSeries"
      query = <<-EOT
        ${local.dashboard_public}
        | fields `attributes.xops.kind` as genre
        | stats sum(genre = "question") as questions, sum(genre = "ad") as annonces by bin(1d)
      EOT
    },
    {
      title = "Attaques bloquées, refus et réponses retirées par jour"
      view  = "timeSeries"
      query = <<-EOT
        ${local.dashboard_public}
        | fields `attributes.xops.result` as issue, `attributes.xops.refusal` as refuse, `attributes.xops.withdrawn` as retiree
        | stats sum(issue = "injection_detected") as attaques_bloquees, sum(refuse) as refus, sum(retiree) as reponses_retirees, sum(issue = "rate_limited") as quota_atteint, sum(issue = "budget_exceeded") as plafond_atteint by bin(1d)
      EOT
    },
    {
      title = "Coût mesuré par jour (USD, public)"
      view  = "timeSeries"
      query = <<-EOT
        ${local.dashboard_public}
        | stats sum(`attributes.xops.cost_usd`) as cout_usd by bin(1d)
      EOT
    },
    {
      title = "Coût cumulé sur la période affichée (USD) : public et total, interne compris"
      view  = "table"
      query = <<-EOT
        SOURCE 'aws/spans' | filter name = "ask"
        | fields `attributes.xops.traffic` as trafic, `attributes.xops.cost_usd` as usd
        | stats sum(usd) as cout_usd, count(*) as requetes by trafic
      EOT
    },
    {
      title = "Latence des réponses servies, p50 et p95 (ms)"
      view  = "timeSeries"
      query = <<-EOT
        ${local.dashboard_public}
        | filter `attributes.xops.result` = "answered"
        | fields durationNano / 1000000 as ms
        | stats pct(ms, 50) as p50, pct(ms, 95) as p95 by bin(1d)
      EOT
    },
    {
      title = "Langue détectée (FR/EN)"
      view  = "pie"
      query = <<-EOT
        ${local.dashboard_public}
        | filter isPresent(`attributes.xops.language`)
        | stats count(*) as requetes by `attributes.xops.language` as langue
      EOT
    },
    {
      title = "Modèle, gabarit de prompt et détecteur servis"
      view  = "table"
      query = <<-EOT
        ${local.dashboard_public}
        | stats count(*) as requetes by `attributes.xops.model` as modele, `attributes.xops.template` as gabarit, `attributes.xops.model_version` as detecteur
        | sort requetes desc
      EOT
    },
    {
      title = "Trafic public et interne (vide : spans antérieurs à #143)"
      view  = "pie"
      query = <<-EOT
        SOURCE 'aws/spans' | filter name = "ask"
        | stats count(*) as requetes by `attributes.xops.traffic` as trafic
      EOT
    },
  ]
}

resource "aws_cloudwatch_dashboard" "usage" {
  dashboard_name = "ask-my-cv-usage"
  dashboard_body = jsonencode({
    widgets = concat(
      [{
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 2
        properties = {
          markdown = "## Usage réel de ${var.site_domain}\nTrafic public seulement (évaluations, tests de fumée et propriétaire exclus, voir `xops.traffic`). Aucun texte de question n'est conservé. Budget mensuel : ${var.monthly_budget_usd} USD ; résumé chaque lundi par courriel (.github/workflows/weekly.yml)."
        }
      }],
      [for i, w in local.dashboard_log_widgets : {
        type   = "log"
        x      = (i % 2) * 12
        y      = 2 + floor(i / 2) * 6
        width  = 12
        height = 6
        properties = {
          title  = w.title
          region = var.region
          view   = w.view
          query  = trimspace(w.query)
        }
      }],
      # Mois en cours contre budget : métrique de facturation (us-east-1), publiée seulement si
      # les alertes de facturation sont activées dans les préférences du compte.
      [{
        type   = "metric"
        x      = (length(local.dashboard_log_widgets) % 2) * 12
        y      = 2 + floor(length(local.dashboard_log_widgets) / 2) * 6
        width  = 12
        height = 6
        properties = {
          title   = "Facture estimée du mois contre budget (USD)"
          region  = "us-east-1"
          view    = "timeSeries"
          stat    = "Maximum"
          period  = 21600
          metrics = [["AWS/Billing", "EstimatedCharges", "Currency", "USD"]]
          annotations = {
            horizontal = [{ label = "Budget mensuel", value = var.monthly_budget_usd }]
          }
        }
      }],
    )
  })
}
