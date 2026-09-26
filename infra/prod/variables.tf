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
