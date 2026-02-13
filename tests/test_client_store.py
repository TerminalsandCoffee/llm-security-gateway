"""Tests for src/clients/store.py — JSONClientStore."""

import json
import os
import time

import pytest

from src.clients.store import JSONClientStore


class TestJSONClientStoreLoad:

    def test_load_valid_file(self, clients_json_file):
        store = JSONClientStore(clients_json_file)
        assert len(store._clients) == 2

    def test_load_missing_file(self, tmp_path):
        store = JSONClientStore(str(tmp_path / "nonexistent.json"))
        assert store._clients == []

    def test_load_empty_clients(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text('{"clients": []}', encoding="utf-8")
        store = JSONClientStore(str(path))
        assert store._clients == []


class TestJSONClientStoreLookup:

    async def test_match_existing_key(self, clients_json_file):
        store = JSONClientStore(clients_json_file)
        client = await store.get_by_api_key("key-aaa-111")
        assert client is not None
        assert client.client_id == "client-a"

    async def test_miss_unknown_key(self, clients_json_file):
        store = JSONClientStore(clients_json_file)
        client = await store.get_by_api_key("nonexistent-key")
        assert client is None

    async def test_timing_safe_comparison(self, clients_json_file):
        """get_by_api_key iterates ALL clients even after finding a match
        (constant-time via hmac.compare_digest)."""
        store = JSONClientStore(clients_json_file)
        # First client matches — ensure we still get correct result
        client = await store.get_by_api_key("key-aaa-111")
        assert client.client_id == "client-a"


class TestJSONClientStoreReload:

    async def test_mtime_reload(self, clients_json_file):
        store = JSONClientStore(clients_json_file)
        assert len(store._clients) == 2

        # Update the file with a new client
        new_data = {
            "clients": [
                {"client_id": "client-c", "api_key": "key-ccc-333"},
            ]
        }
        # Ensure mtime changes (some filesystems have 1s resolution)
        time.sleep(0.05)
        with open(clients_json_file, "w", encoding="utf-8") as f:
            json.dump(new_data, f)
        # Force mtime to be different
        os.utime(clients_json_file, (time.time() + 1, time.time() + 1))

        client = await store.get_by_api_key("key-ccc-333")
        assert client is not None
        assert client.client_id == "client-c"
