"""Shared fixtures for the LLM Security Gateway test suite."""

import json
import os
import tempfile

import pytest

from src.clients.models import ClientConfig
from src.config.settings import get_settings
from src.providers.base import StreamChunk


@pytest.fixture
def sample_client() -> ClientConfig:
    """A typical active client config for testing."""
    return ClientConfig(
        client_id="test-client-1",
        api_key="sk-test-key-12345678",
        provider="openai",
        rate_limit_rpm=10,
        model_allowlist=["gpt-4o", "gpt-4o-mini"],
        upstream_api_key="sk-upstream-key",
    )


@pytest.fixture
def chat_request_body() -> dict:
    """Standard chat completions request body."""
    return {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"},
        ],
    }


@pytest.fixture
def clients_json_file(tmp_path):
    """Create a temp clients.json file and return its path."""
    data = {
        "clients": [
            {
                "client_id": "client-a",
                "api_key": "key-aaa-111",
                "provider": "openai",
                "rate_limit_rpm": 30,
                "model_allowlist": ["gpt-4o"],
                "upstream_api_key": "sk-upstream-a",
            },
            {
                "client_id": "client-b",
                "api_key": "key-bbb-222",
                "provider": "openai",
                "rate_limit_rpm": 60,
                "model_allowlist": [],
                "upstream_api_key": "",
                "status": "suspended",
            },
        ]
    }
    path = tmp_path / "clients.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


@pytest.fixture
def override_settings(monkeypatch):
    """Factory fixture: set env vars and clear settings cache.

    Usage:
        override_settings(GATEWAY_API_KEYS="key1,key2", PII_ACTION="block")
    """
    def _override(**kwargs):
        for key, value in kwargs.items():
            monkeypatch.setenv(key.upper(), str(value))
        # Clear lru_cache so Settings re-reads env
        get_settings.cache_clear()

    yield _override

    # Always clear cache on teardown so other tests get fresh settings
    get_settings.cache_clear()


def make_stream_chunks(text: str, chunk_size: int = 5) -> list[StreamChunk]:
    """Build a list of StreamChunk objects from text, splitting into small deltas."""
    chunks = []
    for i in range(0, len(text), chunk_size):
        delta = text[i:i + chunk_size]
        data = json.dumps({
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
        })
        chunks.append(StreamChunk(data=data, is_done=False, text_delta=delta))
    # Finish reason chunk
    finish_data = json.dumps({
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    })
    chunks.append(StreamChunk(data=finish_data, is_done=False, text_delta=""))
    # [DONE] sentinel
    chunks.append(StreamChunk(data="[DONE]", is_done=True, text_delta=""))
    return chunks
