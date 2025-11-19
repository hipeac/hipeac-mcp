"""Entry point for running the HiPEAC MCP server."""

from . import mcp


if __name__ == "__main__":
    mcp.run(transport="stdio")
