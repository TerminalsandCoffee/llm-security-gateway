output "api_endpoint" {
  description = "API Gateway endpoint URL"
  value       = aws_apigatewayv2_api.gateway.api_endpoint
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.gateway.function_name
}

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.gateway.arn
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group for Lambda"
  value       = aws_cloudwatch_log_group.lambda.name
}

output "dynamodb_table_name" {
  description = "DynamoDB client config table name"
  value       = var.client_store_backend == "dynamodb" ? aws_dynamodb_table.clients[0].name : null
}

output "dynamodb_table_arn" {
  description = "DynamoDB client config table ARN"
  value       = var.client_store_backend == "dynamodb" ? aws_dynamodb_table.clients[0].arn : null
}
