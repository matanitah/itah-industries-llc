resource "aws_dynamodb_table" "customers" {
  name         = local.tables.customers
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "customer_id"

  attribute {
    name = "customer_id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "api_keys" {
  name         = local.tables.api_keys
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "key_hash"

  attribute {
    name = "key_hash"
    type = "S"
  }

  attribute {
    name = "customer_id"
    type = "S"
  }

  global_secondary_index {
    name            = "customer_id-index"
    hash_key        = "customer_id"
    projection_type = "ALL"
  }
}

resource "aws_dynamodb_table" "entitlements" {
  name         = local.tables.entitlements
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "customer_id"
  range_key    = "scope"

  attribute {
    name = "customer_id"
    type = "S"
  }

  attribute {
    name = "scope"
    type = "S"
  }
}

resource "aws_dynamodb_table" "spark_status" {
  name         = local.tables.spark_status
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "portal_users" {
  name         = local.tables.portal_users
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "username"

  attribute {
    name = "username"
    type = "S"
  }

  attribute {
    name = "customer_id"
    type = "S"
  }

  global_secondary_index {
    name            = "customer_id-index"
    hash_key        = "customer_id"
    projection_type = "ALL"
  }
}

# Single-use 24h account-creation invites (token_hash PK; TTL on expires_epoch).
resource "aws_dynamodb_table" "portal_invites" {
  name         = local.tables.portal_invites
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "token_hash"

  attribute {
    name = "token_hash"
    type = "S"
  }

  attribute {
    name = "email"
    type = "S"
  }

  ttl {
    attribute_name = "expires_epoch"
    enabled        = true
  }

  global_secondary_index {
    name            = "email-index"
    hash_key        = "email"
    projection_type = "ALL"
  }
}
