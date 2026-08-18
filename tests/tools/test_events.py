"""Tests for the event MCP tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hipeac_mcp.schemas.events import EventActivityResult, EventListResponse, EventSearchResponse
from hipeac_mcp.tools.events import _get_service, _service_cache, get_events, search_event


@pytest.fixture(autouse=True)
def clear_service_cache():
    """Clear the event service cache between tests."""
    _service_cache.clear()
    yield
    _service_cache.clear()


def _make_event(event_id, name, event_type, city="Kraków", country="PL", year=2026, is_virtual=False):
    """Build a mock Event model instance.

    :param event_id: Primary key.
    :param name: Event name.
    :param event_type: 'conference' or 'acaces'.
    :param city: Host city.
    :param country: ISO country code.
    :param year: Year for start/end dates.
    :param is_virtual: Whether the event is virtual.
    :returns: MagicMock mimicking an Event instance.
    """
    from datetime import date

    event = MagicMock()
    event.id = event_id
    event.name = name
    event.type = event_type
    event.is_virtual = is_virtual
    event.city = city
    event.country = country
    event.start_date = date(year, 1, 20)
    event.end_date = date(year, 1, 22)
    event.get_absolute_url.return_value = f"/{year}/{city.lower()}/"
    return event


def _make_search_response(query="test", n=1):
    """Build a minimal EventSearchResponse.

    :param query: Query string.
    :param n: Number of results.
    :returns: An EventSearchResponse with n results.
    """
    results = [
        EventActivityResult(
            activity_id=i,
            title=f"Activity {i}",
            activity_type="Workshop",
            similarity_score=0.9 - i * 0.1,
            content_preview=f"Preview {i}",
            event_name="HiPEAC 2026",
            event_id=100,
            event_year=2026,
            url=f"https://www.hipeac.net/2026/krakow/#/workshop/{i}/",
        )
        for i in range(n)
    ]
    return EventSearchResponse(
        query=query, event_name="HiPEAC 2026", event_id=100, total_results=len(results), results=results
    )


def _make_async_iterator(items):
    """Create an async iterable from a list of items.

    :param items: Items to iterate.
    :returns: MagicMock with __aiter__.
    """

    async def _iter(self):
        for item in items:
            yield item

    mock_qs = MagicMock()
    mock_qs.__aiter__ = _iter
    return mock_qs


class TestGetServiceCache:
    """Tests for the _get_service cache helper."""

    @patch("hipeac_mcp.tools.events.EventRagService")
    def test_creates_and_caches_service(self, mock_cls):
        """Service is created once and cached for subsequent calls."""
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance

        first = _get_service(100)
        second = _get_service(100)

        assert first is second
        mock_cls.assert_called_once_with(event_id=100)

    @patch("hipeac_mcp.tools.events.EventRagService")
    def test_different_ids_get_different_services(self, mock_cls):
        """Different event IDs produce separate cached services."""
        _get_service(100)
        _get_service(200)

        assert mock_cls.call_count == 2


class TestGetEvents:
    """Tests for the get_events MCP tool."""

    @patch("hipeac_mcp.tools.events.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.events.Event")
    async def test_returns_event_list(self, mock_event_cls, mock_conn):
        """get_events returns a structured EventListResponse."""
        event1 = _make_event(100, "HiPEAC 2026", "conference")
        event2 = _make_event(200, "ACACES 2025", "acaces", city="Fiuggi", country="IT", year=2025)

        mock_qs = _make_async_iterator([event1, event2])
        mock_event_cls.objects.filter.return_value.order_by.return_value.__getitem__ = lambda s, k: mock_qs
        mock_event_cls.CONFERENCE = "conference"
        mock_event_cls.ACACES = "acaces"

        result = await get_events.__wrapped__()

        assert isinstance(result, EventListResponse)
        assert result.total == 2
        assert result.events[0].name == "HiPEAC 2026"
        assert result.events[1].name == "ACACES 2025"

    @patch("hipeac_mcp.tools.events.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.events.Event")
    async def test_event_url_format(self, mock_event_cls, mock_conn):
        """Event URLs are prefixed with the HiPEAC base URL."""
        event = _make_event(100, "HiPEAC 2026", "conference")

        mock_qs = _make_async_iterator([event])
        mock_event_cls.objects.filter.return_value.order_by.return_value.__getitem__ = lambda s, k: mock_qs
        mock_event_cls.CONFERENCE = "conference"
        mock_event_cls.ACACES = "acaces"

        result = await get_events.__wrapped__()

        assert result.events[0].url == "https://www.hipeac.net/2026/kraków/"

    @patch("hipeac_mcp.tools.events.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.events.Event")
    async def test_empty_events(self, mock_event_cls, mock_conn):
        """No events returns an empty list with total=0."""
        mock_qs = _make_async_iterator([])
        mock_event_cls.objects.filter.return_value.order_by.return_value.__getitem__ = lambda s, k: mock_qs
        mock_event_cls.CONFERENCE = "conference"
        mock_event_cls.ACACES = "acaces"

        result = await get_events.__wrapped__()

        assert result.total == 0
        assert result.events == []

    @patch("hipeac_mcp.tools.events.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.events.Event")
    async def test_event_type_filter_narrows_query(self, mock_event_cls, mock_conn):
        """Passing event_type queries only that type instead of conference+acaces."""
        mock_qs = _make_async_iterator([])
        mock_event_cls.objects.filter.return_value.order_by.return_value.__getitem__ = lambda s, k: mock_qs
        mock_event_cls.CONFERENCE = "conference"
        mock_event_cls.ACACES = "acaces"

        await get_events.__wrapped__(event_type="acaces")

        mock_event_cls.objects.filter.assert_called_once_with(type__in=["acaces"])

    @patch("hipeac_mcp.tools.events.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.events.Event")
    async def test_year_filter_applied(self, mock_event_cls, mock_conn):
        """Passing year chains an additional start_date__year filter."""
        mock_qs = _make_async_iterator([])
        year_filtered = MagicMock()
        year_filtered.order_by.return_value.__getitem__ = lambda s, k: mock_qs
        mock_event_cls.objects.filter.return_value.filter.return_value = year_filtered
        mock_event_cls.CONFERENCE = "conference"
        mock_event_cls.ACACES = "acaces"

        await get_events.__wrapped__(year=2025)

        mock_event_cls.objects.filter.return_value.filter.assert_called_once_with(start_date__year=2025)

    @patch("hipeac_mcp.tools.events.ensure_connection_async", new_callable=AsyncMock)
    @patch("hipeac_mcp.tools.events.Event")
    async def test_limit_capped_at_50(self, mock_event_cls, mock_conn):
        """limit is capped at 50 even if a larger value is requested."""
        captured_slice = {}

        def capture_slice(self, k):
            captured_slice["slice"] = k
            return _make_async_iterator([])

        mock_event_cls.objects.filter.return_value.order_by.return_value.__getitem__ = capture_slice
        mock_event_cls.CONFERENCE = "conference"
        mock_event_cls.ACACES = "acaces"

        await get_events.__wrapped__(limit=200)

        assert captured_slice["slice"].stop == 50


class TestSearchEvent:
    """Tests for the search_event MCP tool."""

    @patch("hipeac_mcp.tools.events._get_service")
    async def test_explicit_event_id(self, mock_get_svc):
        """Explicit event_id is used directly."""
        mock_service = AsyncMock()
        mock_service.search_activities.return_value = _make_search_response("RISC-V")
        mock_get_svc.return_value = mock_service

        result = await search_event.__wrapped__("RISC-V", event_id=100)

        mock_get_svc.assert_called_once_with(100)
        assert result.total_results == 1

    @patch("hipeac_mcp.tools.events._get_service")
    @patch("hipeac_mcp.tools.events.sync_to_async")
    @patch("hipeac_mcp.tools.events.ensure_connection_async", new_callable=AsyncMock)
    async def test_defaults_to_latest_conference(self, mock_conn, mock_s2a, mock_get_svc):
        """When no event_id is provided, defaults to the latest conference."""
        latest_event = MagicMock()
        latest_event.id = 100

        mock_s2a.return_value = AsyncMock(return_value=latest_event)

        mock_service = AsyncMock()
        mock_service.search_activities.return_value = _make_search_response("test")
        mock_get_svc.return_value = mock_service

        result = await search_event.__wrapped__("test")

        mock_get_svc.assert_called_once_with(100)
        assert result.total_results == 1

    @patch("hipeac_mcp.tools.events._get_service")
    @patch("hipeac_mcp.tools.events.sync_to_async")
    @patch("hipeac_mcp.tools.events.ensure_connection_async", new_callable=AsyncMock)
    async def test_no_conference_returns_empty(self, mock_conn, mock_s2a, mock_get_svc):
        """When no conference exists, returns an empty response."""
        mock_s2a.return_value = AsyncMock(return_value=None)

        result = await search_event.__wrapped__("test")

        mock_get_svc.assert_not_called()
        assert result.total_results == 0
        assert result.event_id == 0

    @patch("hipeac_mcp.tools.events._get_service")
    async def test_limit_forwarded(self, mock_get_svc):
        """Limit parameter is forwarded to service.search_activities."""
        mock_service = AsyncMock()
        mock_service.search_activities.return_value = _make_search_response()
        mock_get_svc.return_value = mock_service

        await search_event.__wrapped__("test", event_id=100, limit=8)

        mock_service.search_activities.assert_called_once_with(["test"], limit=8)

    @patch("hipeac_mcp.tools.events._get_service")
    @patch("hipeac_mcp.tools.events.sync_to_async")
    @patch("hipeac_mcp.tools.events.ensure_connection_async", new_callable=AsyncMock)
    async def test_database_error_propagates(self, mock_conn, mock_s2a, mock_get_svc):
        """Database errors during latest conference lookup propagate rather than being swallowed.

        Regression: a bare `except Exception` used to turn any DB failure into a
        silent empty response, indistinguishable from "no conference exists yet".
        Real failures must surface so they're visible (logs, Sentry) instead of
        misleading the caller into thinking there's simply no data.
        """
        mock_s2a.return_value = AsyncMock(side_effect=Exception("DB error"))

        with pytest.raises(Exception, match="DB error"):
            await search_event.__wrapped__("test")
