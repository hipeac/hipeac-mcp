"""Tests for VisionDocumentGenerator."""

from unittest.mock import MagicMock

import pytest

from hipeac_mcp.services.rags.vision.generator import VisionDocumentGenerator


@pytest.fixture
def generator():
    """Create a VisionDocumentGenerator instance.

    :returns: Generator with default chunk size.
    """
    return VisionDocumentGenerator(chunk_size=800)


@pytest.fixture
def mock_article():
    """Create a mock VisionArticle with content_tree.

    :returns: Mock article with realistic content_tree structure.
    """
    article = MagicMock()
    article.title = "New Hardware"
    article.slug = "new-hardware"
    article.content = "Some **markdown** content with [links](http://example.com)."
    article.section.name = "Chapters"
    article.section.vision.year = 2025
    article.content_tree = {
        "slug": "chapters--new-hardware",
        "title": "New Hardware",
        "authors": [{"name": "Author One", "bio": None}],
        "elements": [
            {"text": "New Hardware", "level": 1},
            {"text": "Recommendations", "level": 2},
            {"text": "Develop specialized hardware", "level": 3},
            {"text": "The development of efficient hardware is essential for running services."},
            {"text": "Look beyond purely digital hardware", "level": 3},
            {"text": "Investigation of new accelerators using non-digital technologies."},
            {"text": "", "path": "image_1", "caption": "Figure 1: A diagram"},
            {"text": "Background", "level": 2},
            {"text": "The changes in the hardware arena since 2023 may be minor."},
            {"text": "AI accelerator hardware is dominating profits of top hardware manufacturers."},
        ],
        "keywords": [],
        "references": [
            {"code": "BBC-Willow", "text": "https://www.bbc.com/news/articles/example"},
        ],
    }
    return article


class TestChunksFromTree:
    """Tests for content_tree-based chunking."""

    def test_generates_chunks_from_content_tree(self, generator, mock_article):
        """Chunks are generated from content_tree elements."""
        chunks = generator.generate_chunks(mock_article)
        assert len(chunks) > 0
        assert all("content" in c and "metadata" in c and "id" in c for c in chunks)

    def test_chunk_ids_are_sequential(self, generator, mock_article):
        """Chunk IDs follow the pattern {year}_{slug}_chunk{n}."""
        chunks = generator.generate_chunks(mock_article)
        for i, chunk in enumerate(chunks):
            assert chunk["id"] == f"2025_new-hardware_chunk{i}"

    def test_heading_metadata_tracks_hierarchy(self, generator, mock_article):
        """Heading path in metadata reflects the heading hierarchy."""
        chunks = generator.generate_chunks(mock_article)
        # First chunk is under "Recommendations > Develop specialized hardware"
        assert "Recommendations" in chunks[0]["metadata"]["heading"]
        # Last chunk(s) should be under "Background"
        assert "Background" in chunks[-1]["metadata"]["heading"]

    def test_heading_prefix_in_content(self, generator, mock_article):
        """Chunk content is prefixed with the heading path for better embeddings."""
        chunks = generator.generate_chunks(mock_article)
        # First chunk should start with heading context
        assert chunks[0]["content"].startswith("New Hardware > Recommendations")
        # Paragraph text follows after double newline
        assert "\n\n" in chunks[0]["content"]

    def test_images_are_skipped(self, generator, mock_article):
        """Image elements (with 'path' key) do not appear in chunk content."""
        chunks = generator.generate_chunks(mock_article)
        all_content = " ".join(c["content"] for c in chunks)
        assert "image_1" not in all_content
        assert "Figure 1" not in all_content

    def test_references_are_not_indexed(self, generator, mock_article):
        """Reference blocks from content_tree are never embedded."""
        chunks = generator.generate_chunks(mock_article)
        all_content = " ".join(c["content"] for c in chunks)
        assert "BBC-Willow" not in all_content
        assert "bbc.com" not in all_content

    def test_headings_start_new_chunks(self, generator, mock_article):
        """Each heading boundary starts a new chunk."""
        # Use a very large chunk_size so merging won't interfere
        big_generator = VisionDocumentGenerator(chunk_size=10000)
        chunks = big_generator.generate_chunks(mock_article)
        # H3 "Develop specialized hardware" → 1 paragraph → chunk 0
        # H3 "Look beyond purely digital hardware" → 1 paragraph → chunk 1
        # H2 "Background" → 2 paragraphs merged → chunk 2
        assert len(chunks) == 3
        assert "Develop specialized hardware" in chunks[0]["metadata"]["heading"]
        assert "Look beyond" in chunks[1]["metadata"]["heading"]
        assert "Background" in chunks[2]["metadata"]["heading"]

    def test_chunk_size_splits_large_sections(self, generator, mock_article):
        """Sections with text exceeding chunk_size are split into multiple chunks."""
        # Make paragraphs long enough to exceed chunk_size=800
        mock_article.content_tree["elements"] = [
            {"text": "Section", "level": 1},
            {"text": "A" * 500},
            {"text": "B" * 500},
            {"text": "C" * 500},
        ]
        chunks = generator.generate_chunks(mock_article)
        assert len(chunks) >= 2

    def test_empty_content_tree_falls_back_to_content(self, generator, mock_article):
        """When content_tree has no elements, falls back to raw content."""
        mock_article.content_tree = {}
        chunks = generator.generate_chunks(mock_article)
        assert len(chunks) > 0
        # Should have cleaned the markdown
        all_content = " ".join(c["content"] for c in chunks)
        assert "**" not in all_content

    def test_base_metadata_on_all_chunks(self, generator, mock_article):
        """All chunks carry the base metadata fields."""
        chunks = generator.generate_chunks(mock_article)
        for chunk in chunks:
            assert chunk["metadata"]["title"] == "New Hardware"
            assert chunk["metadata"]["slug"] == "new-hardware"
            assert chunk["metadata"]["section"] == "Chapters"
            assert chunk["metadata"]["vision_year"] == 2025


class TestChunksFromContent:
    """Tests for the markdown fallback path."""

    def test_cleans_markdown_formatting(self, generator, mock_article):
        """Markdown syntax is stripped from content."""
        mock_article.content_tree = {}
        mock_article.content = "Some **bold** and *italic* text with `code`."
        chunks = generator.generate_chunks(mock_article)
        assert chunks[0]["content"] == "Some bold and italic text with code."

    def test_cleans_footnote_references(self, generator, mock_article):
        """Footnote definitions and references are removed."""
        mock_article.content_tree = {}
        mock_article.content = "Text with [^ref1] inline.\n[^ref1]: https://example.com"
        chunks = generator.generate_chunks(mock_article)
        all_content = " ".join(c["content"] for c in chunks)
        assert "ref1" not in all_content
        assert "example.com" not in all_content

    def test_cleans_images(self, generator, mock_article):
        """Markdown image syntax is stripped."""
        mock_article.content_tree = {}
        mock_article.content = "Before ![Alt text](image.png) after."
        chunks = generator.generate_chunks(mock_article)
        assert chunks[0]["content"] == "Before after."

    def test_inline_links_kept_as_text(self, generator, mock_article):
        """Inline links are converted to their text."""
        mock_article.content_tree = {}
        mock_article.content = "See [Google](https://google.com) for more."
        chunks = generator.generate_chunks(mock_article)
        assert chunks[0]["content"] == "See Google for more."


class TestShouldIndexArticle:
    """Tests for the year-matching guard."""

    def test_matches_correct_year(self, generator, mock_article):
        """Returns True when article year matches target year."""
        assert generator.should_index_article(mock_article, 2025) is True

    def test_rejects_wrong_year(self, generator, mock_article):
        """Returns False when article year does not match."""
        assert generator.should_index_article(mock_article, 2024) is False


class TestCleanMarkdown:
    """Tests for the static _clean_markdown method."""

    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("<p>Hello</p>", "Hello"),
            ("## Heading", "Heading"),
            ("[^ref]: https://example.com", ""),
            ("![alt](img.png)", ""),
            ("[link](url)", "link"),
            ("::: note\nContent", "Content"),
            ("**bold** and *italic*", "bold and italic"),
        ],
    )
    def test_clean_markdown(self, input_text, expected):
        """Various markdown patterns are cleaned correctly."""
        result = VisionDocumentGenerator._clean_markdown(input_text)
        assert result == expected
