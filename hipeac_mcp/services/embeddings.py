"""Embedding generation service with pluggable provider support.

Currently supports OpenAI. Designed so alternative providers (Mistral, Ollama, etc.)
can be added by implementing the ``EmbeddingProvider`` protocol.
"""

import logging
import os
from typing import Protocol, runtime_checkable


logger = logging.getLogger(__name__)


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text.

        :param text: Text to embed.
        :returns: Embedding vector as a list of floats.
        """
        ...


class OpenAIEmbeddingProvider:
    """OpenAI embedding provider using the embeddings API."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        """Initialize the OpenAI embedding provider.

        :param api_key: OpenAI API key.
        :param model: Embedding model name.
        """
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate an embedding vector using OpenAI.

        :param text: Text to embed.
        :returns: Embedding vector as a list of floats.
        """
        response = await self.client.embeddings.create(model=self.model, input=text)
        return response.data[0].embedding


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Get the configured embedding provider (singleton).

    Reads ``EMBEDDING_PROVIDER`` to select a provider (default: ``openai``).
    Each provider reads its own environment variables for configuration.

    :returns: An embedding provider instance.
    :raises ValueError: If the configured provider is not supported or misconfigured.
    """
    global _provider  # noqa: PLW0603

    if _provider is None:
        provider_name = os.getenv("EMBEDDING_PROVIDER", "openai")

        if provider_name == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable is required for the OpenAI embedding provider")
            model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
            _provider = OpenAIEmbeddingProvider(api_key=api_key, model=model)
        else:
            raise ValueError(f"Unsupported embedding provider: {provider_name}")

    return _provider
