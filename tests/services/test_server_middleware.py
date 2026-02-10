"""Tests for the DatabaseConnectionMiddleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hipeac_mcp.server import DatabaseConnectionMiddleware


class TestDatabaseConnectionMiddleware:
    """Tests for the database connection middleware."""

    @pytest.fixture
    def middleware(self):
        """Provide a middleware instance with a mock app."""
        app = MagicMock()
        return DatabaseConnectionMiddleware(app)

    @patch("hipeac_mcp.server.close_old_connections")
    async def test_closes_connections_before_request(self, mock_close, middleware):
        """Connections are closed before forwarding the request."""
        request = MagicMock()
        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)

        # close_old_connections called at least once before call_next
        assert mock_close.call_count >= 2  # before + finally

    @patch("hipeac_mcp.server.close_old_connections")
    async def test_returns_response_on_success(self, mock_close, middleware):
        """Successful request returns the response from call_next."""
        request = MagicMock()
        expected_response = MagicMock()
        call_next = AsyncMock(return_value=expected_response)

        response = await middleware.dispatch(request, call_next)

        assert response is expected_response

    @patch("hipeac_mcp.server.close_old_connections")
    async def test_closes_connections_on_exception(self, mock_close, middleware):
        """Connections are closed when call_next raises."""
        request = MagicMock()
        call_next = AsyncMock(side_effect=RuntimeError("DB error"))

        with pytest.raises(RuntimeError, match="DB error"):
            await middleware.dispatch(request, call_next)

        # close_old_connections should be called multiple times (before + except + finally)
        assert mock_close.call_count >= 3

    @patch("hipeac_mcp.server.close_old_connections")
    async def test_always_closes_in_finally(self, mock_close, middleware):
        """Connections are always closed in the finally block."""
        request = MagicMock()
        call_next = AsyncMock(return_value=MagicMock())

        await middleware.dispatch(request, call_next)

        # Last call should be the finally close
        assert mock_close.called
