output "site_url" { value = "https://${aws_cloudfront_distribution.site.domain_name}" }
output "function_name" { value = aws_lambda_function.api.function_name }
output "function_url" { value = aws_lambda_function_url.api.function_url }
