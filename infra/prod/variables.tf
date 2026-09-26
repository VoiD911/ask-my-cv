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

# CSP du site (comportement par défaut). 'unsafe-inline' dans script-src : l'export statique
# Next.js injecte des scripts en ligne (données d'hydratation) ; sans lui l'hydratation casse.
# Provisoire : à resserrer au plan 1e-2 en remplaçant 'unsafe-inline' par les hashes
# ('sha256-...') des scripts en ligne mesurés dans web/out. style-src garde 'unsafe-inline'
# (styles en ligne de React Flow). connect-src 'self' : l'API est servie sous /api/ du même domaine.
variable "site_csp" {
  type        = string
  description = "En-tête Content-Security-Policy du site statique."
  default     = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
}
