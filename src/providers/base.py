"""Abstract base for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProviderResponse:
    status_code: int
    body: dict


class LLMProvider(ABC):
    """Base class for LLM provider implementations."""

    @abstractmethod
    async def chat_completion(self, body: dict, api_key: str, model_id: str) -> ProviderResponse:
        """Send a chat completion request to the provider.

        Args:
            body: OpenAI-compatible request body.
            api_key: Upstream API key (or empty for IAM-based auth).
            model_id: Provider-specific model identifier.

        Returns:
            ProviderResponse with status code and response body dict.
        """
        ...

    async def close(self) -> None:
        """Cleanup resources. Override if provider holds connections."""
        pass
