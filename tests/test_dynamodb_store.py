"""Tests for src/clients/dynamodb_store.py — DynamoDB client store."""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.clients.dynamodb_store import DynamoDBClientStore


@pytest.fixture
def mock_table():
    """Mock boto3 DynamoDB Table."""
    return MagicMock()


@pytest.fixture
def store(mock_table):
    """DynamoDBClientStore with pre-injected mock table."""
    s = DynamoDBClientStore(table_name="test-table", region="us-east-1")
    s._table = mock_table
    return s


FULL_ITEM = {
    "client_id": "client-1",
    "api_key": "sk-test-key",
    "provider": "bedrock",
    "rate_limit_rpm": 30,
    "model_allowlist": ["anthropic.claude-3-sonnet"],
    "upstream_api_key": "sk-upstream",
    "bedrock_model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
    "status": "active",
}


class TestQueryByKey:

    async def test_found_client(self, store, mock_table):
        mock_table.query.return_value = {"Items": [FULL_ITEM]}

        result = await store.get_by_api_key("sk-test-key")
        assert result is not None
        assert result.client_id == "client-1"
        assert result.provider == "bedrock"
        assert result.bedrock_model_id == "anthropic.claude-3-sonnet-20240229-v1:0"

    async def test_not_found(self, store, mock_table):
        mock_table.query.return_value = {"Items": []}

        result = await store.get_by_api_key("sk-nonexistent")
        assert result is None

    async def test_maps_all_fields(self, store, mock_table):
        mock_table.query.return_value = {"Items": [FULL_ITEM]}

        result = await store.get_by_api_key("sk-test-key")
        assert result.rate_limit_rpm == 30
        assert result.model_allowlist == ["anthropic.claude-3-sonnet"]
        assert result.upstream_api_key == "sk-upstream"
        assert result.status == "active"

    async def test_defaults_for_missing_fields(self, store, mock_table):
        minimal_item = {"client_id": "client-2", "api_key": "sk-minimal"}
        mock_table.query.return_value = {"Items": [minimal_item]}

        result = await store.get_by_api_key("sk-minimal")
        assert result.provider == "openai"
        assert result.rate_limit_rpm == 60
        assert result.model_allowlist == []
        assert result.upstream_api_key == ""
        assert result.bedrock_model_id == ""
        assert result.status == "active"


class TestCache:

    async def test_cache_hit_skips_query(self, store, mock_table):
        mock_table.query.return_value = {"Items": [FULL_ITEM]}

        # First call — queries DynamoDB
        await store.get_by_api_key("sk-test-key")
        assert mock_table.query.call_count == 1

        # Second call — cache hit, no query
        await store.get_by_api_key("sk-test-key")
        assert mock_table.query.call_count == 1

    async def test_cache_expired_re_queries(self, store, mock_table):
        mock_table.query.return_value = {"Items": [FULL_ITEM]}

        await store.get_by_api_key("sk-test-key")
        assert mock_table.query.call_count == 1

        # Expire the cache entry
        key, (config, _) = next(iter(store._cache.items()))
        store._cache[key] = (config, time.monotonic() - 1)

        await store.get_by_api_key("sk-test-key")
        assert mock_table.query.call_count == 2

    async def test_none_not_cached(self, store, mock_table):
        mock_table.query.return_value = {"Items": []}

        await store.get_by_api_key("sk-missing")
        assert "sk-missing" not in store._cache


class TestLazyInit:

    def test_table_is_none_initially(self):
        store = DynamoDBClientStore(table_name="t", region="us-east-1")
        assert store._table is None

    @patch("boto3.resource")
    def test_table_created_on_first_query(self, mock_resource):
        mock_dynamodb = MagicMock()
        mock_resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = MagicMock()

        store = DynamoDBClientStore(table_name="my-table", region="us-west-2")
        store._get_table()

        mock_resource.assert_called_once_with("dynamodb", region_name="us-west-2")
        mock_dynamodb.Table.assert_called_once_with("my-table")
