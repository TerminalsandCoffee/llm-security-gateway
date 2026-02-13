# --- DynamoDB Client Store (conditional) ---

resource "aws_dynamodb_table" "clients" {
  count = var.client_store_backend == "dynamodb" ? 1 : 0

  name         = "${var.dynamodb_table_name}-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "client_id"

  attribute {
    name = "client_id"
    type = "S"
  }

  attribute {
    name = "api_key"
    type = "S"
  }

  global_secondary_index {
    name            = "api_key_index"
    hash_key        = "api_key"
    projection_type = "ALL"
  }
}
