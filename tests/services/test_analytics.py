"""Tests for the analytics service."""

import json
from enum import Enum
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp import Context

from hipeac_mcp.services.analytics import REDIS_KEY, _build_params, _extract_client_info, _serialize_param, track_usage


class Color(Enum):
    RED = "red"
    BLUE = "blue"


class TestSerializeParam:
    """Tests for _serialize_param helper."""

    def test_serializes_enum_to_value(self):
        """Verify enum values are extracted."""
        assert _serialize_param(Color.RED) == "red"

    def test_serializes_list_of_enums(self):
        """Verify lists of enums are recursively serialized."""
        assert _serialize_param([Color.RED, Color.BLUE]) == ["red", "blue"]

    def test_passes_through_plain_values(self):
        """Verify strings, ints, etc. are returned as-is."""
        assert _serialize_param("hello") == "hello"
        assert _serialize_param(42) == 42
        assert _serialize_param(None) is None


class TestBuildParams:
    """Tests for _build_params helper."""

    def test_captures_non_default_args(self):
        """Verify only non-default arguments are included."""

        async def my_tool(query: str, limit: int = 20) -> None: ...

        params = _build_params(my_tool, (), {"query": "test"})
        assert params == {"query": "test"}

    def test_excludes_default_values(self):
        """Verify arguments matching their default are excluded."""

        async def my_tool(query: str | None = None, limit: int = 20) -> None: ...

        params = _build_params(my_tool, (), {"limit": 20})
        assert params == {}

    def test_captures_positional_args(self):
        """Verify positional arguments are captured correctly."""

        async def my_tool(query: str, limit: int = 20) -> None: ...

        params = _build_params(my_tool, ("test",), {})
        assert params == {"query": "test"}

    def test_serializes_enum_params(self):
        """Verify enum params are serialized to their values."""

        async def my_tool(colors: list[Color] | None = None) -> None: ...

        params = _build_params(my_tool, (), {"colors": [Color.RED, Color.BLUE]})
        assert params == {"colors": ["red", "blue"]}

    def test_excludes_context_params(self):
        """Verify Context-typed parameters are excluded from params."""

        async def my_tool(query: str, ctx: Context = None) -> None: ...

        mock_ctx = MagicMock(spec=Context)
        params = _build_params(my_tool, (), {"query": "test", "ctx": mock_ctx})
        assert params == {"query": "test"}
        assert "ctx" not in params


class TestExtractClientInfo:
    """Tests for _extract_client_info helper."""

    def test_extracts_client_info_from_context(self):
        """Verify client name and version are extracted from Context."""

        async def my_tool(query: str, ctx: Context = None) -> None: ...

        mock_ctx = MagicMock(spec=Context)
        mock_ctx.client_id = "abc-123"
        mock_ctx.request_context.session.client_params.clientInfo.name = "claude-desktop"
        mock_ctx.request_context.session.client_params.clientInfo.version = "1.2.0"

        result = _extract_client_info(my_tool, (), {"query": "test", "ctx": mock_ctx})
        assert result == {"client": "claude-desktop/1.2.0", "client_id": "abc-123"}

    def test_returns_none_without_context(self):
        """Verify None values are returned when no Context parameter exists."""

        async def my_tool(query: str) -> None: ...

        result = _extract_client_info(my_tool, (), {"query": "test"})
        assert result == {"client": None, "client_id": None}

    def test_returns_none_when_client_info_missing(self):
        """Verify graceful handling when session has no client_info."""

        async def my_tool(ctx: Context = None) -> None: ...

        mock_ctx = MagicMock(spec=Context)
        mock_ctx.client_id = None
        mock_ctx.request_context.session.client_params = None

        result = _extract_client_info(my_tool, (), {"ctx": mock_ctx})
        assert result == {"client": None, "client_id": None}


class TestTrackUsage:
    """Tests for the track_usage decorator."""

    @patch("hipeac_mcp.services.analytics._push_event")
    async def test_logs_tool_name_and_params(self, mock_push):
        """Verify the decorator pushes events with function name and params."""

        @track_usage
        async def search_members(query: str, limit: int = 20) -> str:
            return "result"

        result = await search_members(query="AI")

        assert result == "result"
        mock_push.assert_called_once_with("search_members", {"query": "AI"}, client=None, client_id=None)

    @patch("hipeac_mcp.services.analytics._push_event")
    async def test_logs_empty_params_when_all_defaults(self, mock_push):
        """Verify the decorator pushes empty params for tools with no args."""

        @track_usage
        async def get_metadata() -> str:
            return "metadata"

        await get_metadata()

        mock_push.assert_called_once_with("get_metadata", {}, client=None, client_id=None)

    @patch("hipeac_mcp.services.analytics._push_event")
    async def test_logs_client_info_from_context(self, mock_push):
        """Verify the decorator extracts and passes client info from Context."""

        @track_usage
        async def search_vision(query: str, ctx: Context = None) -> str:
            return "result"

        mock_ctx = MagicMock(spec=Context)
        mock_ctx.client_id = "session-42"
        mock_ctx.request_context.session.client_params.clientInfo.name = "chatgpt"
        mock_ctx.request_context.session.client_params.clientInfo.version = "2025.1"

        await search_vision(query="AI", ctx=mock_ctx)

        mock_push.assert_called_once_with(
            "search_vision", {"query": "AI"}, client="chatgpt/2025.1", client_id="session-42"
        )


class TestPushEvent:
    """Tests for _push_event (Redis interaction)."""

    @patch("hipeac_mcp.services.analytics.get_redis_client")
    def test_pushes_event_to_redis(self, mock_get_client):
        """Verify events are pushed to the correct Redis key."""
        from hipeac_mcp.services.analytics import _push_event

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        _push_event("search_members", {"query": "test"})

        mock_client.rpush.assert_called_once()
        key, payload = mock_client.rpush.call_args[0]
        assert key == REDIS_KEY

        event = json.loads(payload)
        assert event["tool"] == "search_members"
        assert event["params"] == {"query": "test"}
        assert "timestamp" in event
        assert "client" not in event

    @patch("hipeac_mcp.services.analytics.get_redis_client")
    def test_pushes_client_info_when_provided(self, mock_get_client):
        """Verify client field is included in the event when available."""
        from hipeac_mcp.services.analytics import _push_event

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        _push_event("search_vision", {"query": "AI"}, client="claude-desktop/1.2.0", client_id="abc-123")

        key, payload = mock_client.rpush.call_args[0]
        event = json.loads(payload)
        assert event["client"] == "claude-desktop/1.2.0"
        assert event["client_id"] == "abc-123"

    @patch("hipeac_mcp.services.analytics.get_redis_client")
    def test_silently_drops_when_redis_unavailable(self, mock_get_client):
        """Verify no exception is raised when Redis is not available."""
        from hipeac_mcp.services.analytics import _push_event

        mock_get_client.return_value = None
        _push_event("search_members", {"query": "test"})

    @patch("hipeac_mcp.services.analytics.get_redis_client")
    def test_silently_drops_on_redis_error(self, mock_get_client):
        """Verify no exception is raised when Redis rpush fails."""
        import redis

        from hipeac_mcp.services.analytics import _push_event

        mock_client = MagicMock()
        mock_client.rpush.side_effect = redis.RedisError("connection lost")
        mock_get_client.return_value = mock_client

        _push_event("search_members", {"query": "test"})
