"""Tests for VisionRagService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

    def test_cuts_at_max_length_when_no_space_before_limit(self):
        """When no space exists before max_length, cuts exactly at max_length."""
        result = VisionRagService._truncate_on_word_boundary("ABCDEFGHIJ", 5)
        assert result == "ABCDE"


class TestAggregateChunks:
    """Tests for _aggregate_chunks."""

    @pytest.fixture
    def service(self):
        """Provide a VisionRagService with mocked dependencies.

        :returns: A VisionRagService instance.
        """
        with (
            patch("hipeac_mcp.services.rags.vision.service.VisionDocumentGenerator"),
            patch.object(VisionRagService, "_load_or_create_index"),
        ):
            return VisionRagService(year=2025)

    def test_aggregates_chunks_by_slug(self, service):
        """Chunks from the same article are grouped under one slug."""
        base_results = [
            {
                "content": "Chunk 1",
                "similarity_score": 0.9,
                "metadata": {"slug": "ai", "title": "AI", "section": "Chapters"},
            },
            {
                "content": "Chunk 2",
                "similarity_score": 0.8,
                "metadata": {"slug": "ai", "title": "AI", "section": "Chapters"},
            },
        ]
        result = service._aggregate_chunks(base_results)

        assert len(result) == 1
        assert result["ai"]["chunks"] == ["Chunk 1", "Chunk 2"]

    def test_keeps_highest_similarity_score(self, service):
        """Aggregated article keeps the max similarity score across chunks."""
        base_results = [
            {"content": "A", "similarity_score": 0.7, "metadata": {"slug": "s", "title": "T", "section": "S"}},
            {"content": "B", "similarity_score": 0.9, "metadata": {"slug": "s", "title": "T", "section": "S"}},
        ]
        result = service._aggregate_chunks(base_results)
        assert result["s"]["similarity_score"] == 0.9

    def test_distinct_slugs_are_separate(self, service):
        """Different slugs produce separate entries."""
        base_results = [
            {"content": "A", "similarity_score": 0.8, "metadata": {"slug": "a", "title": "A", "section": "S"}},
            {"content": "B", "similarity_score": 0.7, "metadata": {"slug": "b", "title": "B", "section": "S"}},
        ]
        result = service._aggregate_chunks(base_results)
        assert len(result) == 2

    def test_empty_results(self, service):
        """Empty input returns empty dict."""
        assert service._aggregate_chunks([]) == {}

    def test_includes_vision_year_from_metadata(self, service):
        """Vision year is taken from metadata when available."""
        base_results = [
            {
                "content": "X",
                "similarity_score": 0.5,
                "metadata": {"slug": "x", "title": "X", "section": "S", "vision_year": 2024},
            },
        ]
        result = service._aggregate_chunks(base_results)
        assert result["x"]["vision_year"] == 2024


class TestSearch:
    """Tests for the search method."""

    @pytest.fixture
    def service(self):
        """Provide a VisionRagService with mocked FAISS.

        :returns: A VisionRagService instance.
        """
        with (
            patch("hipeac_mcp.services.rags.vision.service.VisionDocumentGenerator"),
            patch.object(VisionRagService, "_load_or_create_index"),
        ):
            return VisionRagService(year=2025)

    async def test_returns_aggregated_results(self, service):
        """Search returns formatted, aggregated results."""
        chunk_results = [
            {
                "content": "AI is cool.",
                "similarity_score": 0.9,
                "metadata": {"slug": "ai", "title": "AI", "section": "Chapters"},
            },
            {
                "content": "AI is great.",
                "similarity_score": 0.8,
                "metadata": {"slug": "ai", "title": "AI", "section": "Chapters"},
            },
        ]

        with (
            patch.object(service, "_multi_query_search", new_callable=AsyncMock, return_value=chunk_results),
            patch.object(service, "_enrich_from_database", new_callable=AsyncMock),
        ):
            results, is_fallback = await service.search("artificial intelligence")

        assert len(results) == 1
        assert results[0]["slug"] == "ai"
        assert "content_preview" in results[0]
        assert is_fallback is False

    async def test_returns_empty_on_error(self, service):
        """Search returns empty list when FAISS raises an exception."""
        with patch.object(service, "_multi_query_search", new_callable=AsyncMock, side_effect=RuntimeError("FAISS")):
            results, is_fallback = await service.search("query")

        assert results == []
        assert is_fallback is False

    async def test_no_score_boost_for_chapters(self, service):
        """Chapter articles do not receive a score boost; score is unchanged."""
        chunk_results = [
            {
                "content": "Content.",
                "similarity_score": 0.7,
                "metadata": {"slug": "ch", "title": "T", "section": "Chapters"},
            },
        ]

        with (
            patch.object(service, "_multi_query_search", new_callable=AsyncMock, return_value=chunk_results),
            patch.object(service, "_enrich_from_database", new_callable=AsyncMock),
        ):
            results, is_fallback = await service.search("test")

        assert results[0]["similarity_score"] == pytest.approx(0.7)
        assert is_fallback is False


class TestSearchArticles:
    """Tests for search_articles."""

    @pytest.fixture
    def service(self):
        """Provide a VisionRagService with mocked dependencies.

        :returns: A VisionRagService instance.
        """
        with (
            patch("hipeac_mcp.services.rags.vision.service.VisionDocumentGenerator"),
            patch.object(VisionRagService, "_load_or_create_index"),
        ):
            return VisionRagService(year=2025)

    async def test_returns_vision_search_response(self, service):
        """search_articles wraps search results into VisionSearchResponse."""
        search_results = [
            {
                "slug": "quantum",
                "title": "Quantum Computing",
                "section": "Chapters",
                "summary": "About quantum.",
                "vision_year": 2025,
                "is_draft": False,
                "similarity_score": 0.85,
                "content_preview": "Quantum is...",
                "references": [{"code": "Ref1", "text": "Citation"}],
                "url": "/vision/2025/quantum/",
            }
        ]

        with patch.object(service, "search", new_callable=AsyncMock, return_value=(search_results, False)):
            response = await service.search_articles("quantum computing")

        assert response.query == "quantum computing"
        assert response.total_results == 1
        assert response.articles[0].slug == "quantum"
        assert response.articles[0].url == "https://www.hipeac.net/vision/2025/quantum/"

    async def test_passes_queries_to_search(self, service):
        """search_articles delegates to search with the provided queries."""
        with patch.object(service, "search", new_callable=AsyncMock, return_value=([], False)) as mock_search:
            await service.search_articles("query")

        mock_search.assert_called_once_with("query")


class TestIndexArticle:
    """Tests for index_article."""

    @pytest.fixture
    def service(self):
        """Provide a VisionRagService with mocked dependencies.

        :returns: A VisionRagService instance.
        """
        with (
            patch("hipeac_mcp.services.rags.vision.service.VisionDocumentGenerator") as mock_gen_cls,
            patch.object(VisionRagService, "_load_or_create_index"),
        ):
            svc = VisionRagService(year=2025)
            svc.generator = mock_gen_cls.return_value
            return svc

    async def test_indexes_article_chunks(self, service):
        """Article chunks are embedded and upserted."""
        article = MagicMock()
        article.slug = "ai"
        article.pk = 1
        article.section.vision.year = 2025

        service.generator.should_index_article.return_value = True
        service.generator.generate_chunks.return_value = [
            {"id": "2025_ai_chunk0", "content": "AI content.", "metadata": {"slug": "ai"}},
        ]

        with (
            patch.object(service, "generate_embedding", new_callable=AsyncMock, return_value=[0.1, 0.2]),
            patch.object(service, "upsert_documents", return_value=True) as mock_upsert,
        ):
            result = await service.index_article(article)

        assert result is True
        mock_upsert.assert_called_once()

    async def test_skips_wrong_year(self, service):
        """Articles from a different year are skipped."""
        article = MagicMock()
        article.slug = "old"
        article.section.vision.year = 2023

        service.generator.should_index_article.return_value = False

        result = await service.index_article(article)
        assert result is False

    async def test_returns_false_on_error(self, service):
        """Errors during indexing return False."""
        article = MagicMock()
        article.slug = "err"
        article.pk = 2
        article.section.vision.year = 2025

        service.generator.should_index_article.return_value = True
        service.generator.generate_chunks.side_effect = RuntimeError("parse error")

        result = await service.index_article(article)
        assert result is False

    async def test_returns_false_when_no_chunks_generated(self, service):
        """Empty chunk list skips upsert and returns False without raising IndexError.

        Regression test for HIPEAC-MCP-15: np.array([]) produces a 1D array
        so vectors.shape[1] raises IndexError: tuple index out of range.
        """
        article = MagicMock()
        article.slug = "empty"
        article.pk = 3
        article.section.vision.year = 2025

        service.generator.should_index_article.return_value = True
        service.generator.generate_chunks.return_value = []

        with patch.object(service, "upsert_documents") as mock_upsert:
            result = await service.index_article(article)

        assert result is False
        mock_upsert.assert_not_called()


class TestEnrichFromDatabase:
    """Tests for _enrich_from_database."""

    @staticmethod
    def _make_async_iter(items):
        """Return an object with __aiter__ that yields items.

        :param items: Items to yield.
        :returns: MagicMock with async iteration support.
        """

        async def _gen(self):
            for item in items:
                yield item

        mock_qs = MagicMock()
        mock_qs.__aiter__ = _gen
        return mock_qs

    @pytest.fixture
    def service(self):
        """Provide a VisionRagService with mocked dependencies.

        :returns: A VisionRagService instance.
        """
        with (
            patch("hipeac_mcp.services.rags.vision.service.VisionDocumentGenerator"),
            patch.object(VisionRagService, "_load_or_create_index"),
        ):
            return VisionRagService(year=2025)

    @patch("hipeac_mcp.services.rags.vision.service.ensure_connection_async", new_callable=AsyncMock)
    async def test_enriches_summary_and_url(self, mock_conn, service):
        """Aggregated entry is updated with summary and URL from the database."""
        article = MagicMock()
        article.slug = "ai"
        article.is_aggregate = False
        article.get_absolute_url.return_value = "/vision/2025/ai/"
        article.get_summary.return_value = "About AI."
        article.content_tree = {}

        aggregated = {
            "ai": {"slug": "ai", "vision_year": 2025, "similarity_score": 0.8, "chunks": [], "references": []}
        }

        with patch("hipeac_mcp.services.rags.vision.service.VisionArticle") as mock_cls:
            mock_cls.objects.filter.return_value.select_related.return_value.only.return_value = self._make_async_iter(
                [article]
            )
            await service._enrich_from_database(aggregated)

        assert aggregated["ai"]["summary"] == "About AI."
        assert "/vision/2025/ai/" in aggregated["ai"]["url"]

    @patch("hipeac_mcp.services.rags.vision.service.ensure_connection_async", new_callable=AsyncMock)
    async def test_applies_penalty_to_aggregate_articles(self, mock_conn, service):
        """is_aggregate=True reduces the similarity score by AGGREGATE_SCORE_PENALTY."""
        from hipeac_mcp.services.rags.vision.service import AGGREGATE_SCORE_PENALTY

        article = MagicMock()
        article.slug = "recs"
        article.is_aggregate = True
        article.get_absolute_url.return_value = "/vision/2025/recs/"
        article.get_summary.return_value = ""
        article.content_tree = {}

        aggregated = {
            "recs": {"slug": "recs", "vision_year": 2025, "similarity_score": 1.0, "chunks": [], "references": []}
        }

        with patch("hipeac_mcp.services.rags.vision.service.VisionArticle") as mock_cls:
            mock_cls.objects.filter.return_value.select_related.return_value.only.return_value = self._make_async_iter(
                [article]
            )
            await service._enrich_from_database(aggregated)

        assert aggregated["recs"]["similarity_score"] == pytest.approx(AGGREGATE_SCORE_PENALTY)

    @patch("hipeac_mcp.services.rags.vision.service.ensure_connection_async", new_callable=AsyncMock)
    async def test_filters_references_to_cited_ones(self, mock_conn, service):
        """Only references cited in the matched chunks are kept."""
        article = MagicMock()
        article.slug = "ai"
        article.is_aggregate = False
        article.get_absolute_url.return_value = "/vision/2025/ai/"
        article.get_summary.return_value = ""
        article.content_tree = {
            "references": [
                {"code": "RefA", "text": "Source A"},
                {"code": "RefB", "text": "Source B"},
            ]
        }

        aggregated = {
            "ai": {
                "slug": "ai",
                "vision_year": 2025,
                "similarity_score": 0.8,
                "chunks": ["Text citing [RefA] but not RefB"],
                "references": [],
            }
        }

        with patch("hipeac_mcp.services.rags.vision.service.VisionArticle") as mock_cls:
            mock_cls.objects.filter.return_value.select_related.return_value.only.return_value = self._make_async_iter(
                [article]
            )
            await service._enrich_from_database(aggregated)

        assert len(aggregated["ai"]["references"]) == 1
        assert aggregated["ai"]["references"][0]["code"] == "RefA"

    @patch("hipeac_mcp.services.rags.vision.service.ensure_connection_async", new_callable=AsyncMock)
    async def test_skips_articles_not_in_aggregated(self, mock_conn, service):
        """Articles returned by the DB query whose slug is not in aggregated are silently skipped."""
        article = MagicMock()
        article.slug = "unrelated"

        aggregated = {
            "ai": {"slug": "ai", "vision_year": 2025, "similarity_score": 0.8, "chunks": [], "references": []}
        }

        with patch("hipeac_mcp.services.rags.vision.service.VisionArticle") as mock_cls:
            mock_cls.objects.filter.return_value.select_related.return_value.only.return_value = self._make_async_iter(
                [article]
            )
            await service._enrich_from_database(aggregated)

        assert "url" not in aggregated["ai"]

    @patch(
        "hipeac_mcp.services.rags.vision.service.ensure_connection_async",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db down"),
    )
    async def test_silently_ignores_db_errors(self, mock_conn, service):
        """DB errors during enrichment are caught — aggregated dict is left unchanged."""
        aggregated = {"ai": {"slug": "ai", "vision_year": 2025, "similarity_score": 0.8, "chunks": []}}

        await service._enrich_from_database(aggregated)

        assert aggregated["ai"]["similarity_score"] == 0.8
