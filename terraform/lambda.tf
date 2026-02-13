# --- IAM Role ---

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.function_name}-${var.environment}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Least-privilege: only CloudWatch Logs
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Conditional: Bedrock InvokeModel
resource "aws_iam_role_policy" "bedrock" {
  count = var.enable_bedrock ? 1 : 0

  name = "${var.function_name}-${var.environment}-bedrock"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel"]
      Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/*"
    }]
  })
}

# Conditional: DynamoDB read-only access
resource "aws_iam_role_policy" "dynamodb" {
  count = var.client_store_backend == "dynamodb" ? 1 : 0

  name = "${var.function_name}-${var.environment}-dynamodb"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["dynamodb:GetItem", "dynamodb:Query"]
      Resource = [
        aws_dynamodb_table.clients[0].arn,
        "${aws_dynamodb_table.clients[0].arn}/index/*",
      ]
    }]
  })
}

# --- CloudWatch Log Group ---

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.function_name}-${var.environment}"
  retention_in_days = var.log_retention_days
}

# --- Lambda Function ---

resource "aws_lambda_function" "gateway" {
  function_name = "${var.function_name}-${var.environment}"
  role          = aws_iam_role.lambda.arn
  handler       = "src.lambda_handler.handler"
  runtime       = "python3.12"
  memory_size   = var.lambda_memory
  timeout       = var.lambda_timeout

  filename         = "${path.module}/../deployment.zip"
  source_code_hash = filebase64sha256("${path.module}/../deployment.zip")

  environment {
    variables = merge(
      {
        GATEWAY_API_KEYS    = var.gateway_api_keys
        UPSTREAM_BASE_URL   = var.upstream_base_url
        UPSTREAM_API_KEY    = var.upstream_api_key
        INJECTION_THRESHOLD = var.injection_threshold
        PII_ACTION          = var.pii_action
        RATE_LIMIT_RPM      = var.rate_limit_rpm
        LOG_LEVEL           = "INFO"
      },
      var.client_store_backend != "json" ? {
        CLIENT_STORE_BACKEND = var.client_store_backend
        DYNAMODB_TABLE_NAME  = "${var.dynamodb_table_name}-${var.environment}"
      } : {},
    )
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy_attachment.lambda_logs,
  ]
}
