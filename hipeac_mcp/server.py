"""ASGI production application.

This module provides the MCP server via Streamable HTTP transport.
Endpoint: POST / (at root)
"""

from django.db import close_old_connections
from starlette.middleware.base import BaseHTTPMiddleware

from . import mcp


class DatabaseConnectionMiddleware(BaseHTTPMiddleware):
    """Middleware to manage Django database connections per request.

    This ensures connections are closed properly after each request to prevent
    stale connection errors (2006, 2026) in long-running servers with async ORM.

    With CONN_MAX_AGE=0, close_old_connections() closes all connections immediately.
    We also close connections before each request to ensure fresh connections.
    """

    async def dispatch(self, request, call_next):
        """Process request with proper database connection lifecycle.

        :param request: The incoming request.
        :param call_next: The next middleware or endpoint.
        :returns: The response.
        """
        close_old_connections()

        try:
            response = await call_next(request)
            return response
        finally:
            close_old_connections()


app = mcp.streamable_http_app()
app.add_middleware(DatabaseConnectionMiddleware)
