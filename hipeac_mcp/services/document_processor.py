"""Document processing utilities for RAG services."""

import re
from typing import Any


class DocumentProcessor:
    """Processes documents for embedding and storage in the vector database.

    Provides text cleaning and chunking functionality for optimal RAG performance.
    """

    def _clean_content(self, content: str) -> str:
        """Clean content by removing markdown and HTML tags.

        :param content: Raw content string
        :returns: Cleaned content string
        """
        content = re.sub(r"<[^>]+>", "", content)
        content = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", content)
        content = re.sub(r"[*_`#]+", "", content)
        content = re.sub(r"\s+", " ", content)
        content = content.strip()

        return content

    def chunk_content(self, content: str, chunk_size: int = 1000) -> list[str]:
        """Split content into chunks of approximately chunk_size characters.

        Uses sentence boundaries to avoid breaking semantic units.

        :param content: Cleaned content string
        :param chunk_size: Desired chunk size in characters
        :returns: List of content chunks
        """
        content = content.strip()
        if len(content) <= chunk_size:
            return [content]

        sentences = re.split(r"(?<=[.!?]) +", content)
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk) + len(sentence) < chunk_size:
                current_chunk += sentence + " "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + " "

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def prepare_chunks_for_embedding(
        self, content: str, base_metadata: dict[str, Any], id_prefix: str, chunk_size: int = 1000
    ) -> list[dict[str, Any]]:
        """Prepare content chunks for embedding with metadata.

        :param content: Raw content to process
        :param base_metadata: Base metadata to attach to all chunks
        :param id_prefix: Prefix for chunk IDs (e.g., "article_123")
        :param chunk_size: Desired chunk size in characters
        :returns: List of chunk dictionaries with content and metadata
        """
        cleaned_content = self._clean_content(content)
        chunks = self.chunk_content(cleaned_content, chunk_size)
        chunk_dicts = []

        for idx, chunk in enumerate(chunks):
            metadata = base_metadata.copy()
            metadata["chunk_index"] = idx

            chunk_dicts.append({"id": f"{id_prefix}_chunk{idx}", "content": chunk, "metadata": metadata})

        return chunk_dicts
