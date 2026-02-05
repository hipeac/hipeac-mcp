"""Vision document generator for RAG indexing.

Transforms VisionArticle database models into searchable text chunks with metadata,
using the structured ``content_tree`` JSON field for section-aware chunking.
"""

import logging
import re
from typing import Any

from hipeac_mcp.models.vision import VisionArticle


logger = logging.getLogger(__name__)


class VisionDocumentGenerator:
    """Generates searchable documents from Vision articles.

    Uses the article's ``content_tree`` for section-aware chunking. The tree
    provides clean paragraph text with explicit heading levels, avoiding the
    noise from markdown footnotes, reference blocks, and formatting syntax.

    Falls back to raw ``content`` with basic cleaning if ``content_tree`` is empty.
    """

    def __init__(self, chunk_size: int = 1500):
        """Initialize the generator.

        :param chunk_size: Target size for text chunks in characters.
        """
        self.chunk_size = chunk_size

    def generate_chunks(self, article: VisionArticle) -> list[dict[str, Any]]:
        """Generate searchable chunks from a Vision article.

        :param article: VisionArticle model instance.
        :returns: List of chunk dictionaries with content and metadata.
        """
        base_metadata: dict[str, Any] = {
            "title": article.title,
            "slug": article.slug,
            "section": article.section.name,
            "vision_year": article.section.vision.year,
        }
        id_prefix = f"{article.section.vision.year}_{article.slug}"

        tree = article.content_tree or {}
        elements = tree.get("elements", [])

        if elements:
            chunks = self._chunks_from_tree(elements, base_metadata, id_prefix)
        else:
            chunks = self._chunks_from_content(article.content or "", base_metadata, id_prefix)

        logger.debug(f"Generated {len(chunks)} chunks for article '{article.slug}'")
        return chunks

    def _chunks_from_tree(
        self, elements: list[dict[str, Any]], base_metadata: dict[str, Any], id_prefix: str
    ) -> list[dict[str, Any]]:
        """Create chunks from content_tree elements with section-aware boundaries.

        Walks elements in order, tracking the heading hierarchy. Paragraphs are
        merged into chunks respecting ``chunk_size``, with a new chunk started
        whenever a heading is encountered.

        :param elements: The ``content_tree.elements`` list.
        :param base_metadata: Base metadata to attach to all chunks.
        :param id_prefix: Prefix for chunk IDs.
        :returns: List of chunk dictionaries.
        """
        chunks: list[dict[str, Any]] = []
        heading_stack: list[str] = []
        current_text = ""
        chunk_index = 0

        def flush_chunk() -> None:
            nonlocal current_text, chunk_index
            text = current_text.strip()
            if not text:
                return
            heading_path = " > ".join(heading_stack)
            prefixed_content = f"{heading_path}\n\n{text}" if heading_path else text
            metadata = {**base_metadata, "chunk_index": chunk_index, "heading": heading_path}
            chunks.append({"id": f"{id_prefix}_chunk{chunk_index}", "content": prefixed_content, "metadata": metadata})
            chunk_index += 1
            current_text = ""

        for element in elements:
            level = element.get("level")
            text = element.get("text", "").strip()

            if level is not None:
                # Heading element: flush current chunk and update heading stack
                flush_chunk()
                # Trim stack to parent level, then push this heading
                heading_stack = heading_stack[: level - 1]
                if text:  # skip empty headings (decorative H4s, etc.)
                    heading_stack.append(text)
                continue

            # Skip images (elements with 'path' but no text)
            if not text:
                continue

            # Paragraph element
            if len(current_text) + len(text) > self.chunk_size and current_text:
                flush_chunk()

            current_text += (" " if current_text else "") + text

        flush_chunk()
        return chunks

    def _chunks_from_content(self, content: str, base_metadata: dict[str, Any], id_prefix: str) -> list[dict[str, Any]]:
        """Fallback: create chunks from raw markdown content.

        Used when ``content_tree`` is not available. Applies basic cleaning
        (strip HTML, markdown links, formatting) and sentence-boundary chunking.

        :param content: Raw markdown content.
        :param base_metadata: Base metadata to attach to all chunks.
        :param id_prefix: Prefix for chunk IDs.
        :returns: List of chunk dictionaries.
        """
        cleaned = self._clean_markdown(content)
        if not cleaned:
            return []

        sentences = re.split(r"(?<=[.!?]) +", cleaned)
        chunks: list[dict[str, Any]] = []
        current_chunk = ""
        chunk_index = 0

        for sentence in sentences:
            if len(current_chunk) + len(sentence) > self.chunk_size and current_chunk:
                metadata = {**base_metadata, "chunk_index": chunk_index}
                chunks.append(
                    {
                        "id": f"{id_prefix}_chunk{chunk_index}",
                        "content": current_chunk.strip(),
                        "metadata": metadata,
                    }
                )
                chunk_index += 1
                current_chunk = ""
            current_chunk += sentence + " "

        if current_chunk.strip():
            metadata = {**base_metadata, "chunk_index": chunk_index}
            chunks.append(
                {
                    "id": f"{id_prefix}_chunk{chunk_index}",
                    "content": current_chunk.strip(),
                    "metadata": metadata,
                }
            )

        return chunks

    @staticmethod
    def _clean_markdown(content: str) -> str:
        """Strip HTML tags, markdown links, and formatting from raw content.

        :param content: Raw markdown string.
        :returns: Cleaned plain text.
        """
        content = re.sub(r"<[^>]+>", "", content)
        content = re.sub(r"\[\^[^\]]*\]:?[^\n]*", "", content)  # footnote defs and refs
        content = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", content)  # images
        content = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", content)  # inline links → text
        content = re.sub(r"^#{1,6}\s+", "", content, flags=re.MULTILINE)  # headings
        content = re.sub(r"[*_`]+", "", content)
        content = re.sub(r"^:::[^\n]*$", "", content, flags=re.MULTILINE)  # admonitions
        content = re.sub(r"\s+", " ", content)
        return content.strip()

    def should_index_article(self, article: VisionArticle, target_year: int) -> bool:
        """Check if article should be indexed for the target year.

        :param article: VisionArticle to check.
        :param target_year: Target Vision year for indexing.
        :returns: True if article matches target year.
        """
        return article.section.vision.year == target_year
