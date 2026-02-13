"""Provider registry — singleton map of provider name → instance."""

from src.providers.base import LLMProvider, ProviderResponse
from src.providers.openai import OpenAIProvider

_providers: dict[str, LLMProvider] = {}


def get_provider(name: str) -> LLMProvider:
    """Get or create a provider instance by name."""
    if name in _providers:
        return _providers[name]

    if name == "openai":
        _providers[name] = OpenAIProvider()
    elif name == "bedrock":
        # Lazy import to avoid pulling in boto3 for OpenAI-only setups
        from src.providers.bedrock import BedrockProvider
        _providers[name] = BedrockProvider()
    else:
        raise ValueError(f"Unknown provider: {name}")

    return _providers[name]


async def close_all_providers() -> None:
    """Gracefully shut down all provider connections."""
    for provider in _providers.values():
        await provider.close()
    _providers.clear()
