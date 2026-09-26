output "state_bucket" { value = aws_s3_bucket.state.bucket }
output "ecr_repository_url" { value = aws_ecr_repository.api.repository_url }
output "deploy_role_arn" { value = aws_iam_role.deploy.arn }
