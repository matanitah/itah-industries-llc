data "archive_file" "authorizer" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/authorizer"
  output_path = "${path.module}/build/authorizer.zip"
  excludes    = ["requirements.txt", "__pycache__", "*.pyc"]
}

resource "aws_iam_role" "authorizer" {
  name = "${local.name_prefix}-authorizer"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "authorizer_dynamo" {
  name = "${local.name_prefix}-authorizer-dynamo"
  role = aws_iam_role.authorizer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.customers.arn,
          aws_dynamodb_table.api_keys.arn,
          aws_dynamodb_table.entitlements.arn,
          aws_dynamodb_table.spark_status.arn,
          "${aws_dynamodb_table.api_keys.arn}/index/*",
        ]
      },
      # portal_users table is not read by the authorizer (website verifies passwords)
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_lambda_function" "authorizer" {
  function_name    = "${local.name_prefix}-authorizer"
  role             = aws_iam_role.authorizer.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.authorizer.output_path
  source_code_hash = data.archive_file.authorizer.output_base64sha256
  timeout          = 10

  environment {
    variables = {
      CUSTOMERS_TABLE     = aws_dynamodb_table.customers.name
      API_KEYS_TABLE      = aws_dynamodb_table.api_keys.name
      ENTITLEMENTS_TABLE  = aws_dynamodb_table.entitlements.name
      SPARK_STATUS_TABLE  = aws_dynamodb_table.spark_status.name
      PORTAL_SHARED_TOKEN = var.portal_shared_token
    }
  }
}
