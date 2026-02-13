"""API key authentication for gateway clients.

Validates the X-API-Key header against configured gateway keys.
Returns a ClientConfig for per-client routing and policy enforcement.
"""

import hmac

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from src.clients.factory import get_client_store
from src.clients.models import ClientConfig
from src.config.settings import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(api_key_header)) -> ClientConfig:
    """FastAPI dependency that validates the client's API key.

    Checks the client store first, then falls back to legacy
    comma-separated keys in settings (builds a default ClientConfig).
    """
    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing API key")

    # Try client store first
    store = get_client_store()
    if store is not None:
        client = await store.get_by_api_key(api_key)
        if client is not None:
            if client.status == "suspended":
                raise HTTPException(status_code=403, detail="Client suspended")
            return client

    # Legacy fallback: comma-separated keys → default OpenAI client
    settings = get_settings()
    for valid_key in settings.api_keys_list:
        if hmac.compare_digest(api_key, valid_key):
            return ClientConfig(
                client_id=f"legacy-{valid_key[:8]}",
                api_key=valid_key,
                provider="openai",
                rate_limit_rpm=settings.rate_limit_rpm,
                model_allowlist=[],
                upstream_api_key=settings.upstream_api_key,
            )

    raise HTTPException(status_code=403, detail="Invalid API key")
