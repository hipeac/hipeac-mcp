"""Tests for the Huey background tasks."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from hipeac_mcp.tasks import _reindex_year, check_reindex_signals


class TestCheckReindexSignals:
    """Tests for the check_reindex_signals periodic task."""

    @patch("hipeac_mcp.tasks.get_redis_client")
    def test_returns_empty_when_no_signals(self, mock_get_client):
        """Verify no reindexing happens when Redis queue is empty."""
        mock_client = MagicMock()
        mock_client.lpop.return_value = None
        mock_get_client.return_value = mock_client

        result = check_reindex_signals.call_local()

        assert result == {"reindexed": [], "failed": []}

    @patch("hipeac_mcp.tasks.asyncio")
    @patch("hipeac_mcp.tasks.get_redis_client")
    def test_deduplicates_year_signals(self, mock_get_client, mock_asyncio):
        """Verify multiple signals for the same year trigger only one reindex."""
        mock_client = MagicMock()
        mock_client.lpop.side_effect = [
            json.dumps({"year": 2025}),
            json.dumps({"year": 2025}),
            json.dumps({"year": 2025}),
            None,
        ]
        mock_get_client.return_value = mock_client

        result = check_reindex_signals.call_local()

        assert mock_asyncio.run.call_count == 1
        assert result == {"reindexed": [2025], "failed": []}

    @patch("hipeac_mcp.tasks.asyncio")
    @patch("hipeac_mcp.tasks.get_redis_client")
    def test_processes_multiple_years(self, mock_get_client, mock_asyncio):
        """Verify signals for different years trigger separate reindexes."""
        mock_client = MagicMock()
        mock_client.lpop.side_effect = [
            json.dumps({"year": 2024}),
            json.dumps({"year": 2025}),
            None,
        ]
        mock_get_client.return_value = mock_client

        result = check_reindex_signals.call_local()

        assert mock_asyncio.run.call_count == 2
        assert result == {"reindexed": [2024, 2025], "failed": []}

    @patch("hipeac_mcp.tasks.asyncio")
    @patch("hipeac_mcp.tasks.get_redis_client")
    def test_skips_invalid_signals(self, mock_get_client, mock_asyncio):
        """Verify malformed signals are skipped without crashing."""
        mock_client = MagicMock()
        mock_client.lpop.side_effect = [
            "not-json",
            json.dumps({"year": 2025}),
            None,
        ]
        mock_get_client.return_value = mock_client

        result = check_reindex_signals.call_local()

        assert mock_asyncio.run.call_count == 1
        assert result == {"reindexed": [2025], "failed": []}

    @patch("hipeac_mcp.tasks.asyncio")
    @patch("hipeac_mcp.tasks.get_redis_client")
    def test_reports_failed_reindex(self, mock_get_client, mock_asyncio):
        """Verify failed reindexes are reported in the result."""
        mock_client = MagicMock()
        mock_client.lpop.side_effect = [
            json.dumps({"year": 2025}),
            None,
        ]
        mock_get_client.return_value = mock_client
        mock_asyncio.run.side_effect = RuntimeError("Embedding service down")

        result = check_reindex_signals.call_local()

        assert result == {"reindexed": [], "failed": [2025]}

    @patch("hipeac_mcp.tasks.get_redis_client")
    def test_handles_redis_unavailable(self, mock_get_client):
        """Verify graceful handling when Redis is unavailable."""
        mock_get_client.return_value = None

        result = check_reindex_signals.call_local()

        assert result == {"reindexed": [], "failed": []}


class TestReindexYear:
    """Tests for the _reindex_year async helper."""

    @patch("hipeac_mcp.tasks.VisionRagService")
    @patch("hipeac_mcp.tasks.VisionArticle")
    @patch("hipeac_mcp.tasks.ensure_connection_async")
    async def test_resets_and_reindexes(self, mock_ensure, mock_article_cls, mock_service_cls):
        """Verify the index is reset and articles are reindexed."""
        mock_service = MagicMock()
        mock_service.index_article = AsyncMock()
        mock_service_cls.return_value = mock_service

        mock_article = MagicMock()
        mock_article.slug = "test-article"

        mock_qs = MagicMock()
        mock_qs.select_related.return_value = mock_qs
        mock_qs.count = MagicMock(return_value=1)

        async def async_iter(*_args, **_kwargs):
            yield mock_article

        mock_qs.__aiter__ = async_iter
        mock_article_cls.objects.filter.return_value = mock_qs

        with patch("hipeac_mcp.tasks.sync_to_async", return_value=AsyncMock(return_value=1)):
            await _reindex_year(2025)

        mock_service.reset_index.assert_called_once()
        mock_service.index_article.assert_awaited_once_with(mock_article)
