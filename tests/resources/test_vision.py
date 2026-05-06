"""Tests for Vision MCP resource handlers."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hipeac_mcp.resources.vision import get_vision_article, get_vision_overview


def _make_article(
    title: str = "AI Trends",
    slug: str = "ai",
    content: str = "Body.",
    summary: str = "",
    is_draft: bool = False,
) -> MagicMock:
    """Build a mock VisionArticle for resource handler tests.

    :param title: Article title.
    :param slug: Article slug.
    :param content: Raw article content.
    :param summary: Precomputed summary (empty means fall back to ai_summary).
    :param is_draft: Whether the parent Vision edition is draft.
    :returns: MagicMock mimicking a VisionArticle instance.
    """
    article = MagicMock()
    article.title = title
    article.slug = slug
    article.content = content
    article.get_summary.return_value = summary
    article.section.vision.is_draft = is_draft
    return article


def _make_section(name: str = "Chapters") -> MagicMock:
    """Build a mock VisionSection for resource handler tests.

    :param name: Section name.
    :returns: MagicMock mimicking a VisionSection.
    """
    section = MagicMock()
    section.name = name
    section.vision.pk = 1
    section.vision.is_draft = False
    return section


class TestGetVisionArticleResource:
    """Tests for the get_vision_article resource handler."""

    @patch("hipeac_mcp.resources.vision.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.resources.vision.VisionArticle")
    async def test_returns_markdown_with_summary(self, mock_cls, mock_conn):
        """Returns a header with summary block when summary is present."""
        article = _make_article(summary="A concise summary.")
        mock_cls.objects.select_related.return_value.aget = AsyncMock(return_value=article)

        result = await get_vision_article(2025, "ai")

        assert "# AI Trends" in result
        assert "> A concise summary." in result
        assert "Body." in result

    @patch("hipeac_mcp.resources.vision.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.resources.vision.VisionArticle")
    async def test_returns_markdown_without_summary(self, mock_cls, mock_conn):
        """Returns a plain header when no summary is available."""
        article = _make_article(summary="")
        mock_cls.objects.select_related.return_value.aget = AsyncMock(return_value=article)

        result = await get_vision_article(2025, "ai")

        assert "# AI Trends" in result
        assert ">" not in result
        assert "Body." in result

    @patch("hipeac_mcp.resources.vision.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.resources.vision.VisionArticle")
    async def test_includes_draft_notice_when_edition_is_draft(self, mock_cls, mock_conn):
        """Draft Vision articles include an explicit notice in the markdown header."""
        article = _make_article(summary="A concise summary.", is_draft=True)
        mock_cls.objects.select_related.return_value.aget = AsyncMock(return_value=article)

        result = await get_vision_article(2027, "ai")

        assert "Draft Vision content" in result
        assert "may change" in result

    @patch("hipeac_mcp.resources.vision.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.resources.vision.VisionArticle")
    async def test_raises_value_error_when_not_found(self, mock_cls, mock_conn):
        """Raises ValueError when the article does not exist."""
        from hipeac_mcp.models.vision import VisionArticle as RealVisionArticle

        mock_cls.objects.select_related.return_value.aget = AsyncMock(side_effect=RealVisionArticle.DoesNotExist)
        mock_cls.DoesNotExist = RealVisionArticle.DoesNotExist

        with pytest.raises(ValueError, match="not found"):
            await get_vision_article(2025, "missing-slug")


class TestGetVisionOverviewResource:
    """Tests for the get_vision_overview resource handler."""

    @staticmethod
    def _make_async_iter(items):
        """Return an object whose __aiter__ yields items.

        :param items: Items to iterate.
        :returns: MagicMock with async iteration support.
        """

        async def _gen(self):
            for item in items:
                yield item

        mock_qs = MagicMock()
        mock_qs.__aiter__ = _gen
        return mock_qs

    @patch("hipeac_mcp.resources.vision.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.resources.vision.get_content_type_id", return_value=7)
    @patch("hipeac_mcp.resources.vision.VisionFile")
    @patch("hipeac_mcp.resources.vision.VisionSection")
    async def test_returns_json_with_toc(self, mock_section_cls, mock_file_cls, mock_ct_id, mock_conn):
        """Returns JSON containing year, title, and sections table of contents."""
        section = _make_section("Chapters")

        article1 = MagicMock()
        article1.title = "New Hardware"
        article1.slug = "new-hardware"
        article1.get_summary.return_value = "About hardware."

        section.articles.order_by.return_value.all.return_value = self._make_async_iter([article1])

        qs = mock_section_cls.objects.select_related.return_value.prefetch_related.return_value
        qs.filter.return_value.order_by.return_value = self._make_async_iter([section])
        mock_file_cls.objects.filter.return_value = self._make_async_iter([])

        result = await get_vision_overview(2025)

        data = json.loads(result)
        assert data["year"] == 2025
        assert data["title"] == "HiPEAC Vision 2025"
        assert len(data["sections"]) == 1
        assert data["sections"][0]["section"] == "Chapters"
        assert data["sections"][0]["articles"][0]["slug"] == "new-hardware"

    @patch("hipeac_mcp.resources.vision.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.resources.vision.VisionSection")
    async def test_raises_value_error_when_no_sections(self, mock_section_cls, mock_conn):
        """Raises ValueError when no Vision document exists for the given year."""
        qs = mock_section_cls.objects.select_related.return_value.prefetch_related.return_value
        qs.filter.return_value.order_by.return_value = self._make_async_iter([])

        with pytest.raises(ValueError, match="No Vision document found"):
            await get_vision_overview(1999)

    @patch("hipeac_mcp.resources.vision.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.resources.vision.get_content_type_id", return_value=7)
    @patch("hipeac_mcp.resources.vision.VisionFile")
    @patch("hipeac_mcp.resources.vision.VisionSection")
    async def test_includes_file_urls(self, mock_section_cls, mock_file_cls, mock_ct_id, mock_conn):
        """PDF and EPUB download URLs are included in the overview when files exist."""
        section = _make_section()
        section.articles.order_by.return_value.all.return_value = self._make_async_iter([])
        qs = mock_section_cls.objects.select_related.return_value.prefetch_related.return_value
        qs.filter.return_value.order_by.return_value = self._make_async_iter([section])

        pdf_file = MagicMock()
        pdf_file.file_type = "pdf"
        pdf_file.absolute_url = "https://www.hipeac.net/media/public/doc.pdf"

        mock_file_cls.objects.filter.return_value = self._make_async_iter([pdf_file])

        result = await get_vision_overview(2025)

        data = json.loads(result)
        assert data["pdf_url"] == "https://www.hipeac.net/media/public/doc.pdf"
        assert data["epub_url"] is None
