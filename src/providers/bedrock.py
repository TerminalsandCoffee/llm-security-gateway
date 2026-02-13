"""AWS Bedrock Converse API provider — translates OpenAI format to/from Bedrock."""

import asyncio
import time

from fastapi import HTTPException

from src.providers.base import LLMProvider, ProviderResponse


class BedrockProvider(LLMProvider):
    """Sends requests to AWS Bedrock via the Converse API."""

    def __init__(self):
        self._client = None

    def _get_client(self):
        """Lazy-init boto3 client (avoids import when not needed)."""
        if self._client is None:
            import boto3
            from src.config.settings import get_settings

            settings = get_settings()
            self._client = boto3.client(
                "bedrock-runtime", region_name=settings.aws_region
            )
        return self._client

    @staticmethod
    def _translate_request(body: dict, model_id: str) -> dict:
        """Translate OpenAI chat completion request → Bedrock Converse params."""
        kwargs = {"modelId": model_id}

        # Separate system messages from conversation messages
        system_msgs = []
        converse_msgs = []
        for msg in body.get("messages", []):
            if msg.get("role") == "system":
                system_msgs.append({"text": msg["content"]})
            else:
                converse_msgs.append({
                    "role": msg["role"],
                    "content": [{"text": msg["content"]}],
                })

        if system_msgs:
            kwargs["system"] = system_msgs
        kwargs["messages"] = converse_msgs

        # Map inference params (only include if present)
        inference_config = {}
        if "temperature" in body:
            inference_config["temperature"] = body["temperature"]
        if "max_tokens" in body:
            inference_config["maxTokens"] = body["max_tokens"]
        if "top_p" in body:
            inference_config["topP"] = body["top_p"]
        if "stop" in body:
            inference_config["stopSequences"] = body["stop"]

        if inference_config:
            kwargs["inferenceConfig"] = inference_config

        return kwargs

    @staticmethod
    def _translate_response(response: dict, model_id: str) -> dict:
        """Translate Bedrock Converse response → OpenAI-compatible format."""
        output_msg = response.get("output", {}).get("message", {})
        content_blocks = output_msg.get("content", [])
        text = "".join(block.get("text", "") for block in content_blocks)

        # Map stop reason
        stop_reason = response.get("stopReason", "end_turn")
        finish_reason = "length" if stop_reason == "max_tokens" else "stop"

        # Map usage
        usage = response.get("usage", {})

        return {
            "id": f"bedrock-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": usage.get("inputTokens", 0),
                "completion_tokens": usage.get("outputTokens", 0),
                "total_tokens": usage.get("inputTokens", 0) + usage.get("outputTokens", 0),
            },
        }

    def _call_converse(self, **kwargs) -> dict:
        """Synchronous Converse API call (run via asyncio.to_thread)."""
        return self._get_client().converse(**kwargs)

    async def chat_completion(self, body: dict, api_key: str, model_id: str) -> ProviderResponse:
        # api_key ignored — Bedrock uses IAM credentials from environment
        if not model_id:
            raise HTTPException(
                status_code=400,
                detail="bedrock_model_id is required for Bedrock provider",
            )

        kwargs = self._translate_request(body, model_id)

        try:
            response = await asyncio.to_thread(self._call_converse, **kwargs)
        except Exception as e:
            error_code = getattr(
                getattr(e, "response", None), "Error", {}
            ) if hasattr(e, "response") else {}
            # boto3 exceptions store code in response["Error"]["Code"]
            if isinstance(getattr(e, "response", None), dict):
                error_code = e.response.get("Error", {}).get("Code", "")
            else:
                error_code = type(e).__name__

            if error_code == "ThrottlingException":
                raise HTTPException(status_code=429, detail="Bedrock rate limit exceeded")
            elif error_code == "ValidationException":
                raise HTTPException(status_code=400, detail=f"Bedrock validation error: {e}")
            elif error_code == "ModelNotReadyException":
                raise HTTPException(status_code=503, detail="Bedrock model not ready")
            elif error_code == "AccessDeniedException":
                raise HTTPException(status_code=403, detail="Bedrock access denied — check IAM permissions")
            else:
                raise HTTPException(status_code=502, detail=f"Bedrock error: {e}")

        response_body = self._translate_response(response, model_id)
        return ProviderResponse(status_code=200, body=response_body)

    async def close(self) -> None:
        # boto3 clients don't need explicit cleanup
        self._client = None
