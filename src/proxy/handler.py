"""Proxy handler — thin wrapper delegating to provider registry.

Kept for backward compatibility (close_client, forward_to_provider).
"""

from collections.abc import AsyncGenerator

from src.clients.models import ClientConfig
from src.providers.base import ProviderResponse, StreamChunk
from src.providers.registry import close_all_providers, get_provider


async def forward_to_provider(body: dict, client: ClientConfig) -> ProviderResponse:
    """Route a request to the correct provider based on client config."""
    provider = get_provider(client.provider)
    return await provider.chat_completion(
        body=body,
        api_key=client.upstream_api_key,
        model_id=client.bedrock_model_id,
    )


async def stream_from_provider(
    body: dict, client: ClientConfig
) -> AsyncGenerator[StreamChunk, None]:
    """Route a streaming request to the correct provider."""
    provider = get_provider(client.provider)
    async for chunk in provider.chat_completion_stream(
        body=body,
        api_key=client.upstream_api_key,
        model_id=client.bedrock_model_id,
    ):
        yield chunk


async def close_client() -> None:
    """Gracefully close all providers on shutdown."""
    await close_all_providers()
