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

output "customer_agents_table" {
  description = "DynamoDB table for which agent-spark agents a customer is entitled to"
  value       = aws_dynamodb_table.customer_agents.name
}

output "website_deploy_access_key_id" {
  description = "AWS_ACCESS_KEY_ID for Vercel env vars (website_deploy IAM user)"
  value       = aws_iam_access_key.website_deploy.id
}

output "website_deploy_secret_access_key" {
  description = "AWS_SECRET_ACCESS_KEY for Vercel env vars (website_deploy IAM user). Run `terraform output -raw website_deploy_secret_access_key` to print it; never commit it."
  value       = aws_iam_access_key.website_deploy.secret
  sensitive   = true
}

output "website_env_hints" {
  description = "Values to copy into website/.env after apply (do not commit secrets)"
  value = {
    ITAH_API_BASE_URL     = aws_apigatewayv2_api.customer.api_endpoint
    PORTAL_USERS_TABLE    = aws_dynamodb_table.portal_users.name
    PORTAL_INVITES_TABLE  = aws_dynamodb_table.portal_invites.name
    CUSTOMER_AGENTS_TABLE = aws_dynamodb_table.customer_agents.name
    AWS_REGION            = var.aws_region
  }
}
