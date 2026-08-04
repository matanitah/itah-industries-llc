# IAM policy for the DGX Spark admin agent (attach manually or via principal ARNs).

data "aws_iam_policy_document" "spark_admin" {
  statement {
    sid    = "ControlPlaneReadWrite"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      aws_dynamodb_table.customers.arn,
      aws_dynamodb_table.api_keys.arn,
      aws_dynamodb_table.entitlements.arn,
      aws_dynamodb_table.spark_status.arn,
      aws_dynamodb_table.portal_users.arn,
      aws_dynamodb_table.portal_invites.arn,
      "${aws_dynamodb_table.api_keys.arn}/index/*",
      "${aws_dynamodb_table.portal_users.arn}/index/*",
      "${aws_dynamodb_table.portal_invites.arn}/index/*",
    ]
  }

  statement {
    sid    = "OptionalInviteEmail"
    effect = "Allow"
    actions = [
      "ses:SendEmail",
      "ses:SendRawEmail",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "spark_admin" {
  name   = "${local.name_prefix}-spark-admin"
  policy = data.aws_iam_policy_document.spark_admin.json
}
