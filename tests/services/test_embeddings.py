"""Tests for embedding service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hipeac_mcp.services.embeddings import (
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
)


class TestOpenAIEmbeddingProvider:
    """Test suite for OpenAI embedding provider."""

    def test_implements_protocol(self):
        """Test that OpenAIEmbeddingProvider satisfies the EmbeddingProvider protocol."""
        assert isinstance(OpenAIEmbeddingProvider(api_key="test-key"), EmbeddingProvider)

    @pytest.mark.asyncio
    async def test_generate_embedding(self):
        """Test embedding generation via OpenAI."""
        provider = OpenAIEmbeddingProvider(api_key="test-key")

        mock_embedding = [0.1, 0.2, 0.3]
        mock_data = MagicMock()
        mock_data.embedding = mock_embedding
        mock_response = MagicMock()
        mock_response.data = [mock_data]

        provider.client = MagicMock()
        provider.client.embeddings.create = AsyncMock(return_value=mock_response)

        result = await provider.generate_embedding("test text")

        assert result == mock_embedding
        provider.client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input="test text",
        )

    @pytest.mark.asyncio
    async def test_generate_embedding_custom_model(self):
        """Test embedding generation with a custom model name."""
        provider = OpenAIEmbeddingProvider(api_key="test-key", model="text-embedding-3-large")

        mock_data = MagicMock()
        mock_data.embedding = [0.5]
        mock_response = MagicMock()
        mock_response.data = [mock_data]

        provider.client = MagicMock()
        provider.client.embeddings.create = AsyncMock(return_value=mock_response)

        await provider.generate_embedding("test")

        provider.client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-large",
            input="test",
        )

    @pytest.mark.asyncio
    async def test_health_check_returns_true_on_success(self):
        """Health check returns True when the API responds successfully."""
        provider = OpenAIEmbeddingProvider(api_key="test-key")
        provider.client = MagicMock()
        provider.client.embeddings.create = AsyncMock(return_value=MagicMock())

        result = await provider.health_check()

        assert result is True
        provider.client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input="health check",
        )

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_error(self):
        """Health check returns False (not raises) when the API fails."""
        provider = OpenAIEmbeddingProvider(api_key="test-key")
        provider.client = MagicMock()
        provider.client.embeddings.create = AsyncMock(side_effect=RuntimeError("429 quota exhausted"))

        result = await provider.health_check()

        assert result is False


class TestGetEmbeddingProvider:
    """Test suite for provider factory."""

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_returns_openai_provider_by_default(self):
        """Test that the factory returns an OpenAI provider when no EMBEDDING_PROVIDER is set."""
        import hipeac_mcp.services.embeddings as mod

        mod._provider = None

        provider = get_embedding_provider()

        assert isinstance(provider, OpenAIEmbeddingProvider)
        mod._provider = None

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key_raises(self):
        """Test that missing OPENAI_API_KEY raises ValueError."""
        import hipeac_mcp.services.embeddings as mod

        mod._provider = None

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            get_embedding_provider()

        mod._provider = None

    @patch.dict(
        "os.environ",
        {"OPENAI_API_KEY": "test-key", "EMBEDDING_PROVIDER": "unsupported"},
        clear=True,
    )
    def test_unsupported_provider_raises(self):
        """Test that an unsupported provider raises ValueError."""
        import hipeac_mcp.services.embeddings as mod

        mod._provider = None

        with pytest.raises(ValueError, match="Unsupported embedding provider"):
            get_embedding_provider()

        mod._provider = None

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_singleton_behavior(self):
        """Test that the factory returns the same instance on repeated calls."""
        import hipeac_mcp.services.embeddings as mod

        mod._provider = None

        provider1 = get_embedding_provider()
        provider2 = get_embedding_provider()

        assert provider1 is provider2
        mod._provider = None

    @patch.dict(
        "os.environ",
        {"OPENAI_API_KEY": "test-key", "EMBEDDING_MODEL": "text-embedding-3-large"},
        clear=True,
    )
    def test_custom_model_from_env(self):
        """Test that EMBEDDING_MODEL env var is passed to the provider."""
        import hipeac_mcp.services.embeddings as mod

        mod._provider = None

        provider = get_embedding_provider()

        assert isinstance(provider, OpenAIEmbeddingProvider)
        assert provider.model == "text-embedding-3-large"
        mod._provider = None
