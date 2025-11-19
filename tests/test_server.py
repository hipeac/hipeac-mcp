"""Tests for server initialization and configuration."""


class TestServerInitialization:
    """Tests for MCP server initialization."""

    def test_mcp_server_exists(self):
        """Test that FastMCP server instance is created."""
        from hipeac_mcp import mcp

        assert mcp is not None
        assert mcp.name == "hipeac-mcp"

    def test_tools_registered(self):
        """Test that tools are registered with the server."""
        from hipeac_mcp import mcp

        tool_names = [tool.name for tool in mcp._tool_manager._tools.values()]
        assert "search_members" in tool_names
        assert "find_experts" in tool_names
        assert len(tool_names) == 2

    def test_resources_registered(self):
        """Test that resources are registered with the server."""
        from hipeac_mcp import mcp

        assert len(mcp._resource_manager._resources) == 4

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
        assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.mysql"

    def test_read_only_router_exists(self):
        """Test read-only database router is configured."""
        from django.conf import settings

        assert "hipeac_mcp.db.ReadOnlyRouter" in settings.DATABASE_ROUTERS
