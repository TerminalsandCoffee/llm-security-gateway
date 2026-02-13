"""OpenAI provider implementation."""

import json
from collections.abc import AsyncGenerator

import httpx
from fastapi import HTTPException

from src.config.settings import get_settings
from src.providers.base import LLMProvider, ProviderResponse, StreamChunk


class OpenAIProvider(LLMProvider):
    """Forwards requests to OpenAI-compatible APIs."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        return self._client

    def _build_headers(self, api_key: str) -> dict:
        settings = get_settings()
        upstream_key = api_key or settings.upstream_api_key
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {upstream_key}",
        }

    async def chat_completion(self, body: dict, api_key: str, model_id: str) -> ProviderResponse:
        settings = get_settings()
        upstream_url = f"{settings.upstream_base_url.rstrip('/')}/v1/chat/completions"
        headers = self._build_headers(api_key)

        client = await self._get_client()
        try:
            response = await client.post(upstream_url, json=body, headers=headers)
            return ProviderResponse(status_code=response.status_code, body=response.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Cannot reach upstream provider")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Upstream provider timed out")
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Upstream error: {e}")

    async def chat_completion_stream(
        self, body: dict, api_key: str, model_id: str
    ) -> AsyncGenerator[StreamChunk, None]:
        settings = get_settings()
        upstream_url = f"{settings.upstream_base_url.rstrip('/')}/v1/chat/completions"
        headers = self._build_headers(api_key)

        # Ensure stream flag is set in the forwarded body
        stream_body = {**body, "stream": True}

        client = await self._get_client()
        try:
            async with client.stream("POST", upstream_url, json=stream_body, headers=headers) as response:
                if response.status_code != 200:
                    body_bytes = await response.aread()
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=body_bytes.decode(errors="replace"),
                    )

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue

                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        yield StreamChunk(data="[DONE]", is_done=True, text_delta="")
                        return

                    # Extract text delta from chunk
                    text_delta = ""
                    try:
                        chunk = json.loads(payload)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            text_delta = delta.get("content", "") or ""
                    except json.JSONDecodeError:
                        pass

                    yield StreamChunk(data=payload, is_done=False, text_delta=text_delta)

        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Cannot reach upstream provider")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Upstream provider timed out")
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Upstream error: {e}")

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
