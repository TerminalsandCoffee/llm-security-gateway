"""OpenAI provider implementation."""

import httpx
from fastapi import HTTPException

from src.config.settings import get_settings
from src.providers.base import LLMProvider, ProviderResponse


class OpenAIProvider(LLMProvider):
    """Forwards requests to OpenAI-compatible APIs."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        return self._client

    async def chat_completion(self, body: dict, api_key: str, model_id: str) -> ProviderResponse:
        settings = get_settings()

        # Per-client key with fallback to global
        upstream_key = api_key or settings.upstream_api_key
        upstream_url = f"{settings.upstream_base_url.rstrip('/')}/v1/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {upstream_key}",
        }

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

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
