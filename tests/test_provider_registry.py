"""Tests for src/providers/registry.py — provider singleton registry."""

import pytest

import src.providers.registry as registry_mod
from src.providers.openai import OpenAIProvider


@pytest.fixture(autouse=True)
def reset_registry(monkeypatch):
    """Clear the provider registry between tests."""
    monkeypatch.setattr(registry_mod, "_providers", {})
    yield
    monkeypatch.setattr(registry_mod, "_providers", {})


class TestGetProvider:

    def test_creates_openai_provider(self):
        provider = registry_mod.get_provider("openai")
        assert isinstance(provider, OpenAIProvider)

    def test_singleton_behavior(self):
        p1 = registry_mod.get_provider("openai")
        p2 = registry_mod.get_provider("openai")
        assert p1 is p2

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            registry_mod.get_provider("fake-provider")


class TestCloseAllProviders:

    async def test_close_all(self):
        p = registry_mod.get_provider("openai")
        await registry_mod.close_all_providers()
        assert registry_mod._providers == {}
