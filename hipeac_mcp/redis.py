"""Redis client utilities for the HiPEAC MCP server.

Provides a shared, cached Redis client used by analytics and background tasks.
"""

import logging
import os

import redis


logger = logging.getLogger(__name__)

_client: redis.Redis | None = None
_checked = False


def get_redis_client() -> redis.Redis | None:
    """Get a cached Redis client, returning None if unavailable.

    The client is created once and reused across calls. If ``REDIS_URL``
    is not configured or the connection fails, returns None.

    :returns: Redis client or None if Redis is not available.
    """
    global _client, _checked

    if _checked:
        return _client

    redis_url = os.environ.get("REDIS_URL")

    if not redis_url:
        _checked = True
        return None

    try:
        _client = redis.from_url(redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
        _client.ping()  # type: ignore[no-untyped-call]
        _checked = True
        return _client
    except redis.RedisError:
        logger.warning("Failed to connect to Redis")
        _checked = True
        _client = None
        return None


def reset_redis_client() -> None:
    """Reset the cached Redis client.

    Useful for testing or after connection failures.
    """
    global _client, _checked
    _client = None
    _checked = False
