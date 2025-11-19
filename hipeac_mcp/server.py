"""HTTP/SSE server for production deployment.

This module provides an ASGI application for the MCP server,
suitable for deployment via Dokku with Uvicorn workers.
"""

import os

from hipeac_mcp import mcp


app = mcp.sse_app()


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 5000))
    mcp.settings.port = port
    mcp.settings.host = "0.0.0.0"
    mcp.run(transport="sse")
