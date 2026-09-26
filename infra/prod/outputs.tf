output "site_url" { value = "https://${aws_cloudfront_distribution.site.domain_name}" }
output "function_name" { value = aws_lambda_function.api.function_name }
output "function_url" { value = aws_lambda_function_url.api.function_url }
output "site_bucket" { value = aws_s3_bucket.site.bucket }
output "distribution_id" { value = aws_cloudfront_distribution.site.id }
output "distribution_arn" { value = aws_cloudfront_distribution.site.arn }
# Enregistrement(s) CNAME à créer chez le registraire pour valider le certificat ACM.
output "site_cert_validation_records" {
  value = [for o in aws_acm_certificate.site.domain_validation_options : {
    name  = o.resource_record_name
    type  = o.resource_record_type
    value = o.resource_record_value
  }]
}
# Cible du CNAME job.stevelang.net chez le registraire.
output "site_cname_target" { value = aws_cloudfront_distribution.site.domain_name }
