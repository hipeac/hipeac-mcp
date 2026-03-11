"""Shared fixtures for integration tests."""

import asyncio
import contextlib
import os
import socket
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio


uvicorn = pytest.importorskip("uvicorn", reason="uvicorn not installed")

if not os.environ.get("OPENAI_API_KEY"):
    pytest.skip("OPENAI_API_KEY not set", allow_module_level=True)

if not os.environ.get("DATABASE_URL"):
    pytest.skip("DATABASE_URL not set", allow_module_level=True)


STARTUP_TIMEOUT_SECONDS = 10
SHUTDOWN_TIMEOUT_SECONDS = 5


def _free_port() -> int:
    """Find a free TCP port on localhost.

    :returns: An available port number.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@asynccontextmanager
async def _run_mcp_server():
    """Start the real HiPEAC MCP server on a random port and yield the URL.

    :yields: The base URL of the running MCP server (e.g. ``http://127.0.0.1:12345/``).
    :raises TimeoutError: If the server does not start within the timeout.
    """
    from hipeac_mcp.server import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    task = asyncio.create_task(server.serve())

    try:
        async with asyncio.timeout(STARTUP_TIMEOUT_SECONDS):
            while not server.started:
                await asyncio.sleep(0.05)
    except TimeoutError:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        raise TimeoutError(f"MCP server failed to start within {STARTUP_TIMEOUT_SECONDS}s") from None

    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=SHUTDOWN_TIMEOUT_SECONDS)
        except TimeoutError, asyncio.CancelledError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def mcp_url():
    """Fixture that provides the URL of a running MCP server for all integration tests.

    :yields: The MCP server base URL.
    """
    async with _run_mcp_server() as url:
        yield url
