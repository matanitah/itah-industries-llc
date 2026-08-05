resource "aws_apigatewayv2_api" "customer" {
  name          = "${local.name_prefix}-customer-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers = ["authorization", "content-type", "x-api-key"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_origins = ["*"]
    max_age       = 3600
  }
}

resource "aws_apigatewayv2_authorizer" "api_key" {
  api_id                            = aws_apigatewayv2_api.customer.id
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = aws_lambda_function.authorizer.invoke_arn
  identity_sources                  = ["$request.header.Authorization"]
  name                              = "api-key-authorizer"
  authorizer_payload_format_version = "2.0"
  authorizer_result_ttl_in_seconds  = 0
  enable_simple_responses           = true
}

resource "aws_lambda_permission" "authorizer_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.customer.execution_arn}/authorizers/${aws_apigatewayv2_authorizer.api_key.id}"
}

locals {
  origin = trimsuffix(var.spark_origin_base_url, "/")

  edge_header_params = var.edge_shared_token != "" ? {
    "append:header.x-itah-edge-token" = var.edge_shared_token
  } : {}

  customer_routes = {
    health = {
      route_key = "GET /v1/health"
      uri       = "${local.origin}/v1/health"
      method    = "GET"
    }
    llm_completions = {
      route_key = "POST /v1/llm/completions"
      uri       = "${local.origin}/v1/llm/completions"
      method    = "POST"
    }
    docling_health = {
      route_key = "GET /v1/docling/health"
      uri       = "${local.origin}/v1/docling/health"
      method    = "GET"
    }
    docling_convert = {
      route_key = "POST /v1/docling/convert"
      uri       = "${local.origin}/v1/docling/convert"
      method    = "POST"
    }
    agents_list = {
      route_key = "GET /v1/agents"
      uri       = "${local.origin}/v1/agents"
      method    = "GET"
    }
    agents_status = {
      route_key = "GET /v1/agents/{agent_slug}/status"
      uri       = "${local.origin}/v1/agents/{agent_slug}/status"
      method    = "GET"
    }
    agents_start = {
      route_key = "POST /v1/agents/{agent_slug}/start"
      uri       = "${local.origin}/v1/agents/{agent_slug}/start"
      method    = "POST"
    }
    agents_stop = {
      route_key = "POST /v1/agents/{agent_slug}/stop"
      uri       = "${local.origin}/v1/agents/{agent_slug}/stop"
      method    = "POST"
    }
    agents_dashboard_url = {
      route_key = "POST /v1/agents/{agent_slug}/dashboard-url"
      uri       = "${local.origin}/v1/agents/{agent_slug}/dashboard-url"
      method    = "POST"
    }
  }
}

resource "aws_apigatewayv2_integration" "spark_route" {
  for_each = local.customer_routes

  api_id                 = aws_apigatewayv2_api.customer.id
  integration_type       = "HTTP_PROXY"
  integration_method     = each.value.method
  integration_uri        = each.value.uri
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000

  request_parameters = local.edge_header_params
}

resource "aws_apigatewayv2_route" "spark_route" {
  for_each = local.customer_routes

  api_id             = aws_apigatewayv2_api.customer.id
  route_key          = each.value.route_key
  target             = "integrations/${aws_apigatewayv2_integration.spark_route[each.key].id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.api_key.id
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.customer.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 50
    throttling_rate_limit  = 20
  }
}
