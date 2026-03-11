"""Shared fixtures for service tests."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import Context


@dataclass
class FakeImplementation:
    """Minimal stand-in for mcp.types.Implementation (used as client_info)."""

    name: str
    version: str | None = None


@dataclass
class FakeInitializeRequestParams:
    """Minimal stand-in for mcp.types.InitializeRequestParams."""

    client_info: FakeImplementation | None = None


@dataclass
class FakeSession:
    """Minimal stand-in for mcp.server.session.ServerSession."""

    client_params: FakeInitializeRequestParams | None = None


@dataclass
class FakeRequestContext:
    """Minimal stand-in for ServerRequestContext."""

    session: FakeSession | None = None


@dataclass
class FakeContext:
    """Structured mock for FastMCP Context that mirrors the real attribute chain.

    Using dataclasses instead of MagicMock ensures tests fail if product code
    accesses wrong attribute names (e.g. ``clientInfo`` instead of ``client_info``).
    """

    request_context: FakeRequestContext | None = None
    client_id: str | None = None


def build_fake_context(
    *, client_name: str = "test-client", client_version: str = "1.0.0", client_id: str | None = None
) -> FakeContext:
    """Build a fake Context with a realistic client_info chain.

    :param client_name: Client implementation name.
    :param client_version: Client implementation version.
    :param client_id: Optional client instance identifier.
    :returns: A structured fake Context.
    """
    return FakeContext(
        request_context=FakeRequestContext(
            session=FakeSession(
                client_params=FakeInitializeRequestParams(
                    client_info=FakeImplementation(name=client_name, version=client_version),
                ),
            ),
        ),
        client_id=client_id,
    )


@pytest.fixture
def fake_ctx() -> FakeContext:
    """Create a fake Context with default client info.

    :returns: FakeContext with ``test-client/1.0.0``.
    """
    return build_fake_context()


@pytest.fixture
def mock_ctx() -> MagicMock:
    """Create a MagicMock Context (spec-constrained) for tests that need mocking.

    :returns: MagicMock with spec=Context.
    """
    return MagicMock(spec=Context)
