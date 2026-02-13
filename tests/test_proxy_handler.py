"""Tests for src/proxy/handler.py — proxy routing."""

from unittest.mock import AsyncMock, patch

import pytest

from src.clients.models import ClientConfig
from src.providers.base import ProviderResponse
from src.proxy.handler import forward_to_provider, close_client
import src.providers.registry as registry_mod


@pytest.fixture(autouse=True)
def reset_registry(monkeypatch):
    monkeypatch.setattr(registry_mod, "_providers", {})
    yield
    monkeypatch.setattr(registry_mod, "_providers", {})


class TestForwardToProvider:

    async def test_routes_to_correct_provider(self):
        mock_provider = AsyncMock()
        mock_provider.chat_completion.return_value = ProviderResponse(
            status_code=200, body={"choices": []}
        )

        with patch("src.proxy.handler.get_provider", return_value=mock_provider) as mock_get:
            client = ClientConfig(
                client_id="c1", api_key="k1", provider="openai",
                upstream_api_key="sk-up", bedrock_model_id="",
            )
            result = await forward_to_provider({"model": "gpt-4o"}, client)

            mock_get.assert_called_once_with("openai")
            mock_provider.chat_completion.assert_called_once_with(
                body={"model": "gpt-4o"},
                api_key="sk-up",
                model_id="",
            )
            assert result.status_code == 200

    async def test_passes_bedrock_model_id(self):
        mock_provider = AsyncMock()
        mock_provider.chat_completion.return_value = ProviderResponse(
            status_code=200, body={}
        )

        with patch("src.proxy.handler.get_provider", return_value=mock_provider):
            client = ClientConfig(
                client_id="c1", api_key="k1", provider="bedrock",
                bedrock_model_id="anthropic.claude-3",
            )
            await forward_to_provider({}, client)
            call_kwargs = mock_provider.chat_completion.call_args.kwargs
            assert call_kwargs["model_id"] == "anthropic.claude-3"


class TestCloseClient:

    async def test_delegates_to_close_all(self):
        with patch("src.proxy.handler.close_all_providers", new_callable=AsyncMock) as mock_close:
            await close_client()
            mock_close.assert_called_once()
