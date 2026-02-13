"""Tests for src/security/auth.py — API key authentication."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import src.clients.factory as factory_mod
from src.clients.models import ClientConfig
from src.clients.store import JSONClientStore
from src.security.auth import verify_api_key


@pytest.fixture(autouse=True)
def reset_factory(monkeypatch):
    monkeypatch.setattr(factory_mod, "_store", None)
    yield
    monkeypatch.setattr(factory_mod, "_store", None)


class TestVerifyApiKey:

    async def test_missing_key_returns_401(self):
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(api_key=None)
        assert exc_info.value.status_code == 401

    async def test_invalid_key_returns_403(self, override_settings):
        override_settings(GATEWAY_API_KEYS="valid-key")
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(api_key="wrong-key")
        assert exc_info.value.status_code == 403

    async def test_store_match_returns_client(self, override_settings, clients_json_file):
        override_settings(
            CLIENT_STORE_BACKEND="json",
            CLIENT_CONFIG_PATH=clients_json_file,
        )
        client = await verify_api_key(api_key="key-aaa-111")
        assert client.client_id == "client-a"

    async def test_suspended_client_returns_403(self, override_settings, clients_json_file):
        override_settings(
            CLIENT_STORE_BACKEND="json",
            CLIENT_CONFIG_PATH=clients_json_file,
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(api_key="key-bbb-222")
        assert exc_info.value.status_code == 403
        assert "suspended" in exc_info.value.detail.lower()

    async def test_legacy_fallback(self, override_settings, tmp_path):
        """When no store file exists, fall back to comma-separated keys."""
        override_settings(
            GATEWAY_API_KEYS="legacy-key-abc",
            CLIENT_STORE_BACKEND="json",
            CLIENT_CONFIG_PATH=str(tmp_path / "nope.json"),
            UPSTREAM_API_KEY="sk-fallback",
        )
        client = await verify_api_key(api_key="legacy-key-abc")
        assert client.client_id.startswith("legacy-")
        assert client.provider == "openai"
        assert client.upstream_api_key == "sk-fallback"

    async def test_legacy_invalid_key_returns_403(self, override_settings, tmp_path):
        override_settings(
            GATEWAY_API_KEYS="valid-key",
            CLIENT_STORE_BACKEND="json",
            CLIENT_CONFIG_PATH=str(tmp_path / "nope.json"),
        )
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(api_key="bad-key")
        assert exc_info.value.status_code == 403

    async def test_store_miss_then_legacy_match(self, override_settings, clients_json_file):
        """Key not in store but in legacy keys should match via fallback."""
        override_settings(
            GATEWAY_API_KEYS="fallback-key-xyz",
            CLIENT_STORE_BACKEND="json",
            CLIENT_CONFIG_PATH=clients_json_file,
        )
        client = await verify_api_key(api_key="fallback-key-xyz")
        assert client.client_id.startswith("legacy-")
