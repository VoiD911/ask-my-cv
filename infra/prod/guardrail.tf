# Garde-fou Bedrock « annonces » (tâche 4c, #118) : second avis sur les annonces collées que le
# classifieur ONNX laisse passer. Seul le filtre d'attaque de prompt est actif (niveau classique :
# EN/FR/ES). Appelé par le service (src/ask_my_cv/guardrail.py) sur les textes d'au moins 400
# caractères que le classifieur n'a pas bloqués ; règle choisie sur la mesure `ml.guardrail_eval`.
# ca-central-1 n'offre pas InvokeGuardrailChecks (sans ressource) : ressource + ApplyGuardrail.
resource "aws_bedrock_guardrail" "annonces" {
  name                      = "ask-my-cv-annonces"
  description               = "Second avis attaque de prompt sur les annonces collees"
  blocked_input_messaging   = "Contenu refuse."
  blocked_outputs_messaging = "Contenu refuse."

  content_policy_config {
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = var.guardrail_prompt_attack_strength
      output_strength = "NONE" # exigé par l'API pour PROMPT_ATTACK
    }
    tier_config {
      tier_name = "CLASSIC"
    }
  }
}

# Version publiée (immuable) : c'est elle que le service et la mesure appellent, jamais DRAFT.
# Toute modification du garde-fou publie une nouvelle version, créée AVANT la destruction de
# l'ancienne (create_before_destroy) : une version épinglée par le service ne disparaît jamais
# en cours d'apply ; les références (sorties, environnement Lambda) basculent dans le
# même apply, puis l'ancienne version est supprimée.
resource "aws_bedrock_guardrail_version" "annonces" {
  guardrail_arn = aws_bedrock_guardrail.annonces.guardrail_arn
  description   = "Filtre attaque de prompt, entree ${var.guardrail_prompt_attack_strength}"

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_bedrock_guardrail.annonces]
  }
}
