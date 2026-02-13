"""Tests for src/providers/openai.py — OpenAI provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
from fastapi import HTTPException

from src.providers.openai import OpenAIProvider


@pytest.fixture
def provider():
    return OpenAIProvider()


class TestOpenAIProvider:

    async def test_chat_completion_success(self, provider, override_settings):
        override_settings(
            UPSTREAM_BASE_URL="https://api.openai.com",
            UPSTREAM_API_KEY="sk-global",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "Hi"}}]}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.is_closed = False
        provider._client = mock_client

        result = await provider.chat_completion(
            body={"model": "gpt-4o", "messages": []},
            api_key="sk-per-client",
            model_id="",
        )
        assert result.status_code == 200
        assert result.body["choices"][0]["message"]["content"] == "Hi"

        # Per-client key should be used (not global)
        call_kwargs = mock_client.post.call_args
        assert "Bearer sk-per-client" in call_kwargs.kwargs["headers"]["Authorization"]

    async def test_fallback_to_global_key(self, provider, override_settings):
        override_settings(
            UPSTREAM_BASE_URL="https://api.openai.com",
            UPSTREAM_API_KEY="sk-global-key",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.is_closed = False
        provider._client = mock_client

        await provider.chat_completion(body={}, api_key="", model_id="")
        call_kwargs = mock_client.post.call_args
        assert "Bearer sk-global-key" in call_kwargs.kwargs["headers"]["Authorization"]

    async def test_connect_error_raises_502(self, provider, override_settings):
        override_settings(UPSTREAM_BASE_URL="https://api.openai.com")
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.is_closed = False
        provider._client = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await provider.chat_completion(body={}, api_key="k", model_id="")
        assert exc_info.value.status_code == 502

    async def test_timeout_raises_504(self, provider, override_settings):
        override_settings(UPSTREAM_BASE_URL="https://api.openai.com")
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ReadTimeout("Timed out")
        mock_client.is_closed = False
        provider._client = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await provider.chat_completion(body={}, api_key="k", model_id="")
        assert exc_info.value.status_code == 504

    async def test_close(self, provider):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        provider._client = mock_client

        await provider.close()
        mock_client.aclose.assert_called_once()
        assert provider._client is None

    async def test_close_when_no_client(self, provider):
        """Closing without a client should not raise."""
        await provider.close()
