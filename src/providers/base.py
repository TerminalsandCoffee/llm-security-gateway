"""Abstract base for LLM providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass


@dataclass
class ProviderResponse:
    status_code: int
    body: dict


@dataclass
class StreamChunk:
    data: str          # Raw SSE payload (JSON string or "[DONE]")
    is_done: bool      # True for terminal signal
    text_delta: str    # Extracted text for accumulation


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

    async def chat_completion_stream(
        self, body: dict, api_key: str, model_id: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream a chat completion response. Override to enable streaming.

        Yields StreamChunk objects with SSE-formatted data.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support streaming")
        # Make this an async generator (yield never reached, but required for type)
        yield  # pragma: no cover

    async def close(self) -> None:
        """Cleanup resources. Override if provider holds connections."""
        pass
