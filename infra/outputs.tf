output "api_endpoint" {
  description = "Customer API Gateway endpoint"
  value       = aws_apigatewayv2_api.customer.api_endpoint
}

output "dynamodb_tables" {
  description = "Control-plane DynamoDB table names"
  value       = local.tables
}

output "authorizer_function_name" {
  value = aws_lambda_function.authorizer.function_name
}

output "spark_admin_policy_arn" {
  description = "Attach this policy to the IAM principal used on the DGX Spark"
  value       = aws_iam_policy.spark_admin.arn
}

output "spark_origin_base_url" {
  value = var.spark_origin_base_url
}

output "portal_users_table" {
  description = "DynamoDB table for website username/password logins"
  value       = aws_dynamodb_table.portal_users.name
}

output "portal_invites_table" {
  description = "DynamoDB table for 24h portal signup invites"
  value       = aws_dynamodb_table.portal_invites.name
}

output "website_env_hints" {
  description = "Values to copy into website/.env after apply (do not commit secrets)"
  value = {
    ITAH_API_BASE_URL    = aws_apigatewayv2_api.customer.api_endpoint
    PORTAL_USERS_TABLE   = aws_dynamodb_table.portal_users.name
    PORTAL_INVITES_TABLE = aws_dynamodb_table.portal_invites.name
    AWS_REGION           = var.aws_region
  }
}
