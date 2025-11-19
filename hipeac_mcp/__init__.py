"""HiPEAC MCP Server - Network analysis and member discovery tools."""

from mcp.server.fastmcp import FastMCP

from .db import setup_django


setup_django()

mcp = FastMCP("hipeac-mcp")

from . import resources, tools  # noqa: E402, F401


__all__ = ["mcp"]
