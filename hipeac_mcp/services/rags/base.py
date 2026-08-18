"""Base RAG service with FAISS vector storage."""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, cast

import faiss  # type: ignore[import-untyped]
import numpy as np
from django.conf import settings

from hipeac_mcp.services.embeddings import get_embedding_provider


logger = logging.getLogger(__name__)

type MetadataStore = dict[str, list[str | dict[str, str]]]


class BaseRagService:
    """Base class for RAG services using FAISS for vector storage."""

    # Must be defined by subclasses
    COLLECTION_NAME: str | None = None
    COLLECTION_DESCRIPTION: str | None = None

    # Class-level cache for indices
    _cache: dict[str, tuple[faiss.IndexFlatIP | None, MetadataStore, float]] = {}

    def __init__(self):
        """Initialize the RAG service with FAISS index and embedding provider."""
        if not self.COLLECTION_NAME:
            raise NotImplementedError("Subclasses must define COLLECTION_NAME")

        self.embedding_provider = get_embedding_provider()
        self.embedding_dimension: int | None = None
        self.index: faiss.IndexFlatIP | None = None
        self.metadata_store: MetadataStore = {"ids": [], "documents": [], "metadatas": []}

        self.index_dir = Path(settings.FAISS_INDEX_PATH)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.index_path = self.index_dir / f"{self.COLLECTION_NAME}.index"
        self.metadata_path = self.index_dir / f"{self.COLLECTION_NAME}.json"

        self._load_or_create_index()

    def _load_or_create_index(self) -> None:
        """Load existing FAISS index or create a new one.

        The class-level cache is keyed by collection name and shared across
        service instances within this process, but a *separate* process (e.g.
        a reindex management command) can rewrite the index files on disk at
        any time. Compare the cached entry's on-disk mtime against the file's
        current mtime and reload whenever they diverge, so a long-running
        server process picks up reindexes without needing a restart.
        """
        on_disk_mtime = self.index_path.stat().st_mtime if self.index_path.exists() else None

        if self.COLLECTION_NAME in self._cache:
            cached_index, cached_metadata, cached_mtime = self._cache[self.COLLECTION_NAME]
            if on_disk_mtime is None or cached_mtime == on_disk_mtime:
                self.index, self.metadata_store = cached_index, cached_metadata
                if self.index is not None:
                    self.embedding_dimension = self.index.d
                logger.info(f"Used cached index '{self.COLLECTION_NAME}'")
                return
            logger.info(f"On-disk index '{self.COLLECTION_NAME}' changed since caching — reloading")

        if self.index_path.exists() and self.metadata_path.exists():
            self.index = cast(faiss.IndexFlatIP, faiss.read_index(str(self.index_path)))  # type: ignore[no-untyped-call]
            with open(self.metadata_path) as f:
                self.metadata_store = json.load(f)
            self.embedding_dimension = self.index.d
            logger.info(f"Loaded existing index '{self.COLLECTION_NAME}' with {self.index.ntotal} vectors")
        else:
            self.index = None
            self.metadata_store = {"ids": [], "documents": [], "metadatas": []}
            logger.info(f"Created new index '{self.COLLECTION_NAME}'")

        self._update_cache()

    def _update_cache(self) -> None:
        """Update the in-memory cache with current index state and on-disk mtime."""
        if self.COLLECTION_NAME:
            mtime = self.index_path.stat().st_mtime if self.index_path.exists() else time.time()
            self._cache[self.COLLECTION_NAME] = (self.index, self.metadata_store, mtime)

    def _save_index(self) -> None:
        """Save FAISS index and metadata to disk."""
        if self.index:
            faiss.write_index(self.index, str(self.index_path))  # type: ignore[no-untyped-call]
        with open(self.metadata_path, "w") as f:
            json.dump(self.metadata_store, f)

        self._update_cache()

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for given text.

        :param text: Text to embed.
        :returns: List of float values representing the embedding.
        """
        return await self.embedding_provider.generate_embedding(text)

    async def health_check(self) -> bool:
        """Check if the embedding provider is operational.

        Call this before destructive operations (e.g. ``reset_index``) to
        avoid wiping a good index when the provider is down (quota exhausted,
        network failure, etc.).

        :returns: True if the provider can generate embeddings, False otherwise.
        """
        return await self.embedding_provider.health_check()

    async def _faiss_search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Run a single FAISS similarity search for one query string.

        :param query: Search query string.
        :param limit: Maximum number of raw chunk results to return.
        :returns: List of chunk result dictionaries sorted by descending similarity.
        """
        if self.index is None or self.index.ntotal == 0:  # type: ignore[union-attr]
            return []

        try:
            query_embedding = await self.generate_embedding(query)
            query_vector = np.array([query_embedding], dtype=np.float32)
            faiss.normalize_L2(query_vector)  # type: ignore[no-untyped-call]

            distances, indices = self.index.search(query_vector, min(limit, self.index.ntotal))  # type: ignore[union-attr]
            distances = cast(np.ndarray, distances)
            indices = cast(np.ndarray, indices)

            formatted_results: list[dict[str, Any]] = []

            for i, idx in enumerate(indices[0]):
                if idx == -1:
                    continue

                formatted_results.append(
                    {
                        "id": self.metadata_store["ids"][idx],
                        "content": self.metadata_store["documents"][idx],
                        "metadata": self.metadata_store["metadatas"][idx],
                        "similarity_score": float(distances[0][i]),
                    }
                )

            return formatted_results

        except Exception as e:
            logger.error(f"Error searching: {e}")
            return []

    async def _multi_query_search(self, queries: list[str], limit: int) -> list[dict[str, Any]]:
        """Run multiple FAISS searches in parallel and merge results by chunk ID.

        Each query produces a ranked list of chunks. Results are merged keeping
        the highest similarity score seen for each chunk across all queries, then
        re-sorted by score descending. This lets each semantic angle of a
        multi-faceted question surface its own best-matching chunks.

        :param queries: List of query strings (1–3 recommended).
        :param limit: Number of raw chunks to fetch per query.
        :returns: Merged and re-sorted list of chunk result dicts.
        """
        per_query_results = await asyncio.gather(*[self._faiss_search(q, limit) for q in queries])

        merged: dict[str, dict[str, Any]] = {}
        for chunk_list in per_query_results:
            for chunk in chunk_list:
                chunk_id = chunk["id"]
                if chunk_id not in merged or chunk["similarity_score"] > merged[chunk_id]["similarity_score"]:
                    merged[chunk_id] = chunk

        return sorted(merged.values(), key=lambda c: c["similarity_score"], reverse=True)

    async def search(self, queries: list[str] | str, limit: int = 10) -> list[dict[str, Any]]:
        """Search for documents using semantic similarity.

        Accepts one or more query strings. Multiple queries are searched in
        parallel and their raw chunk results merged (keeping the highest score
        per chunk), so each semantic angle has a fair chance to surface
        relevant documents.

        :param queries: One query string or a list of up to 3 query strings.
        :param limit: Maximum number of results to return.
        :returns: List of search result dictionaries sorted by descending similarity.
        """
        query_list = [queries] if isinstance(queries, str) else queries
        return await self._multi_query_search(query_list, limit)

    def upsert_documents(
        self, ids: list[str], documents: list[str], embeddings: list[list[float]], metadatas: list[dict[str, Any]]
    ) -> bool:
        """Upsert documents into the FAISS index.

        :param ids: List of document IDs.
        :param documents: List of document texts.
        :param embeddings: List of embedding vectors.
        :param metadatas: List of metadata dictionaries.
        :returns: True if successful, False otherwise.
        """
        try:
            if not embeddings:
                logger.warning(f"upsert_documents called with empty embeddings for '{self.COLLECTION_NAME}'")
                return False

            vectors = np.array(embeddings, dtype=np.float32)

            if self.index is None:
                self.embedding_dimension = vectors.shape[1]
                self.index = faiss.IndexFlatIP(self.embedding_dimension)
                logger.info(f"Initialized FAISS index with dimension {self.embedding_dimension}")

            faiss.normalize_L2(vectors)  # type: ignore[no-untyped-call]

            for i, doc_id in enumerate(ids):
                if doc_id in self.metadata_store["ids"]:
                    idx = self.metadata_store["ids"].index(doc_id)
                    self.metadata_store["documents"][idx] = documents[i]
                    self.metadata_store["metadatas"][idx] = metadatas[i]
                else:
                    self.metadata_store["ids"].append(doc_id)
                    self.metadata_store["documents"].append(documents[i])
                    self.metadata_store["metadatas"].append(metadatas[i])
                    self.index.add(vectors[i : i + 1])  # type: ignore[union-attr]

            self._save_index()
            return True

        except Exception as e:
            logger.error(f"Error upserting documents: {e}")
            return False

    def reset_index(self) -> bool:
        """Reset the index in memory without saving to disk.

        The cleared index is only persisted when ``upsert_documents``
        writes new data. This prevents a failed reindex from leaving
        an empty FAISS file on disk (losing the previous good index).

        :returns: True if successful.
        """
        try:
            if self.embedding_dimension:
                self.index = faiss.IndexFlatIP(self.embedding_dimension)
            else:
                self.index = None
            self.metadata_store = {"ids": [], "documents": [], "metadatas": []}
            self._update_cache()
            logger.info(f"Index '{self.COLLECTION_NAME}' reset in memory")
            return True

        except Exception as e:
            logger.error(f"Error resetting index '{self.COLLECTION_NAME}': {e}")
            return False
