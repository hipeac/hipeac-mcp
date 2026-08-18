"""Tests for server initialization and configuration."""

import asyncio


class TestServerInitialization:
    """Tests for MCP server initialization."""

    def test_mcp_server_exists(self):
        """Test that MCPServer instance is created."""
        from hipeac_mcp import mcp

        assert mcp is not None
        assert mcp.name == "HiPEAC"

    def test_tools_registered(self):
        """Test that the expected public MCP tools are available via the public API."""
        from hipeac_mcp import mcp

        tool_names = [t.name for t in asyncio.run(mcp.list_tools())]
        assert "get_metadata" in tool_names
        assert "search_members" in tool_names
        assert "list_events" in tool_names
        assert "search_in_event" in tool_names
        assert "search_jobs" in tool_names
        assert "get_job" in tool_names
        assert "search_vision" in tool_names

    def test_resources_registered(self):
        """Test that Vision resource templates are registered with expected URI patterns."""
        from hipeac_mcp import mcp

        templates = asyncio.run(mcp.list_resource_templates())
        uris = [str(t.uri_template) for t in templates]
        assert "hipeac://vision/{year}/{slug}" in uris
        assert "hipeac://vision/{year}" in uris

    def test_server_asgi_app(self):
        """Test that server exports ASGI app."""
        from hipeac_mcp.server import app

        assert app is not None


class TestDatabaseSetup:
    """Tests for database configuration."""

    def test_django_settings_configured(self):
        """Test Django settings are properly configured."""
        from django.conf import settings

        assert settings.configured
        assert "django.db.backends" in settings.DATABASES["default"]["ENGINE"]

    def test_read_only_router_exists(self):
        """Test read-only database router is configured."""
        from django.conf import settings

        assert "hipeac_mcp.db.ReadOnlyRouter" in settings.DATABASE_ROUTERS
