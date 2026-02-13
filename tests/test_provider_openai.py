"""Tests for src/providers/openai.py — OpenAI provider."""

import json
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


class TestOpenAIStreaming:

    async def test_stream_yields_chunks(self, provider, override_settings):
        override_settings(
            UPSTREAM_BASE_URL="https://api.openai.com",
            UPSTREAM_API_KEY="sk-test",
        )
        # Simulate SSE lines from upstream
        sse_lines = [
            'data: {"id":"x","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}',
            "",
            'data: {"id":"x","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":" world"},"finish_reason":null}]}',
            "",
            "data: [DONE]",
            "",
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.aiter_lines = MagicMock(return_value=_async_iter(sse_lines))
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        chunks = []
        async for chunk in provider.chat_completion_stream(
            body={"model": "gpt-4o", "messages": []},
            api_key="sk-test",
            model_id="",
        ):
            chunks.append(chunk)

        assert len(chunks) == 3  # 2 content + 1 DONE
        assert chunks[0].text_delta == "Hello"
        assert chunks[1].text_delta == " world"
        assert chunks[2].is_done
        assert chunks[2].data == "[DONE]"

    async def test_stream_extracts_empty_delta(self, provider, override_settings):
        """Chunks without content delta should yield empty text_delta."""
        override_settings(
            UPSTREAM_BASE_URL="https://api.openai.com",
            UPSTREAM_API_KEY="sk-test",
        )
        sse_lines = [
            'data: {"id":"x","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}',
            "",
            "data: [DONE]",
            "",
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.aiter_lines = MagicMock(return_value=_async_iter(sse_lines))
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        chunks = []
        async for chunk in provider.chat_completion_stream(
            body={"model": "gpt-4o", "messages": []},
            api_key="sk-test",
            model_id="",
        ):
            chunks.append(chunk)

        assert chunks[0].text_delta == ""
        assert chunks[1].is_done

    async def test_stream_connect_error(self, provider, override_settings):
        override_settings(UPSTREAM_BASE_URL="https://api.openai.com")
        mock_client = AsyncMock()
        mock_client.stream = MagicMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.is_closed = False
        provider._client = mock_client

        with pytest.raises(HTTPException) as exc_info:
            async for _ in provider.chat_completion_stream(body={}, api_key="k", model_id=""):
                pass
        assert exc_info.value.status_code == 502

    async def test_stream_upstream_error_status(self, provider, override_settings):
        """Non-200 upstream status during stream should raise HTTPException."""
        override_settings(
            UPSTREAM_BASE_URL="https://api.openai.com",
            UPSTREAM_API_KEY="sk-test",
        )
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.aread = AsyncMock(return_value=b'{"error": "invalid key"}')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        with pytest.raises(HTTPException) as exc_info:
            async for _ in provider.chat_completion_stream(
                body={"model": "gpt-4o", "messages": []},
                api_key="sk-test",
                model_id="",
            ):
                pass
        assert exc_info.value.status_code == 401

    async def test_stream_sets_stream_true_in_body(self, provider, override_settings):
        """The forwarded body should have stream: true set."""
        override_settings(
            UPSTREAM_BASE_URL="https://api.openai.com",
            UPSTREAM_API_KEY="sk-test",
        )
        sse_lines = ["data: [DONE]", ""]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.aiter_lines = MagicMock(return_value=_async_iter(sse_lines))
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_response)
        mock_client.is_closed = False
        provider._client = mock_client

        async for _ in provider.chat_completion_stream(
            body={"model": "gpt-4o", "messages": []},
            api_key="sk-test",
            model_id="",
        ):
            pass

        call_kwargs = mock_client.stream.call_args
        sent_body = call_kwargs.kwargs.get("json", {})
        assert sent_body.get("stream") is True


async def _async_iter(items):
    """Helper to make a sync list into an async iterator."""
    for item in items:
        yield item
