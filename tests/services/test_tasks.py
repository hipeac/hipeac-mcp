"""Tests for the Huey background tasks."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from hipeac_mcp.tasks import (
    _drain_redis_list,
    _reindex_event,
    _reindex_vision_year,
    check_reindex_signals,
)


class TestDrainRedisList:
    """Tests for the _drain_redis_list helper."""

    @patch("hipeac_mcp.tasks.get_redis_client")
    def test_returns_empty_when_redis_unavailable(self, mock_get_client):
        """Returns empty set when Redis is not available."""
        mock_get_client.return_value = None
        assert _drain_redis_list("any:key") == set()

    @patch("hipeac_mcp.tasks.get_redis_client")
    def test_drains_year_signals(self, mock_get_client):
        """Drains year-based signals correctly."""
        mock_client = MagicMock()
        mock_client.lpop.side_effect = [
            json.dumps({"year": 2025}),
            json.dumps({"year": 2024}),
            None,
        ]
        mock_get_client.return_value = mock_client

        result = _drain_redis_list("hipeac:mcp:reindex:vision")
        assert result == {2024, 2025}

    @patch("hipeac_mcp.tasks.get_redis_client")
    def test_drains_event_id_signals(self, mock_get_client):
        """Drains event_id-based signals correctly."""
        mock_client = MagicMock()
        mock_client.lpop.side_effect = [
            json.dumps({"event_id": 100}),
            json.dumps({"event_id": 200}),
            None,
        ]
        mock_get_client.return_value = mock_client

        result = _drain_redis_list("hipeac:mcp:reindex:event")
        assert result == {100, 200}

    @patch("hipeac_mcp.tasks.get_redis_client")
    def test_deduplicates_signals(self, mock_get_client):
        """Duplicate signals are deduplicated."""
        mock_client = MagicMock()
        mock_client.lpop.side_effect = [
            json.dumps({"year": 2025}),
            json.dumps({"year": 2025}),
            json.dumps({"year": 2025}),
            None,
        ]
        mock_get_client.return_value = mock_client

        result = _drain_redis_list("hipeac:mcp:reindex:vision")
        assert result == {2025}

    @patch("hipeac_mcp.tasks.get_redis_client")
    def test_skips_invalid_json(self, mock_get_client):
        """Malformed JSON signals are skipped."""
        mock_client = MagicMock()
        mock_client.lpop.side_effect = [
            "not-json",
            json.dumps({"year": 2025}),
            None,
        ]
        mock_get_client.return_value = mock_client

        result = _drain_redis_list("hipeac:mcp:reindex:vision")
        assert result == {2025}


class TestCheckReindexSignals:
    """Tests for the check_reindex_signals periodic task."""

    @patch("hipeac_mcp.tasks._drain_redis_list")
    def test_returns_empty_when_no_signals(self, mock_drain):
        """No reindexing happens when both Redis queues are empty."""
        mock_drain.return_value = set()

        result = check_reindex_signals.call_local()

        assert result == {"reindexed": [], "failed": []}

    @patch("hipeac_mcp.tasks._reindex_vision_year", new_callable=MagicMock)
    @patch("hipeac_mcp.tasks._drain_redis_list")
    @patch("hipeac_mcp.tasks.asyncio")
    def test_processes_vision_signals(self, mock_asyncio, mock_drain, mock_reindex):
        """Vision year signals trigger reindexing."""
        mock_drain.side_effect = [{2024, 2025}, set()]

        result = check_reindex_signals.call_local()

        assert mock_asyncio.run.call_count == 2
        assert result == {"reindexed": [2024, 2025], "failed": []}

    @patch("hipeac_mcp.tasks._reindex_event", new_callable=MagicMock)
    @patch("hipeac_mcp.tasks._drain_redis_list")
    @patch("hipeac_mcp.tasks.asyncio")
    def test_processes_event_signals(self, mock_asyncio, mock_drain, mock_reindex):
        """Event ID signals trigger reindexing."""
        mock_drain.side_effect = [set(), {100}]

        result = check_reindex_signals.call_local()

        assert mock_asyncio.run.call_count == 1
        assert 100 in result["reindexed"]

    @patch("hipeac_mcp.tasks._reindex_event", new_callable=MagicMock)
    @patch("hipeac_mcp.tasks._reindex_vision_year", new_callable=MagicMock)
    @patch("hipeac_mcp.tasks._drain_redis_list")
    @patch("hipeac_mcp.tasks.asyncio")
    def test_processes_both_vision_and_event(self, mock_asyncio, mock_drain, mock_reindex_v, mock_reindex_e):
        """Vision and event signals in the same cycle are both processed."""
        mock_drain.side_effect = [{2025}, {100}]

        result = check_reindex_signals.call_local()

        assert mock_asyncio.run.call_count == 2
        assert result == {"reindexed": [2025, 100], "failed": []}

    @patch("hipeac_mcp.tasks._reindex_vision_year", new_callable=MagicMock)
    @patch("hipeac_mcp.tasks._drain_redis_list")
    @patch("hipeac_mcp.tasks.asyncio")
    def test_reports_failed_reindex(self, mock_asyncio, mock_drain, mock_reindex):
        """Failed reindexes are reported in the result."""
        mock_drain.side_effect = [{2025}, set()]
        mock_asyncio.run.side_effect = RuntimeError("Embedding service down")

        result = check_reindex_signals.call_local()

        assert result == {"reindexed": [], "failed": [2025]}


class TestReindexVisionYear:
    """Tests for the _reindex_vision_year async helper."""

    @patch("hipeac_mcp.tasks.VisionRagService")
    @patch("hipeac_mcp.tasks.VisionArticle")
    @patch("hipeac_mcp.tasks.ensure_connection_async")
    async def test_resets_and_reindexes(self, mock_ensure, mock_article_cls, mock_service_cls):
        """The index is reset and articles are reindexed."""
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
            await _reindex_vision_year(2025)

        mock_service.reset_index.assert_called_once()
        mock_service.index_article.assert_awaited_once_with(mock_article)


class TestReindexEvent:
    """Tests for the _reindex_event async helper."""

    @patch("hipeac_mcp.tasks.EventRagService")
    @patch("hipeac_mcp.tasks.Event")
    @patch("hipeac_mcp.tasks.ensure_connection_async")
    async def test_resets_and_reindexes(self, mock_ensure, mock_event_cls, mock_service_cls):
        """The index is reset and event is reindexed."""
        mock_event = MagicMock()
        mock_event.id = 100
        mock_event.name = "HiPEAC 2026"

        mock_service = MagicMock()
        mock_service.index_event = AsyncMock(return_value=True)
        mock_service_cls.return_value = mock_service

        with patch("hipeac_mcp.tasks.sync_to_async", return_value=AsyncMock(return_value=mock_event)):
            await _reindex_event(100)

        mock_service.reset_index.assert_called_once()
        mock_service.index_event.assert_awaited_once_with(mock_event)

    @patch("hipeac_mcp.tasks.EventRagService")
    @patch("hipeac_mcp.tasks.Event")
    @patch("hipeac_mcp.tasks.ensure_connection_async")
    async def test_raises_on_failure(self, mock_ensure, mock_event_cls, mock_service_cls):
        """RuntimeError is raised if index_event returns False."""
        import pytest

        mock_event = MagicMock()
        mock_event.id = 100
        mock_event.name = "HiPEAC 2026"

        mock_service = MagicMock()
        mock_service.index_event = AsyncMock(return_value=False)
        mock_service_cls.return_value = mock_service

        with patch("hipeac_mcp.tasks.sync_to_async", return_value=AsyncMock(return_value=mock_event)):
            with pytest.raises(RuntimeError, match="reindex failed"):
                await _reindex_event(100)
