"""Shared test configuration and fixtures."""

import os

import pytest
import redis


@pytest.fixture(autouse=True)
def setup_django():
    """Automatically setup Django before any test runs.

    :yields: None.
    """
    from hipeac_mcp.db import setup_django as _setup_django

    _setup_django()
    yield


@pytest.fixture(scope="session")
def redis_client():
    """Provide a real Redis client for integration tests.

    Connects to ``REDIS_URL`` if set, otherwise tries ``redis://localhost:6379``.
    Skips the test when Redis is not reachable.

    :returns: A connected Redis client.
    """
    url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    client = redis.from_url(url, decode_responses=True)

    try:
        client.ping()
    except redis.RedisError:
        pytest.skip("Redis is not available")

    return client


@pytest.fixture
def redis_test_key(redis_client):
    """Provide a unique Redis key that is cleaned up after the test.

    :param redis_client: The session-scoped Redis client.
    :returns: A unique test key string.
    """
    key = "hipeac:mcp:test"
    yield key
    redis_client.delete(key)
