"""Tests for the base RAG service with FAISS vector storage."""

from unittest.mock import AsyncMock, MagicMock, patch

import faiss
import numpy as np
import pytest

from hipeac_mcp.services.rags.base import BaseRagService


class ConcreteRagService(BaseRagService):
    """Concrete subclass for testing BaseRagService."""

    COLLECTION_NAME = "test_collection"
    COLLECTION_DESCRIPTION = "Test collection for unit tests"


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the class-level index cache before and after each test."""
    BaseRagService._cache.clear()
    yield
    BaseRagService._cache.clear()


@pytest.fixture
def mock_faiss_paths(tmp_path):
    """Provide a temporary directory for FAISS index files."""
    with patch("hipeac_mcp.services.rags.base.settings") as mock_settings:
        mock_settings.FAISS_INDEX_PATH = str(tmp_path)
        yield tmp_path


@pytest.fixture
def mock_embedding_provider():
    """Provide a mock embedding provider."""
    mock_provider = MagicMock()
    mock_provider.generate_embedding = AsyncMock(return_value=[0.1] * 128)
    with patch("hipeac_mcp.services.rags.base.get_embedding_provider", return_value=mock_provider):
        yield mock_provider


class TestBaseRagServiceInit:
    """Tests for BaseRagService initialization."""

    def test_raises_without_collection_name(self, mock_faiss_paths, mock_embedding_provider):
        """Subclass without COLLECTION_NAME raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Subclasses must define COLLECTION_NAME"):

            class NoNameService(BaseRagService):
                COLLECTION_NAME = None

            NoNameService()

    def test_creates_index_directory(self, mock_faiss_paths, mock_embedding_provider):
        """Index directory is created on initialization."""
        service = ConcreteRagService()
        assert mock_faiss_paths.exists()
        assert service.COLLECTION_NAME == "test_collection"

    def test_starts_with_no_index(self, mock_faiss_paths, mock_embedding_provider):
        """New service starts with no index and empty metadata store."""
        service = ConcreteRagService()
        assert service.index is None
        assert service.metadata_store == {"ids": [], "documents": [], "metadatas": []}

    def test_loads_from_cache(self, mock_faiss_paths, mock_embedding_provider):
        """Second instantiation loads from class-level cache."""
        first = ConcreteRagService()
        first.index = faiss.IndexFlatIP(128)
        first._update_cache()

        second = ConcreteRagService()
        assert second.index is first.index


class TestUpsertDocuments:
    """Tests for upsert_documents."""

    def test_upserts_new_documents(self, mock_faiss_paths, mock_embedding_provider):
        """New documents are added to the index."""
        service = ConcreteRagService()

        embeddings = np.random.rand(2, 128).tolist()
        result = service.upsert_documents(
            ids=["doc1", "doc2"],
            documents=["First document", "Second document"],
            embeddings=embeddings,
            metadatas=[{"key": "val1"}, {"key": "val2"}],
        )

        assert result is True
        assert service.index is not None
        assert service.index.ntotal == 2
        assert service.metadata_store["ids"] == ["doc1", "doc2"]

    def test_updates_existing_document_metadata(self, mock_faiss_paths, mock_embedding_provider):
        """Upserting with an existing ID updates metadata without duplicating vectors."""
        service = ConcreteRagService()

        embeddings = [[0.1] * 128]
        service.upsert_documents(["doc1"], ["Original"], embeddings, [{"v": 1}])
        service.upsert_documents(["doc1"], ["Updated"], embeddings, [{"v": 2}])

        assert service.index.ntotal == 1
        assert service.metadata_store["documents"][0] == "Updated"
        assert service.metadata_store["metadatas"][0] == {"v": 2}

    def test_returns_false_on_error(self, mock_faiss_paths, mock_embedding_provider):
        """Returns False when an error occurs during upsert."""
        service = ConcreteRagService()
        result = service.upsert_documents(
            ids=["doc1"],
            documents=["doc"],
            embeddings="not-a-list",  # type: ignore[arg-type]
            metadatas=[{}],
        )

        assert result is False


class TestSearch:
    """Tests for search."""

    @pytest.fixture
    def indexed_service(self, mock_faiss_paths, mock_embedding_provider):
        """Provide a service with pre-indexed documents."""
        service = ConcreteRagService()
        embeddings = np.random.rand(3, 128).astype(np.float32)
        # Normalize so cosine similarity works
        faiss.normalize_L2(embeddings)
        service.upsert_documents(
            ids=["a", "b", "c"],
            documents=["alpha content", "beta content", "gamma content"],
            embeddings=embeddings.tolist(),
            metadatas=[{"tag": "a"}, {"tag": "b"}, {"tag": "c"}],
        )
        return service

    async def test_returns_empty_when_no_index(self, mock_faiss_paths, mock_embedding_provider):
        """Search returns empty list when index is None."""
        service = ConcreteRagService()
        assert service.index is None
        results = await service.search("anything")
        assert results == []

    async def test_returns_results(self, indexed_service, mock_embedding_provider):
        """Search returns results with expected structure."""
        results = await indexed_service.search("query", limit=2)
        assert len(results) <= 2
        for result in results:
            assert "id" in result
            assert "content" in result
            assert "metadata" in result
            assert "similarity_score" in result

    async def test_returns_empty_on_error(self, mock_faiss_paths, mock_embedding_provider):
        """Search returns empty list when the embedding call fails on a non-empty index."""
        service = ConcreteRagService()
        # Add a document so the index is non-empty (avoids the early ntotal==0 exit)
        embeddings = np.random.rand(1, 128).tolist()
        service.upsert_documents(["doc1"], ["content"], embeddings, [{}])
        mock_embedding_provider.generate_embedding = AsyncMock(side_effect=RuntimeError("API down"))

        results = await service.search("query")
        assert results == []

    async def test_skips_invalid_faiss_indices(self, indexed_service, mock_embedding_provider):
        """Idx == -1 entries returned by FAISS are silently skipped."""
        # Request more results than the index contains — FAISS pads with -1
        results = await indexed_service._faiss_search("query", limit=100)
        # All three documents were indexed; none should be -1
        assert len(results) == 3
        assert all(r["id"] != -1 for r in results)


class TestResetIndex:
    """Tests for reset_index."""

    def test_resets_populated_index(self, mock_faiss_paths, mock_embedding_provider):
        """Index is cleared after reset."""
        service = ConcreteRagService()
        embeddings = np.random.rand(2, 128).tolist()
        service.upsert_documents(["a", "b"], ["x", "y"], embeddings, [{}, {}])
        assert service.index.ntotal == 2

        result = service.reset_index()

        assert result is True
        assert service.index.ntotal == 0
        assert service.metadata_store == {"ids": [], "documents": [], "metadatas": []}

    def test_resets_empty_index(self, mock_faiss_paths, mock_embedding_provider):
        """Reset works even when no index exists."""
        service = ConcreteRagService()
        assert service.index is None

        result = service.reset_index()

        assert result is True
        assert service.index is None

    def test_returns_false_on_error(self, mock_faiss_paths, mock_embedding_provider):
        """reset_index returns False when an internal error occurs."""
        service = ConcreteRagService()
        with patch.object(service, "_update_cache", side_effect=RuntimeError("cache failure")):
            result = service.reset_index()
        assert result is False


class TestSaveAndLoad:
    """Tests for index persistence."""

    def test_save_and_reload(self, mock_faiss_paths, mock_embedding_provider):
        """Index can be saved to disk and loaded back."""
        service = ConcreteRagService()
        embeddings = np.random.rand(2, 128).tolist()
        service.upsert_documents(["d1", "d2"], ["doc one", "doc two"], embeddings, [{"k": 1}, {"k": 2}])

        # Clear cache to force reload from disk
        BaseRagService._cache.clear()

        reloaded = ConcreteRagService()
        assert reloaded.index is not None
        assert reloaded.index.ntotal == 2
        assert reloaded.metadata_store["ids"] == ["d1", "d2"]
