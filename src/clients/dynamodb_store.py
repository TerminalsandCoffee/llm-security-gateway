"""DynamoDB-backed client store with in-memory TTL cache."""

import time

from src.clients.models import ClientConfig
from src.clients.store import ClientStore


class DynamoDBClientStore(ClientStore):
    """Looks up client config from a DynamoDB table with GSI on api_key."""

    CACHE_TTL = 300  # 5 minutes

    def __init__(self, table_name: str, region: str = "us-east-1"):
        self._table_name = table_name
        self._region = region
        self._table = None
        self._cache: dict[str, tuple[ClientConfig, float]] = {}

    def _get_table(self):
        """Lazy-init boto3 Table resource."""
        if self._table is None:
            import boto3

            dynamodb = boto3.resource("dynamodb", region_name=self._region)
            self._table = dynamodb.Table(self._table_name)
        return self._table

    async def get_by_api_key(self, api_key: str) -> ClientConfig | None:
        # Check cache first
        if api_key in self._cache:
            config, expires_at = self._cache[api_key]
            if time.monotonic() < expires_at:
                return config
            # Expired — remove and re-query
            del self._cache[api_key]

        import asyncio

        result = await asyncio.to_thread(self._query_by_key, api_key)

        # Only cache hits — don't cache None (avoids stale denial for new clients)
        if result is not None:
            self._cache[api_key] = (result, time.monotonic() + self.CACHE_TTL)

        return result

    def _query_by_key(self, api_key: str) -> ClientConfig | None:
        """Query GSI for a client by api_key."""
        from boto3.dynamodb.conditions import Key

        table = self._get_table()
        resp = table.query(
            IndexName="api_key_index",
            KeyConditionExpression=Key("api_key").eq(api_key),
            Limit=1,
        )

        items = resp.get("Items", [])
        if not items:
            return None

        item = items[0]
        return ClientConfig(
            client_id=item["client_id"],
            api_key=item["api_key"],
            provider=item.get("provider", "openai"),
            rate_limit_rpm=int(item.get("rate_limit_rpm", 60)),
            model_allowlist=item.get("model_allowlist", []),
            upstream_api_key=item.get("upstream_api_key", ""),
            bedrock_model_id=item.get("bedrock_model_id", ""),
            status=item.get("status", "active"),
        )
