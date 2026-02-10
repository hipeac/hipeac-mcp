"""Tests for DocumentProcessor."""

import pytest

from hipeac_mcp.services.document_processor import DocumentProcessor


@pytest.fixture
def processor():
    """Provide a DocumentProcessor instance.

    :returns: A DocumentProcessor.
    """
    return DocumentProcessor()


class TestCleanContent:
    """Tests for _clean_content."""

    def test_removes_html_tags(self, processor):
        """HTML tags are stripped from content."""
        assert processor._clean_content("<p>Hello <b>world</b></p>") == "Hello world"

    def test_removes_markdown_links(self, processor):
        """Markdown links are replaced with their text."""
        assert processor._clean_content("See [here](https://example.com) for more.") == "See here for more."

    def test_removes_markdown_formatting(self, processor):
        """Bold, italic, code markers, and headings are removed."""
        assert processor._clean_content("## A **bold** and *italic* `code`") == "A bold and italic code"

    def test_collapses_whitespace(self, processor):
        """Multiple spaces and newlines are collapsed."""
        assert processor._clean_content("Hello   \n\n  world") == "Hello world"

    def test_strips_leading_trailing_whitespace(self, processor):
        """Leading and trailing whitespace is removed."""
        assert processor._clean_content("  padded  ") == "padded"

    def test_empty_string(self, processor):
        """Empty input returns empty output."""
        assert processor._clean_content("") == ""


class TestChunkContent:
    """Tests for chunk_content."""

    def test_short_content_single_chunk(self, processor):
        """Content shorter than chunk size returns one chunk."""
        result = processor.chunk_content("Short text.", chunk_size=100)
        assert result == ["Short text."]

    def test_splits_on_sentence_boundaries(self, processor):
        """Chunks split at sentence boundaries."""
        content = "First sentence. Second sentence. Third sentence."
        result = processor.chunk_content(content, chunk_size=30)
        assert len(result) >= 2
        assert all(chunk.endswith(".") or chunk.endswith(". ") for chunk in result)

    def test_respects_chunk_size(self, processor):
        """Each chunk is approximately within chunk_size."""
        content = ". ".join(f"Sentence number {i}" for i in range(50)) + "."
        result = processor.chunk_content(content, chunk_size=100)
        assert all(len(chunk) <= 200 for chunk in result)

    def test_long_sentence_becomes_single_chunk(self, processor):
        """Content without sentence-ending punctuation stays as one chunk."""
        content = "word " * 200
        result = processor.chunk_content(content.strip(), chunk_size=50)
        assert len(result) == 1

    def test_empty_content(self, processor):
        """Empty content returns single empty chunk."""
        result = processor.chunk_content("", chunk_size=100)
        assert result == [""]


class TestPrepareChunksForEmbedding:
    """Tests for prepare_chunks_for_embedding."""

    def test_returns_chunk_dicts(self, processor):
        """Each chunk has id, content, and metadata."""
        result = processor.prepare_chunks_for_embedding(
            content="<p>Hello world.</p>",
            base_metadata={"slug": "test"},
            id_prefix="article_1",
            chunk_size=1000,
        )
        assert len(result) == 1
        assert result[0]["id"] == "article_1_chunk0"
        assert result[0]["content"] == "Hello world."
        assert result[0]["metadata"]["slug"] == "test"
        assert result[0]["metadata"]["chunk_index"] == 0

    def test_multiple_chunks_get_sequential_ids(self, processor):
        """Chunk IDs use sequential indices."""
        content = ". ".join(f"Sentence {i}" for i in range(50)) + "."
        result = processor.prepare_chunks_for_embedding(
            content=content,
            base_metadata={"type": "article"},
            id_prefix="doc",
            chunk_size=80,
        )
        assert len(result) >= 2
        for idx, chunk in enumerate(result):
            assert chunk["id"] == f"doc_chunk{idx}"
            assert chunk["metadata"]["chunk_index"] == idx

    def test_cleans_content_before_chunking(self, processor):
        """HTML and markdown are removed before chunking."""
        result = processor.prepare_chunks_for_embedding(
            content="<b>Bold</b> and [link](http://x.com).",
            base_metadata={},
            id_prefix="p",
        )
        assert "<b>" not in result[0]["content"]
        assert "http://x.com" not in result[0]["content"]

    def test_base_metadata_not_mutated(self, processor):
        """Original metadata dict is not modified."""
        metadata = {"slug": "test"}
        processor.prepare_chunks_for_embedding(
            content="Hello.",
            base_metadata=metadata,
            id_prefix="p",
        )
        assert "chunk_index" not in metadata
