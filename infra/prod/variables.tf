variable "region" {
  type    = string
  default = "ca-central-1"
}

variable "image_tag" {
  type        = string
  description = "Tag de l'image dans ECR pour la création de la fonction ; ensuite, la CI déploie."
}

variable "alert_email" {
  type        = string
  description = "Destinataire des alertes de budget."
}

variable "monthly_budget_usd" {
  type    = number
  default = 15
}

variable "reserved_concurrency" {
  type        = number
  default     = -1
  description = "-1 = non réservée (obligatoire tant que la concurrence du compte vaut 10)."
}

variable "llm_model_arn_suffix" {
  type    = string
  default = "anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "llm_destination_regions" {
  type    = list(string)
  default = ["ca-central-1", "us-east-1", "us-east-2", "us-west-2"]
}

variable "site_domain" {
  type        = string
  default     = "job.stevelang.net"
  description = "Nom de domaine du site (certificat ACM us-east-1 et alias CloudFront)."
}

# CSP du site (comportement par défaut). script-src garde 'self' 'unsafe-inline', mais ce
# 'unsafe-inline' est inopérant : chaque page de web/out porte en tête du <head> une balise
# <meta http-equiv="Content-Security-Policy" content="script-src 'self' 'sha256-...' ..."> insérée
# au build par web/scripts/csp.mjs (hashes des scripts en ligne de Next.js, propres à chaque page).
# Le navigateur applique les deux politiques (intersection) : un script en ligne ne s'exécute que
# si son hash figure dans la meta. Les hashes changent à chaque build : ils ne peuvent pas vivre
# dans cet en-tête, commun à toutes les pages et appliqué hors CI. Le serveur e2e
# (web/e2e/serve.mjs) lit cette valeur par défaut et la sert telle quelle : l'e2e éprouve
# l'intersection réelle. style-src garde 'unsafe-inline' (styles en ligne de React Flow).
# connect-src 'self' : l'API est servie sous /api/ du même domaine.
variable "site_csp" {
  type        = string
  description = "En-tête Content-Security-Policy du site statique."
  default     = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
}
