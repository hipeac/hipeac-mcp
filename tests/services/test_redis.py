"""Tests for Redis client utilities."""

import os
from unittest.mock import MagicMock, patch

import pytest
import redis as real_redis

from hipeac_mcp.redis import get_redis_client, reset_redis_client


@pytest.fixture(autouse=True)
def reset_state():
    """Reset Redis client state before each test."""
    reset_redis_client()
    yield
    reset_redis_client()


class TestGetRedisClient:
    """Tests for get_redis_client."""

    @patch.dict(os.environ, {}, clear=True)
    def test_returns_none_without_redis_url(self):
        """Returns None when REDIS_URL is not set."""
        # Remove REDIS_URL if present
        os.environ.pop("REDIS_URL", None)
        result = get_redis_client()
        assert result is None

    @patch.dict(os.environ, {}, clear=True)
    def test_caches_none_result(self):
        """After checking once, subsequent calls return None without re-checking."""
        os.environ.pop("REDIS_URL", None)
        first = get_redis_client()
        second = get_redis_client()
        assert first is None
        assert second is None

    @patch("hipeac_mcp.redis.redis")
    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"})
    def test_returns_client_on_success(self, mock_redis_mod):
        """Returns a Redis client when connection succeeds."""
        mock_client = MagicMock()
        mock_redis_mod.from_url.return_value = mock_client

        result = get_redis_client()

        assert result is mock_client
        mock_client.ping.assert_called_once()

    @patch("hipeac_mcp.redis.redis")
    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"})
    def test_returns_none_on_connection_error(self, mock_redis_mod):
        """Returns None when Redis connection fails."""
        mock_client = MagicMock()
        mock_client.ping.side_effect = real_redis.RedisError("Connection refused")
        mock_redis_mod.RedisError = real_redis.RedisError
        mock_redis_mod.from_url.return_value = mock_client

        result = get_redis_client()

        assert result is None

    @patch("hipeac_mcp.redis.redis")
    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"})
    def test_caches_successful_client(self, mock_redis_mod):
        """Client is cached after successful connection."""
        mock_client = MagicMock()
        mock_redis_mod.from_url.return_value = mock_client

        first = get_redis_client()
        second = get_redis_client()

        assert first is second
        # from_url should only be called once
        mock_redis_mod.from_url.assert_called_once()


class TestResetRedisClient:
    """Tests for reset_redis_client."""

    @patch("hipeac_mcp.redis.redis")
    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"})
    def test_reset_allows_reconnection(self, mock_redis_mod):
        """After reset, get_redis_client attempts a new connection."""
        mock_client = MagicMock()
        mock_redis_mod.from_url.return_value = mock_client

        get_redis_client()
        assert mock_redis_mod.from_url.call_count == 1

        reset_redis_client()
        get_redis_client()
        assert mock_redis_mod.from_url.call_count == 2


class TestRealRedis:
    """Integration tests using a real Redis server."""

    def test_real_connection(self, redis_client, redis_test_key):
        """Verify basic operations against a real Redis server."""
        redis_client.rpush(redis_test_key, "hello")
        redis_client.rpush(redis_test_key, "world")

        assert redis_client.llen(redis_test_key) == 2
        assert redis_client.lpop(redis_test_key) == "hello"

    def test_get_redis_client_returns_real_client(self, redis_client):
        """get_redis_client returns a working client when REDIS_URL is valid."""
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")

        with patch.dict(os.environ, {"REDIS_URL": url}):
            reset_redis_client()
            client = get_redis_client()

        assert client is not None
        assert client.ping() is True
