"""Tests for src/clients/factory.py — get_client_store factory."""

import pytest

import src.clients.factory as factory_mod
from src.clients.store import JSONClientStore


@pytest.fixture(autouse=True)
def reset_store_singleton(monkeypatch):
    """Reset the factory singleton between tests."""
    monkeypatch.setattr(factory_mod, "_store", None)
    yield
    monkeypatch.setattr(factory_mod, "_store", None)


class TestGetClientStore:

    def test_json_backend_with_file(self, override_settings, clients_json_file):
        override_settings(
            CLIENT_STORE_BACKEND="json",
            CLIENT_CONFIG_PATH=clients_json_file,
        )
        store = factory_mod.get_client_store()
        assert isinstance(store, JSONClientStore)

    def test_json_backend_missing_file(self, override_settings, tmp_path):
        override_settings(
            CLIENT_STORE_BACKEND="json",
            CLIENT_CONFIG_PATH=str(tmp_path / "nonexistent.json"),
        )
        store = factory_mod.get_client_store()
        assert store is None

    def test_singleton_returns_same_instance(self, override_settings, clients_json_file):
        override_settings(
            CLIENT_STORE_BACKEND="json",
            CLIENT_CONFIG_PATH=clients_json_file,
        )
        store1 = factory_mod.get_client_store()
        store2 = factory_mod.get_client_store()
        assert store1 is store2

    def test_unknown_backend(self, override_settings):
        override_settings(CLIENT_STORE_BACKEND="redis")
        store = factory_mod.get_client_store()
        assert store is None
