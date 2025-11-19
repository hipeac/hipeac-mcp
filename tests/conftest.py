"""Shared test configuration and fixtures."""

import pytest


@pytest.fixture(autouse=True)
def setup_django():
    """Automatically setup Django before any test runs.

    :yields: None.
    """
    from hipeac_mcp.db import setup_django as _setup_django

    _setup_django()
    yield
