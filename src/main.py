"""LLM Security Gateway — FastAPI application entry point.

A security proxy that sits between applications and LLM APIs,
enforcing authentication, logging, and security policies.
"""

import json
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.clients.models import ClientConfig
from src.config.settings import get_settings
from src.logging.audit import (
    RequestTimer,
    generate_request_id,
    get_audit_logger,
    request_id_var,
    setup_logging,
)
from src.proxy.handler import close_client, forward_to_provider, stream_from_provider
from src.security.auth import verify_api_key
from src.security.injection import scan_prompt
from src.security.pii import scan_for_pii
from src.security.ratelimit import check_rate_limit
from src.security.response import scan_response

VERSION = "0.5.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle hooks."""
    setup_logging()
    get_audit_logger().info("Gateway started")
    yield
    await close_client()
    get_audit_logger().info("Gateway stopped")


app = FastAPI(
    title="LLM Security Gateway",
    description="Security proxy for LLM API requests",
    version=VERSION,
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "healthy", "version": VERSION}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, client: ClientConfig = Depends(verify_api_key)):
    """Proxy endpoint mirroring the OpenAI chat completions API.

    Pipeline: Auth -> Rate Limit -> Model Allowlist -> Injection Scan -> PII Scan -> Forward -> Response Scan -> Log
    """
    logger = get_audit_logger()
    rid = generate_request_id()
    request_id_var.set(rid)

    body = await request.json()
    client_ip = request.client.host if request.client else "unknown"
    model = body.get("model", "unknown")
    is_stream = body.get("stream", False)

    # --- Security pipeline ---

    # 1. Rate limiting (per-client)
    rate_result = await check_rate_limit(client.client_id, client.rate_limit_rpm)
    if not rate_result.allowed:
        logger.warning(
            "Rate limit exceeded",
            extra={"audit_data": {
                "client_id": client.client_id,
                "client_ip": client_ip,
                "rate_limit": rate_result.limit,
                "retry_after": rate_result.reset_seconds,
            }},
        )
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded"},
            headers={
                "Retry-After": str(int(rate_result.reset_seconds)),
                "X-RateLimit-Limit": str(rate_result.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(rate_result.reset_seconds)),
            },
        )

    # 2. Model allowlist check
    if client.model_allowlist and model not in client.model_allowlist:
        logger.warning(
            "Model not allowed",
            extra={"audit_data": {
                "client_id": client.client_id,
                "client_ip": client_ip,
                "model": model,
                "allowed_models": client.model_allowlist,
            }},
        )
        return JSONResponse(
            status_code=403,
            content={"error": f"Model '{model}' not allowed for this client"},
        )

    # 3. Prompt injection scan
    prompt_content = _extract_prompt_content(body)
    injection_result = await scan_prompt(prompt_content)
    if not injection_result.allowed:
        logger.warning(
            "Prompt injection blocked",
            extra={"audit_data": {
                "client_id": client.client_id,
                "client_ip": client_ip,
                "risk_score": injection_result.risk_score,
                "reason": injection_result.reason,
                "categories": injection_result.matched_categories,
            }},
        )
        return JSONResponse(
            status_code=400,
            content={"error": "Request blocked by security policy"},
        )

    # 4. PII scan
    pii_result = await scan_for_pii(prompt_content)

    # Block mode: reject the entire request if PII found
    if not pii_result.clean and pii_result.redacted_content is None and pii_result.detection_count > 0:
        settings = get_settings()
        if settings.pii_action == "block":
            logger.warning(
                "PII detected — request blocked",
                extra={"audit_data": {
                    "client_id": client.client_id,
                    "client_ip": client_ip,
                    "pii_types": pii_result.detections,
                    "pii_count": pii_result.detection_count,
                }},
            )
            return JSONResponse(
                status_code=400,
                content={"error": "Request contains sensitive data (PII)"},
            )

    # Redact mode: swap in sanitized content
    if pii_result.redacted_content:
        body = _replace_prompt_content(body, pii_result.redacted_content)

    # 5. Lambda guard: reject streaming on Lambda (no SSE support via API Gateway + Mangum)
    if is_stream and os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return JSONResponse(
            status_code=400,
            content={"error": "Streaming is not supported in Lambda deployments"},
        )

    # --- Branch: streaming vs non-streaming ---

    if is_stream:
        return await _handle_streaming(body, client, client_ip, model, rid, rate_result,
                                       injection_result, pii_result, logger)

    # --- Non-streaming: Forward to upstream ---
    with RequestTimer() as timer:
        result = await forward_to_provider(body, client)

    # Response scanning (non-streaming)
    response_content = _extract_response_content(result.body)
    response_scan = await scan_response(response_content)

    if response_scan.blocked:
        logger.warning(
            "Response blocked — PII in LLM output",
            extra={"audit_data": {
                "client_id": client.client_id,
                "client_ip": client_ip,
                "response_pii_types": response_scan.pii.detections,
                "response_pii_count": response_scan.pii.detection_count,
            }},
        )
        return JSONResponse(
            status_code=400,
            content={"error": "Response blocked by security policy — contains sensitive data"},
        )

    # --- Audit log ---
    logger.info(
        "Request proxied",
        extra={"audit_data": {
            "client_id": client.client_id,
            "client_ip": client_ip,
            "provider": client.provider,
            "model": model,
            "upstream_status": result.status_code,
            "latency_ms": timer.elapsed_ms,
            "injection_score": injection_result.risk_score,
            "injection_categories": injection_result.matched_categories,
            "pii_detections": pii_result.detections,
            "pii_count": pii_result.detection_count,
            "response_injection_score": response_scan.injection.risk_score,
            "response_pii_detections": response_scan.pii.detections,
            "rate_limit_remaining": rate_result.remaining,
        }},
    )

    # Return upstream response with rate limit headers
    return JSONResponse(
        status_code=result.status_code,
        content=result.body,
        headers={
            "X-RateLimit-Limit": str(rate_result.limit),
            "X-RateLimit-Remaining": str(rate_result.remaining),
            "X-RateLimit-Reset": str(int(rate_result.reset_seconds)),
            "X-Request-Id": rid,
        },
    )


async def _handle_streaming(body, client, client_ip, model, rid, rate_result,
                             injection_result, pii_result, logger):
    """Handle streaming requests — forward chunks, scan accumulated text at end."""

    async def event_generator():
        accumulated_text = []

        try:
            async for chunk in stream_from_provider(body, client):
                if chunk.text_delta:
                    accumulated_text.append(chunk.text_delta)

                if chunk.is_done:
                    # Scan accumulated response before sending [DONE]
                    full_text = "".join(accumulated_text)
                    response_scan = await scan_response(full_text)

                    # Log response scan results
                    logger.info(
                        "Stream completed",
                        extra={"audit_data": {
                            "client_id": client.client_id,
                            "client_ip": client_ip,
                            "provider": client.provider,
                            "model": model,
                            "stream": True,
                            "injection_score": injection_result.risk_score,
                            "pii_detections": pii_result.detections,
                            "response_injection_score": response_scan.injection.risk_score,
                            "response_pii_detections": response_scan.pii.detections,
                            "rate_limit_remaining": rate_result.remaining,
                        }},
                    )

                    if response_scan.blocked:
                        # Send error event instead of [DONE]
                        error_data = json.dumps({
                            "error": "Response blocked by security policy — contains sensitive data"
                        })
                        yield f"data: {error_data}\n\n"
                        return

                    yield "data: [DONE]\n\n"
                    return

                yield f"data: {chunk.data}\n\n"

        except Exception as e:
            error_data = json.dumps({"error": str(e)})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "X-RateLimit-Limit": str(rate_result.limit),
            "X-RateLimit-Remaining": str(rate_result.remaining),
            "X-RateLimit-Reset": str(int(rate_result.reset_seconds)),
            "X-Request-Id": rid,
            "Cache-Control": "no-cache",
        },
    )


def _extract_prompt_content(body: dict) -> str:
    """Extract user message content from a chat completions request body."""
    messages = body.get("messages", [])
    parts = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            # Handle multi-part content (text + image_url)
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
    return "\n".join(parts)


def _extract_response_content(body: dict) -> str:
    """Extract assistant message text from a chat completion response body."""
    choices = body.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    return message.get("content", "") or ""


def _replace_prompt_content(body: dict, redacted: str) -> dict:
    """Replace user message content with redacted version.

    Simplified: replaces the last user message's content.
    """
    messages = body.get("messages", [])
    for msg in reversed(messages):
        if msg.get("role") == "user":
            msg["content"] = redacted
            break
    return body
