# LLM Security Gateway

A security proxy that sits between applications and LLM APIs (OpenAI, AWS Bedrock) to enforce authentication, rate limiting, content security policies, and response scanning — with real-time SSE streaming support.

<img width="1376" height="768" alt="image" src="https://github.com/user-attachments/assets/2a65e9ba-a755-4c60-a7c9-329d3a7486f2" />


**v0.5.0** | 168 tests | Zero security-module dependencies beyond stdlib

## Architecture

<img width="1376" height="768" alt="image" src="https://github.com/user-attachments/assets/ff09b96e-e4d1-4778-a8bd-375100a68541" />


**Local**: FastAPI + uvicorn | **Production**: API Gateway + Lambda (Terraform-managed)

The gateway mirrors the OpenAI `/v1/chat/completions` API, making it a drop-in proxy. Point your application's base URL at the gateway instead of OpenAI directly. Supports both standard and streaming (`stream: true`) requests.

## Features

- **Multi-provider** — route requests to OpenAI or AWS Bedrock per client
- **Per-client config** — API keys, rate limits, model allowlists, provider selection (JSON or DynamoDB)
- **Prompt injection detection** — 20 patterns across 4 categories with cumulative risk scoring
- **PII scanning** — SSN, credit card (Luhn-validated), email, phone, IPv4 — redact, block, or log
- **Response scanning** — same injection + PII scanners run on LLM output before delivery
- **SSE streaming** — real-time token delivery with hybrid scan (forward chunks, hold `[DONE]` for scan)
- **Structured audit logging** — JSON lines with request ID correlation, pipeline results, latency
- **AWS-native deployment** — Lambda + API Gateway + CloudWatch via Terraform, CI/CD via GitHub Actions

## Quick Start (Local)

```bash
cd llm-security-gateway
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your upstream API key

uvicorn src.main:app --reload
```

## Deploy to AWS

### Prerequisites
- AWS CLI configured with credentials
- Terraform >= 1.12

### Steps

```bash
# 1. Build the Lambda deployment package
bash scripts/package.sh

# 2. Configure Terraform variables
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set gateway_api_keys and upstream_api_key

# 3. Deploy
terraform init
terraform plan
terraform apply
```

Terraform outputs the API Gateway endpoint URL. Use it as your base URL:

```bash
curl https://your-api-id.execute-api.us-east-1.amazonaws.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-gateway-key" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hello"}]}'
```

### CI/CD (GitHub Actions)

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `ci.yml` | Push/PR to main | Lint (ruff), test, build deployment zip |
| `deploy.yml` | After CI passes on main | Terraform plan + apply |

**Required GitHub secrets**:
- `AWS_DEPLOY_ROLE_ARN` — IAM role ARN for OIDC auth
- `GATEWAY_API_KEYS` — comma-separated client API keys
- `UPSTREAM_API_KEY` — upstream LLM provider API key

**Optional GitHub vars**: `AWS_REGION`, `UPSTREAM_BASE_URL`, `ENVIRONMENT`

## Usage

```bash
# Health check
curl http://localhost:8000/health

# Standard request (mirrors OpenAI API)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-1" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello"}]
  }'

# Streaming request
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-1" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

## Security Pipeline

Each request passes through these stages in order:

| Stage | Description |
|-------|-------------|
| Authentication | Constant-time API key validation (`X-API-Key`). Per-client config via JSON or DynamoDB |
| Rate Limiting | Sliding window counter, per-client RPM. Returns `X-RateLimit-*` headers |
| Model Allowlist | Per-client model restrictions (empty = all allowed) |
| Injection Detection | Pattern scoring across 4 categories. Blocks at configurable threshold |
| PII Detection | Regex + Luhn for SSN, CC, email, phone, IP. Configurable: redact, block, or log |
| Lambda Guard | Rejects `stream: true` on Lambda (API Gateway + Mangum doesn't support SSE) |
| Forward | Routes to OpenAI or Bedrock based on client config. Streaming or non-streaming |
| Response Scan | Injection + PII scanners on LLM output. PII action configurable, injection always advisory |

### Injection Detection Categories

| Category | Examples | Weight |
|----------|----------|--------|
| Instruction Override | "ignore previous instructions", "forget your rules" | 0.3-0.5 |
| Role Manipulation | "you are now DAN", "jailbreak", "act as unrestricted" | 0.4-0.7 |
| Delimiter Injection | `<\|im_start\|>`, `[SYSTEM]`, `### system` | 0.3-0.6 |
| Context Manipulation | "bypass your restrictions", "no ethical guidelines" | 0.5-0.6 |

### PII Types Detected

| Type | Pattern | Redaction |
|------|---------|-----------|
| SSN | `123-45-6789` | `[REDACTED_SSN]` |
| Credit Card | 13-19 digits, Luhn-validated | `[REDACTED_CC]` |
| Email | Standard email format | `[REDACTED_EMAIL]` |
| Phone | US formats with separators | `[REDACTED_PHONE]` |
| IPv4 | Dotted quad notation | `[REDACTED_IP]` |

### Streaming + Response Scanning

For streaming requests, the gateway uses a **hybrid approach**:
1. Content chunks are forwarded to the client in real-time (no latency penalty)
2. Text deltas are accumulated in memory as they arrive
3. The `[DONE]` signal is held until the accumulated text is scanned
4. If the response scan triggers a block, an SSE error event replaces `[DONE]`

This balances real-time delivery with security scanning. Note that chunks reach the client before the scan completes — this is an inherent trade-off of streaming.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEWAY_API_KEYS` | `dev-key-1` | Comma-separated valid client API keys (legacy mode) |
| `UPSTREAM_BASE_URL` | `https://api.openai.com` | LLM provider base URL |
| `UPSTREAM_API_KEY` | (empty) | API key for the upstream provider |
| `INJECTION_THRESHOLD` | `0.7` | Risk score at which to block requests (0.0-1.0) |
| `PII_ACTION` | `redact` | Action on input PII: `redact`, `block`, or `log_only` |
| `RESPONSE_PII_ACTION` | `log_only` | Action on output PII: `redact`, `block`, or `log_only` |
| `RATE_LIMIT_RPM` | `60` | Default max requests per minute per client |
| `CLIENT_STORE_BACKEND` | `json` | Client config backend: `json` or `dynamodb` |
| `CLIENT_CONFIG_PATH` | `clients.json` | Path to JSON client config file |
| `DYNAMODB_TABLE_NAME` | `llm-gateway-clients` | DynamoDB table name (when using dynamodb backend) |
| `AWS_REGION` | `us-east-1` | AWS region for Bedrock and DynamoDB |
| `LOG_LEVEL` | `INFO` | Logging level |
| `AUDIT_LOG_FILE` | (empty) | Optional file path for audit logs |

## Design Decisions

- **OpenAI-compatible API surface** — mirrors `/v1/chat/completions` for drop-in proxying
- **Constant-time key comparison** — `hmac.compare_digest` prevents timing attacks
- **Structured JSON logging** — 12-factor compliant, stdout-based, SIEM-ingestible
- **Sequential security pipeline** — each module returns an allow/deny dataclass with metadata
- **Luhn validation on credit cards** — reduces false positives mathematically
- **Zero extra deps for security modules** — injection, PII, rate limiting use only stdlib
- **Response PII defaults to log_only** — blocking LLM output is high false-positive; operators opt in
- **Injection in responses always advisory** — same rationale; logged but never blocked
- **Provider registry with lazy imports** — no boto3 loaded for OpenAI-only setups
- **HTTP API Gateway v2** — cheaper and lower latency than REST API for proxy workloads
- **OIDC for CI/CD** — GitHub Actions assumes AWS role, no long-lived access keys

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/ -v --tb=short
```

168 tests across 17 files. Runs in ~1.6s.

## Roadmap

- [x] **Phase 1**: HTTP proxy, authentication, structured logging
- [x] **Phase 2**: Prompt injection detection, PII scanning, rate limiting
- [x] **Phase 3**: AWS Lambda + API Gateway deployment, Terraform IaC, GitHub Actions CI/CD
- [x] **Phase 4**: AWS Bedrock provider, per-client key management, DynamoDB client store
- [x] **Phase 5**: SSE streaming, response scanning (input + output security)
