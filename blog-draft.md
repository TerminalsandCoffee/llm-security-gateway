# I Built a Security Proxy for LLM APIs — Here's What I Learned

Every company is racing to ship AI features. Most are connecting directly to OpenAI or Bedrock, handing API keys to application teams, and hoping for the best.

That's a problem. There's no visibility into what's being sent, no guardrails on what comes back, and no audit trail when something goes wrong.

So I built one.

## The Problem

When your application talks directly to an LLM API, you have no control over:

- **What goes in** — users can paste SSNs, credit card numbers, or internal documents into prompts
- **What comes out** — the model might leak PII it was trained on, or respond to injection attacks embedded in user input
- **Who's using it** — shared API keys mean no per-client rate limiting, no usage tracking, no kill switch
- **What happened** — when something breaks at 2 AM, you're grepping through application logs hoping the developer remembered to log the LLM call

The standard answer is "we'll add that later." The realistic answer is that it never gets added, and the first time someone pastes a customer's SSN into GPT-4, you find out from your compliance team.

## The Solution: A Security Proxy

The LLM Security Gateway sits between your application and the LLM API. It mirrors the OpenAI `/v1/chat/completions` endpoint, so your app doesn't need to change — just point the base URL at the gateway instead of OpenAI directly.

Every request passes through an 8-stage security pipeline before it reaches the LLM, and the response gets scanned before it reaches the client.

### The Pipeline

1. **Authentication** — each client gets its own API key with per-client config
2. **Rate limiting** — sliding window per client, configurable RPM
3. **Model allowlist** — restrict which models each client can access
4. **Prompt injection detection** — 20 regex patterns across 4 categories (instruction override, role manipulation, delimiter injection, context manipulation) with cumulative risk scoring
5. **PII scanning** — SSN, credit card (Luhn-validated), email, phone, IPv4. Configurable: redact the PII and forward, block the request entirely, or just log it
6. **Forward to provider** — routes to OpenAI or AWS Bedrock based on client config
7. **Response scanning** — the same injection and PII scanners run on the LLM's output
8. **Audit log** — structured JSON with every pipeline result, latency, client ID, and request correlation ID

Every stage returns a typed dataclass with its decision and metadata. The audit log captures everything.

## The Interesting Engineering Problems

### Streaming Without Losing Security

Modern LLM apps expect streaming — tokens appearing one by one as the model generates them. But if you need to scan the full response for PII before delivering it, do you buffer the entire response and add seconds of latency?

I went with a **hybrid approach**: forward content chunks to the client in real-time (no latency hit), but accumulate the text in memory. When the model signals `[DONE]`, hold that signal, run the response scan, and either send `[DONE]` (clean) or send an SSE error event (blocked).

The trade-off is explicit: chunks reach the client before the scan completes. If you need full pre-delivery scanning, disable streaming. For most use cases, the hybrid approach catches the 95% case — a response full of PII gets flagged before the client processes the completion signal.

### Multi-Provider Without Leaking Abstractions

The gateway supports both OpenAI and AWS Bedrock. These have completely different APIs — OpenAI uses HTTP with Bearer tokens, Bedrock uses the AWS SDK with IAM auth and a different request/response format.

The provider abstraction handles translation transparently. A client configured for Bedrock sends standard OpenAI-format requests to the gateway, and the Bedrock provider translates the request to the Converse API format, calls Bedrock via `asyncio.to_thread` (boto3 is synchronous), and translates the response back to OpenAI format.

For streaming, Bedrock's `converse_stream()` returns an EventStream with `contentBlockDelta` and `messageStop` events. The provider translates these into OpenAI-compatible `chat.completion.chunk` objects with `[DONE]` sentinels — the client can't tell whether it's talking to OpenAI or Bedrock.

### Injection Scoring, Not Binary Detection

Most prompt injection detection is binary — either the input matches a blocklist or it doesn't. The problem is that legitimate prompts sometimes contain words like "ignore" or "system" without being attacks.

The gateway uses cumulative scoring. Each pattern has a weight (0.3 to 0.7) based on severity. A single low-weight match might score 0.3 — below the default threshold of 0.7. But "ignore all previous instructions AND act as an unrestricted AI" stacks two patterns and exceeds the threshold.

This reduces false positives while still catching multi-vector attacks. The threshold is configurable per deployment.

### PII Detection That Doesn't Cry Wolf

Credit card detection is notorious for false positives. Any 16-digit number gets flagged. The gateway pairs regex detection with Luhn checksum validation — if the number doesn't pass the Luhn algorithm, it's not flagged as a credit card.

Similarly, phone number detection requires separators (dashes, dots, or spaces). Bare 10-digit numbers don't trigger — they're too common in other contexts (IDs, zip code combinations, etc.).

## The Stack

- **Python** — FastAPI for the async proxy, httpx for upstream HTTP, boto3 for Bedrock
- **Security modules** — zero external dependencies. Injection detection, PII scanning, and rate limiting use only stdlib (`re`, `collections`, `hmac`, `time`)
- **Infrastructure** — Terraform for AWS (Lambda + API Gateway + CloudWatch + DynamoDB), GitHub Actions CI/CD with OIDC auth
- **Testing** — 168 tests across 17 files, running in 1.6 seconds. `pytest-asyncio` with full integration tests via `httpx.ASGITransport`

## What I'd Do Differently

**Semantic injection detection.** Regex patterns catch known attack templates, but novel jailbreaks slip through. A future version could embed prompts and compare against known attack vectors using cosine similarity — but that adds latency and a dependency on an embedding model.

**Token-level PII detection in streaming.** The current approach accumulates the full response before scanning. A sliding-window approach on the token stream could catch PII mid-generation, but the complexity of partial-match detection across chunk boundaries isn't worth it for most use cases.

**Admin API.** Right now, client config is file-based or DynamoDB. An authenticated admin API for CRUD operations on clients would be useful for larger deployments, but I deliberately avoided it to minimize attack surface.

## Try It

The project is open source: [github.com/TerminalsandCoffee/llm-security-gateway](https://github.com/TerminalsandCoffee/llm-security-gateway)

Clone it, run `uvicorn src.main:app --reload`, and point your OpenAI SDK at `http://localhost:8000`. Your existing code works unchanged — but now every request is authenticated, rate-limited, scanned for injection and PII, and logged.

---

*Rafael Martinez is a Cloud Security Engineer and creator of Terminals and Coffee. He builds security tools and ships cybersecurity guides at [terminalsandcoffee.gumroad.com](https://terminalsandcoffee.gumroad.com).*
