# Garde-fou Bedrock « annonces » (tâche 4c, #118) : second avis sur les annonces collées que le
# classifieur ONNX bloque à tort. Seul le filtre d'attaque de prompt est actif (niveau classique :
# EN/FR/ES). Pas encore appelé par le service : la mesure (`python -m ml.guardrail_eval`) décide
# de la règle combinée avant tout changement de comportement en production.
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
# Toute modification du garde-fou publie une nouvelle version.
resource "aws_bedrock_guardrail_version" "annonces" {
  guardrail_arn = aws_bedrock_guardrail.annonces.guardrail_arn
  description   = "Filtre attaque de prompt, entree ${var.guardrail_prompt_attack_strength}"

  lifecycle {
    replace_triggered_by = [aws_bedrock_guardrail.annonces]
  }
}
