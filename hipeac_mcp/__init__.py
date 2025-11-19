"""HiPEAC MCP Server - Network analysis and member discovery tools."""

import logging
import os

import sentry_sdk
from mcp.server.fastmcp import FastMCP
from sentry_sdk.integrations.logging import LoggingIntegration

from .db import setup_django


sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN", None),
    release=os.environ.get("GIT_REV", None),
    enable_logs=True,
    integrations=[
        LoggingIntegration(
            sentry_logs_level=logging.WARNING,
        ),
    ],
    traces_sample_rate=0.1,
)

setup_django()


server_instructions = """
This MCP server provides network analysis and member discovery tools for the HiPEAC community.
"""

mcp = FastMCP("hipeac-mcp", stateless_http=True, streamable_http_path="/", instructions=server_instructions)

from . import resources, tools  # type: ignore[reportUnusedImport] # noqa: E402, F401


__all__ = ["mcp"]
