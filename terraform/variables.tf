variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "function_name" {
  description = "Lambda function name"
  type        = string
  default     = "llm-security-gateway"
}

variable "lambda_memory" {
  description = "Lambda memory in MB"
  type        = number
  default     = 256
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 60
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

# --- Gateway config (passed as Lambda env vars) ---

variable "gateway_api_keys" {
  description = "Comma-separated API keys for gateway clients"
  type        = string
  sensitive   = true
}

variable "upstream_base_url" {
  description = "Upstream LLM provider base URL"
  type        = string
  default     = "https://api.openai.com"
}

variable "upstream_api_key" {
  description = "API key for the upstream LLM provider"
  type        = string
  sensitive   = true
}

variable "injection_threshold" {
  description = "Prompt injection risk score threshold (0.0-1.0)"
  type        = string
  default     = "0.7"
}

variable "pii_action" {
  description = "PII detection action: redact, block, or log_only"
  type        = string
  default     = "redact"
}

variable "rate_limit_rpm" {
  description = "Rate limit: requests per minute per client"
  type        = string
  default     = "60"
}

# --- Phase 4: Bedrock + DynamoDB ---

variable "enable_bedrock" {
  description = "Enable AWS Bedrock provider support"
  type        = bool
  default     = false
}

variable "client_store_backend" {
  description = "Client config store backend"
  type        = string
  default     = "json"

  validation {
    condition     = contains(["json", "dynamodb"], var.client_store_backend)
    error_message = "client_store_backend must be 'json' or 'dynamodb'."
  }
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for client configs"
  type        = string
  default     = "llm-gateway-clients"
}
