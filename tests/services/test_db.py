"""Tests for database utility functions in hipeac_mcp.db."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from hipeac_mcp.db import (
    _content_type_cache,
    _preload_content_types,
    clear_content_type_cache,
    ensure_connection,
    get_content_type_id,
)


@pytest.fixture(autouse=True)
def clean_cache():
    """Clear the content type cache before and after each test.

    :yields: None.
    """
    clear_content_type_cache()
    yield
    clear_content_type_cache()


class TestPreloadContentTypes:
    """Tests for _preload_content_types."""

    def test_logs_warning_when_db_unavailable(self, caplog):
        """Logs a warning when the database connection fails during preload."""
        with patch("hipeac_mcp.db.connection") as mock_conn:
            mock_conn.cursor.side_effect = Exception("connection refused")
            with caplog.at_level(logging.WARNING, logger="hipeac_mcp.db"):
                _preload_content_types()

        assert "Could not preload content types" in caplog.text

    def test_skips_if_already_populated(self):
        """Does nothing when cache is already populated."""
        _content_type_cache["hipeac.activity"] = 99

        with patch("hipeac_mcp.db.connection") as mock_conn:
            _preload_content_types()
            mock_conn.cursor.assert_not_called()


class TestEnsureConnection:
    """Tests for ensure_connection retry logic."""

    def test_succeeds_on_first_attempt(self):
        """No exception when the first connection check succeeds."""
        with patch("hipeac_mcp.db.connection") as mock_conn:
            ensure_connection()
            mock_conn.ensure_connection.assert_called_once()

    def test_retries_after_non_transient_error(self):
        """Retries once on a generic error and succeeds on the second attempt."""
        with (
            patch("hipeac_mcp.db.connection") as mock_conn,
            patch("hipeac_mcp.db.close_old_connections") as mock_close,
        ):
            mock_conn.ensure_connection.side_effect = [Exception("gone"), None]
            ensure_connection()

        assert mock_conn.ensure_connection.call_count == 2
        mock_close.assert_called_once()

    def test_retries_with_sleep_on_transient_mysql_error(self):
        """Sleeps 0.2s before retrying on transient MySQL error codes (2006, 2026)."""
        with (
            patch("hipeac_mcp.db.connection") as mock_conn,
            patch("hipeac_mcp.db.close_old_connections"),
            patch("hipeac_mcp.db.time") as mock_time,
        ):
            mock_conn.ensure_connection.side_effect = [Exception(2006, "Server gone"), None]
            ensure_connection()

        mock_time.sleep.assert_called_once_with(0.2)

    def test_raises_on_second_failure(self):
        """Exception propagates when the retry also fails."""
        with (
            patch("hipeac_mcp.db.connection") as mock_conn,
            patch("hipeac_mcp.db.close_old_connections"),
        ):
            mock_conn.ensure_connection.side_effect = [Exception("first"), Exception("second")]
            with pytest.raises(Exception, match="second"):
                ensure_connection()


class TestGetContentTypeId:
    """Tests for get_content_type_id."""

    def test_returns_from_cache_when_present(self):
        """Cache hit returns the stored value without touching the database."""
        _content_type_cache["hipeac.activity"] = 42
        assert get_content_type_id("hipeac", "activity") == 42

    def test_logs_warning_on_cache_miss(self, caplog):
        """Logs a warning when the key is missing from the cache."""
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (99,)

        with patch("hipeac_mcp.db.connection") as mock_conn:
            mock_conn.cursor.return_value = mock_cursor
            with caplog.at_level(logging.WARNING, logger="hipeac_mcp.db"):
                result = get_content_type_id("hipeac", "activity")

        assert result == 99
        assert "ContentType cache miss" in caplog.text

    def test_populates_cache_after_live_query(self):
        """A successful live query stores the result in the cache for future calls."""
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (77,)

        with patch("hipeac_mcp.db.connection") as mock_conn:
            mock_conn.cursor.return_value = mock_cursor
            get_content_type_id("hipeac", "vision")

        assert _content_type_cache["hipeac.vision"] == 77

    def test_raises_key_error_when_not_found(self):
        """Raises KeyError when the content type does not exist in the database."""
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = None

        with patch("hipeac_mcp.db.connection") as mock_conn:
            mock_conn.cursor.return_value = mock_cursor
            with pytest.raises(KeyError, match="hipeac.nonexistent"):
                get_content_type_id("hipeac", "nonexistent")


class TestClearContentTypeCache:
    """Tests for clear_content_type_cache."""

    def test_empties_the_cache(self):
        """clear_content_type_cache removes all entries."""
        _content_type_cache["hipeac.activity"] = 42
        _content_type_cache["hipeac.vision"] = 7
        clear_content_type_cache()
        assert len(_content_type_cache) == 0

    def test_safe_to_call_when_already_empty(self):
        """Calling on an empty cache does not raise."""
        clear_content_type_cache()
        clear_content_type_cache()  # second call is a no-op
        assert len(_content_type_cache) == 0
