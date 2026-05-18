"""Tests for the Vision search tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hipeac_mcp.schemas.vision import VisionArticleResult, VisionSearchResponse
from hipeac_mcp.tools.vision import (
    _get_latest_published_year,
    _get_service,
    _service_cache,
    get_vision_article,
    get_vision_overview,
    search_vision,
)


@pytest.fixture(autouse=True)
def clear_service_cache():
    """Clear the vision service cache between tests."""
    _service_cache.clear()
    yield
    _service_cache.clear()


def _make_response(query: str = "test", n: int = 1) -> VisionSearchResponse:
    """Build a minimal VisionSearchResponse for testing.

    :param query: Query string for the response.
    :param n: Number of articles to include.
    :returns: A VisionSearchResponse with n articles.
    """
    articles = [
        VisionArticleResult(
            slug=f"article-{i}",
            title=f"Article {i}",
            section="Chapters",
            summary=f"Summary {i}",
            vision_year=2025,
            is_draft=False,
            similarity_score=0.9 - i * 0.1,
            content_preview=f"Preview {i}",
            references=[],
            resource_uri=f"hipeac://vision/2025/article-{i}",
            url=f"https://hipeac.net/vision/2025/article-{i}/",
        )
        for i in range(n)
    ]
    return VisionSearchResponse(query=query, total_results=len(articles), articles=articles)


class TestGetService:
    """Tests for the _get_service cache helper."""

    @patch("hipeac_mcp.tools.vision.VisionRagService")
    def test_creates_and_caches_service(self, mock_cls):
        """Service is created once and cached for subsequent calls."""
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        first = _get_service(2025)
        second = _get_service(2025)

        assert first is second
        mock_cls.assert_called_once_with(year=2025)

    @patch("hipeac_mcp.tools.vision.VisionRagService")
    def test_different_years_get_different_services(self, mock_cls):
        """Different years produce separate cached services."""
        _get_service(2024)
        _get_service(2025)

        assert mock_cls.call_count == 2


class TestGetLatestPublishedYear:
    """Tests for latest published Vision year resolution."""

    @patch("hipeac_mcp.tools.vision.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.vision.Vision")
    async def test_returns_latest_published_year(self, mock_vision, mock_conn):
        """The helper returns the most recent non-draft Vision year."""
        latest = MagicMock(year=2025)
        mock_vision.objects.filter.return_value.order_by.return_value.only.return_value.afirst = AsyncMock(
            return_value=latest
        )

        result = await _get_latest_published_year()

        assert result == 2025
        mock_vision.objects.filter.assert_called_once_with(status=mock_vision.PUBLISHED)

    @patch("hipeac_mcp.tools.vision.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.vision.Vision")
    async def test_raises_when_no_published_edition_exists(self, mock_vision, mock_conn):
        """The helper raises a clear error when no published Vision exists."""
        mock_vision.objects.filter.return_value.order_by.return_value.only.return_value.afirst = AsyncMock(
            return_value=None
        )

        with pytest.raises(ValueError, match="No published Vision edition found"):
            await _get_latest_published_year()


class TestSearchVision:
    """Tests for the search_vision MCP tool."""

    @patch("hipeac_mcp.tools.vision._get_latest_published_year", new_callable=AsyncMock, return_value=2025)
    @patch("hipeac_mcp.tools.vision._get_service")
    async def test_single_year_default(self, mock_get_svc, mock_latest_year):
        """Default search resolves the latest published year and searches only that edition."""
        mock_service = AsyncMock()
        mock_service.search_articles.return_value = _make_response("quantum")
        mock_get_svc.return_value = mock_service

        result = await search_vision.__wrapped__("quantum computing")

        mock_latest_year.assert_awaited_once()
        mock_get_svc.assert_called_once_with(2025)
        assert result.total_results <= 4

    @patch("hipeac_mcp.tools.vision._get_service")
    async def test_single_year_explicit(self, mock_get_svc):
        """Explicit year parameter is forwarded."""
        mock_service = AsyncMock()
        mock_service.search_articles.return_value = _make_response()
        mock_get_svc.return_value = mock_service

        await search_vision.__wrapped__("query", year=2024)

        mock_get_svc.assert_called_once_with(2024)

    @patch("hipeac_mcp.tools.vision._get_service")
    async def test_multi_year_search(self, mock_get_svc):
        """Years parameter searches multiple years and merges results."""
        mock_service = AsyncMock()
        mock_service.search_articles.return_value = _make_response("query", n=2)
        mock_get_svc.return_value = mock_service

        await search_vision.__wrapped__("query", years=[2024, 2025])

        assert mock_get_svc.call_count == 2

    @patch("hipeac_mcp.tools.vision._get_service")
    async def test_multi_year_results_sorted_by_score(self, mock_get_svc):
        """Multi-year results are sorted by similarity_score descending."""
        response_2024 = VisionSearchResponse(
            query="q",
            total_results=1,
            articles=[
                VisionArticleResult(
                    slug="old",
                    title="Old",
                    section="S",
                    summary="",
                    vision_year=2024,
                    is_draft=False,
                    similarity_score=0.5,
                    content_preview="",
                    references=[],
                    resource_uri="hipeac://vision/2024/old",
                    url="https://hipeac.net/vision/2024/old/",
                )
            ],
        )
        response_2025 = VisionSearchResponse(
            query="q",
            total_results=1,
            articles=[
                VisionArticleResult(
                    slug="new",
                    title="New",
                    section="S",
                    summary="",
                    vision_year=2025,
                    is_draft=False,
                    similarity_score=0.9,
                    content_preview="",
                    references=[],
                    resource_uri="hipeac://vision/2025/new",
                    url="https://hipeac.net/vision/2025/new/",
                )
            ],
        )

        mock_svc_2024 = AsyncMock()
        mock_svc_2024.search_articles.return_value = response_2024
        mock_svc_2025 = AsyncMock()
        mock_svc_2025.search_articles.return_value = response_2025
        mock_get_svc.side_effect = lambda y: mock_svc_2024 if y == 2024 else mock_svc_2025

        result = await search_vision.__wrapped__("q", years=[2024, 2025])

        assert result.articles[0].slug == "new"
        assert result.articles[0].similarity_score > result.articles[1].similarity_score


class TestGetVisionArticleTool:
    """Tests for the get_vision_article tool wrapper."""

    @patch("hipeac_mcp.tools.vision._get_article")
    async def test_delegates_to_resource_handler(self, mock_get_article):
        """get_vision_article passes year and slug through to the resource handler."""
        mock_get_article.return_value = "# AI Trends\nBody text."

        result = await get_vision_article.__wrapped__("ai-trends", year=2025)

        mock_get_article.assert_called_once_with(year=2025, slug="ai-trends")
        assert result == "# AI Trends\nBody text."

    @patch("hipeac_mcp.tools.vision._get_latest_published_year", new_callable=AsyncMock, return_value=2025)
    @patch("hipeac_mcp.tools.vision._get_article")
    async def test_resolves_latest_published_year_when_omitted(self, mock_get_article, mock_latest_year):
        """When year is omitted, the wrapper resolves the latest published Vision year."""
        mock_get_article.return_value = "# AI Trends\nBody text."

        result = await get_vision_article.__wrapped__("ai-trends")

        mock_latest_year.assert_awaited_once()
        mock_get_article.assert_called_once_with(year=2025, slug="ai-trends")
        assert result == "# AI Trends\nBody text."


class TestGetVisionOverviewTool:
    """Tests for the get_vision_overview tool wrapper."""

    @patch("hipeac_mcp.tools.vision._get_overview")
    async def test_delegates_to_resource_handler(self, mock_get_overview):
        """get_vision_overview passes year through to the resource handler."""
        mock_get_overview.return_value = '{"year": 2025}'

        result = await get_vision_overview.__wrapped__(year=2025)

        mock_get_overview.assert_called_once_with(year=2025)
        assert result == '{"year": 2025}'

    @patch("hipeac_mcp.tools.vision._get_latest_published_year", new_callable=AsyncMock, return_value=2025)
    @patch("hipeac_mcp.tools.vision._get_overview")
    async def test_resolves_latest_published_year_when_omitted(self, mock_get_overview, mock_latest_year):
        """When year is omitted, the wrapper resolves the latest published Vision year."""
        mock_get_overview.return_value = '{"year": 2025}'

        result = await get_vision_overview.__wrapped__()

        mock_latest_year.assert_awaited_once()
        mock_get_overview.assert_called_once_with(year=2025)
        assert result == '{"year": 2025}'
