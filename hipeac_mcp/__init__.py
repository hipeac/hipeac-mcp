"""HiPEAC MCP Server - Network analysis and member discovery tools."""

import logging
import os

import sentry_sdk
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import Icon
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.mcp import MCPIntegration

from .db import setup_django


# Disable OpenAI Agents integration: openai-agents is a dev-only dependency
# and the Sentry integration is incompatible with the installed version.
_disabled = []

try:
    from sentry_sdk.integrations.openai_agents import OpenAIAgentsIntegration

    _disabled.append(OpenAIAgentsIntegration)
except Exception:  # noqa: S110
    pass

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN", None),
    release=os.environ.get("GIT_REV", None),
    enable_logs=True,
    disabled_integrations=_disabled,
    integrations=[
        LoggingIntegration(
            sentry_logs_level=logging.WARNING,
        ),
        MCPIntegration(),
    ],
    traces_sample_rate=0.5,
    # pii
    send_default_pii=True,
)

setup_django()


server_instructions = "Access the HiPEAC research network: Vision strategic documents, network members, and events."

transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["mcp.hipeac.net", "mcp.hipeac.net:*", "localhost:*", "127.0.0.1:*"],
)

mcp = MCPServer(
    "HiPEAC",
    instructions=server_instructions,
    website_url="https://www.hipeac.net/mcp/",
    icons=[
        Icon(
            src="https://www.hipeac.net/static/images/hipeac--icon.png",
            mimeType="image/png",
        )
    ],
)

from . import resources, tools  # type: ignore[reportUnusedImport] # noqa: E402, F401


__all__ = ["mcp"]
