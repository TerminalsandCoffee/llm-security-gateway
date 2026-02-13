# LLM Security Gateway

A security proxy that sits between applications and LLM APIs (OpenAI, AWS Bedrock) to enforce authentication, rate limiting, and content security policies.

**Built by Secure Cloud Academy**

## Architecture

```
                          ┌─────────────────────────────┐
                          │     LLM Security Gateway     │
                          │                              │
Client App ──► API GW ──►│  Auth ► RateLimit ► Inject  │──► LLM Provider
                          │  Scan ► PII Scan ► Forward  │    (OpenAI / Bedrock)
                          │         │                    │
                          │         ▼                    │
                          │    Audit Log (JSON)          │
                          └─────────────────────────────┘
                                    │
                          CloudWatch / SIEM
```

**Local**: FastAPI + uvicorn | **Production**: API Gateway + Lambda (Terraform-managed)

The gateway mirrors the OpenAI `/v1/chat/completions` API, making it a drop-in proxy. Point your application's base URL at the gateway instead of OpenAI directly.

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

# Proxy a chat completion (mirrors OpenAI API)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-key-1" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## Security Pipeline

Each request passes through these stages in order:

| Stage | Status | Description |
|-------|--------|-------------|
| Authentication | Active | Constant-time API key validation via `X-API-Key` header |
| Rate Limiting | Active | Sliding window counter, per-client by API key. Returns `X-RateLimit-*` headers |
| Injection Detection | Active | Pattern-based scoring across 4 categories. Blocks at configurable threshold |
| PII Detection | Active | Regex detection for SSN, credit card (Luhn-validated), email, phone, IPv4. Configurable: redact, block, or log-only |

### Injection Detection Categories

| Category | Examples | Weight |
|----------|----------|--------|
| Instruction Override | "ignore previous instructions", "forget your rules" | 0.3-0.5 |
| Role Manipulation | "you are now DAN", "jailbreak", "act as unrestricted" | 0.4-0.7 |
| Delimiter Injection | `<\|im_start\|>`, `[SYSTEM]`, `### system` | 0.3-0.6 |
| Context Manipulation | "bypass your restrictions", "no ethical guidelines" | 0.5-0.6 |

Patterns accumulate a risk score. Request is blocked when score >= `INJECTION_THRESHOLD` (default 0.7).

### PII Types Detected

| Type | Pattern | Redaction |
|------|---------|-----------|
| SSN | `123-45-6789` | `[REDACTED_SSN]` |
| Credit Card | 13-19 digits, Luhn-validated | `[REDACTED_CC]` |
| Email | Standard email format | `[REDACTED_EMAIL]` |
| Phone | US formats with separators | `[REDACTED_PHONE]` |
| IPv4 | Dotted quad notation | `[REDACTED_IP]` |

## Design Decisions

- **OpenAI-compatible API surface**: Mirrors `/v1/chat/completions` for drop-in proxying. Familiar to anyone who has used the OpenAI API.
- **Constant-time key comparison**: Uses `hmac.compare_digest` to prevent timing attacks on API key validation.
- **Structured JSON logging (stdout)**: 12-factor compliant. Logs are JSON lines on stdout, directly ingestible by CloudWatch, Elastic, Splunk, or any SIEM.
- **Security pipeline pattern**: Auth, rate limit, injection scan, and PII scan run as a sequential pipeline. Each module returns an allow/deny result with metadata.
- **Luhn validation on credit cards**: Reduces false positives by validating card numbers mathematically.
- **Zero extra dependencies for security modules**: Injection detection, PII scanning, and rate limiting use only stdlib.
- **HTTP API Gateway (v2)**: Cheaper and lower latency than REST API. Sufficient for proxy workloads.
- **OIDC for CI/CD**: GitHub Actions uses OIDC to assume an AWS role — no long-lived access keys.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEWAY_API_KEYS` | `dev-key-1` | Comma-separated valid client API keys |
| `UPSTREAM_BASE_URL` | `https://api.openai.com` | LLM provider base URL |
| `UPSTREAM_API_KEY` | (empty) | API key for the upstream provider |
| `INJECTION_THRESHOLD` | `0.7` | Risk score at which to block requests (0.0-1.0) |
| `PII_ACTION` | `redact` | Action on PII detection: `redact`, `block`, or `log_only` |
| `RATE_LIMIT_RPM` | `60` | Max requests per minute per client |
| `LOG_LEVEL` | `INFO` | Logging level |
| `AUDIT_LOG_FILE` | (empty) | Optional file path for audit logs |

## Roadmap

- [x] **Phase 1**: HTTP proxy, authentication, structured logging
- [x] **Phase 2**: Prompt injection detection, PII scanning, rate limiting
- [x] **Phase 3**: AWS Lambda + API Gateway deployment, Terraform IaC, GitHub Actions CI/CD
- [ ] **Phase 4**: AWS Bedrock support as upstream provider
- [ ] **Phase 4**: Per-client key management and usage tracking
