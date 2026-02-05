"""Tests for VisionRagService static methods."""

from hipeac_mcp.services.rags.vision.service import VisionRagService


class TestExtractReferenceCodes:
    """Tests for _extract_reference_codes."""

    def test_extracts_simple_codes(self):
        """Single-word reference codes are extracted."""
        chunks = ["This is about quantum computing [Willow] and its impact."]
        assert VisionRagService._extract_reference_codes(chunks) == {"Willow"}

    def test_extracts_hyphenated_codes(self):
        """Hyphenated reference codes like [CRA-EU] are extracted."""
        chunks = ["The regulation [CRA-EU] mandates compliance [CRA-wiki]."]
        assert VisionRagService._extract_reference_codes(chunks) == {"CRA-EU", "CRA-wiki"}

    def test_extracts_codes_with_underscores(self):
        """Codes with underscores are extracted."""
        chunks = ["See [some_ref] for details."]
        assert VisionRagService._extract_reference_codes(chunks) == {"some_ref"}

    def test_extracts_from_multiple_chunks(self):
        """Codes are collected across all chunks."""
        chunks = ["First chunk [RefA].", "Second chunk [RefB] and [RefC]."]
        assert VisionRagService._extract_reference_codes(chunks) == {"RefA", "RefB", "RefC"}

    def test_deduplicates_codes(self):
        """Duplicate codes across chunks are deduplicated."""
        chunks = ["Chunk one [RefA].", "Chunk two [RefA] again."]
        assert VisionRagService._extract_reference_codes(chunks) == {"RefA"}

    def test_empty_chunks(self):
        """Empty chunk list returns empty set."""
        assert VisionRagService._extract_reference_codes([]) == set()

    def test_no_references(self):
        """Chunks without reference markers return empty set."""
        chunks = ["No references here.", "Or here either."]
        assert VisionRagService._extract_reference_codes(chunks) == set()

    def test_ignores_non_alphanumeric_brackets(self):
        """Bracket content with spaces or special chars is ignored."""
        chunks = ["This [is not a ref] and [also not one!]."]
        assert VisionRagService._extract_reference_codes(chunks) == set()


class TestResolveInlineReferences:
    """Tests for _resolve_inline_references."""

    def test_resolves_url_references(self):
        """Inline markers are replaced with markdown links."""
        text = "See [BBC-Willow] for details."
        refs = [{"code": "BBC-Willow", "text": "https://www.bbc.com/news/articles/example"}]
        result = VisionRagService._resolve_inline_references(text, refs)
        assert result == "See [BBC-Willow](https://www.bbc.com/news/articles/example) for details."

    def test_extracts_url_from_citation_text(self):
        """URL is extracted from longer citation text."""
        text = "As noted in [DraghiReport]."
        refs = [{"code": "DraghiReport", "text": "European Commission. The Future. https://ec.europa.eu/report"}]
        result = VisionRagService._resolve_inline_references(text, refs)
        assert result == "As noted in [DraghiReport](https://ec.europa.eu/report)."

    def test_no_url_in_reference_leaves_marker(self):
        """Markers without a URL in the reference text are left unchanged."""
        text = "See [SomeRef] for details."
        refs = [{"code": "SomeRef", "text": "A book title with no URL"}]
        result = VisionRagService._resolve_inline_references(text, refs)
        assert result == "See [SomeRef] for details."

    def test_multiple_references(self):
        """Multiple markers are resolved independently."""
        text = "Sources [RefA] and [RefB]."
        refs = [
            {"code": "RefA", "text": "https://example.com/a"},
            {"code": "RefB", "text": "https://example.com/b"},
        ]
        result = VisionRagService._resolve_inline_references(text, refs)
        assert "[RefA](https://example.com/a)" in result
        assert "[RefB](https://example.com/b)" in result

    def test_empty_references(self):
        """Empty references list returns text unchanged."""
        text = "No refs here."
        assert VisionRagService._resolve_inline_references(text, []) == text

    def test_marker_not_in_text(self):
        """References not matching any marker leave text unchanged."""
        text = "No markers here."
        refs = [{"code": "RefA", "text": "https://example.com"}]
        assert VisionRagService._resolve_inline_references(text, refs) == text


class TestTruncateOnWordBoundary:
    """Tests for _truncate_on_word_boundary."""

    def test_short_text_unchanged(self):
        """Text shorter than max_length is returned as-is."""
        assert VisionRagService._truncate_on_word_boundary("Short text.", 800) == "Short text."

    def test_cuts_at_last_space(self):
        """Truncation happens at the last space before max_length."""
        text = "word " * 200
        result = VisionRagService._truncate_on_word_boundary(text, 50)
        assert len(result) <= 50
        assert result.endswith("word")

    def test_preserves_complete_link(self):
        """Markdown links within max_length are kept intact."""
        text = "See [Ref](https://example.com) ok. " + "x " * 400
        result = VisionRagService._truncate_on_word_boundary(text, 50)
        assert "[Ref](https://example.com)" in result

    def test_extends_to_include_broken_link(self):
        """If cut falls inside a markdown link, extends to include it."""
        text = "Before. [Ref](https://example.com/very/long/path) after."
        cut_inside_link = text.index("[Ref]") + 5
        result = VisionRagService._truncate_on_word_boundary(text, cut_inside_link)
        assert "[Ref](https://example.com/very/long/path)" in result
