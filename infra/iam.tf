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
      aws_dynamodb_table.customer_agents.arn,
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

# IAM user for the Next.js website (Vercel), scoped to only the tables and
# actions website/lib/dynamo.ts actually calls: GetItem/PutItem/UpdateItem on
# portal_users, portal_invites, spark_status. No Query/Scan/Delete, and no
# access to customers/api_keys/entitlements/customer_agents (those stay
# reserved for the Spark admin agent's broader spark_admin policy above).
# Vercel can't assume an AWS IAM role, so this is a long-lived access key
# (rotate via `terraform taint aws_iam_access_key.website_deploy` + apply).
data "aws_iam_policy_document" "website_deploy" {
  statement {
    sid    = "WebsitePortalReadWrite"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ]
    resources = [
      aws_dynamodb_table.portal_users.arn,
      aws_dynamodb_table.portal_invites.arn,
      aws_dynamodb_table.spark_status.arn,
    ]
  }
}

resource "aws_iam_policy" "website_deploy" {
  name   = "${local.name_prefix}-website-deploy"
  policy = data.aws_iam_policy_document.website_deploy.json
}

resource "aws_iam_user" "website_deploy" {
  name = "${local.name_prefix}-website-deploy"
  path = "/service/"
}

resource "aws_iam_user_policy_attachment" "website_deploy" {
  user       = aws_iam_user.website_deploy.name
  policy_arn = aws_iam_policy.website_deploy.arn
}

resource "aws_iam_access_key" "website_deploy" {
  user = aws_iam_user.website_deploy.name
}
