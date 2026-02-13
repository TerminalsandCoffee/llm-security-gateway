"""Shared fixtures for the LLM Security Gateway test suite."""

import json
import os
import tempfile

import pytest

from src.clients.models import ClientConfig
from src.config.settings import get_settings


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
