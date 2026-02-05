"""Database utilities for HiPEAC MCP server."""

import logging
import os
from typing import Any

import django
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections, connection
from django.db.models import Model


logger = logging.getLogger(__name__)


def setup_django():
    """Initialize Django ORM for standalone use.

    This configures Django to use the hipeac-redux models in read-only mode.
    Call this once at startup before using any models.
    """
    if not settings.configured:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hipeac_mcp.settings")
        django.setup()


def ensure_connection():
    """Ensure database connection is alive and healthy.

    This function checks if the connection is usable and recreates it if needed.
    Call this before database operations or after long operations.

    :raises: Exception if connection cannot be established.
    """
    try:
        connection.ensure_connection()
    except Exception as e:
        logger.warning(f"Database connection lost, reconnecting: {e}")
        close_old_connections()
        connection.ensure_connection()


async def ensure_connection_async():
    """Async-safe version of ensure_connection.

    Use this in async contexts before database queries to prevent MySQL 2006 errors,
    especially after long-running operations (FAISS searches, AI generation).
    """
    await sync_to_async(ensure_connection)()


class ReadOnlyRouter:
    """Database router that enforces read-only access.

    This prevents accidental writes to the database from the MCP server.
    """

    def db_for_read(self, model: type[Model], **hints: dict[str, Any]) -> str:
        """All reads go to the default database.

        :param model: Model being queried.
        :param hints: Additional routing hints.
        :returns: Database alias.
        """
        return "default"

    def db_for_write(self, model: type[Model], **hints: dict[str, Any]) -> None:
        """Prevent all writes by returning None.

        :param model: Model being written.
        :param hints: Additional routing hints.
        :returns: None to prevent writes.
        """
        return None

    def allow_migrate(self, db: str, app_label: str, model_name: str | None = None, **hints: dict[str, Any]) -> bool:
        """Prevent migrations.

        :param db: Database alias.
        :param app_label: App label.
        :param model_name: Model name.
        :param hints: Additional hints.
        :returns: False to prevent migrations.
        """
        return False


__all__ = ["setup_django", "ensure_connection", "ensure_connection_async", "ReadOnlyRouter"]
