"""Database utilities for HiPEAC MCP server."""

import os

import django
from django.conf import settings


def setup_django():
    """Initialize Django ORM for standalone use.

    This configures Django to use the hipeac-redux models in read-only mode.
    Call this once at startup before using any models.
    """
    if not settings.configured:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hipeac_mcp.settings")
        django.setup()


class ReadOnlyRouter:
    """Database router that enforces read-only access.

    This prevents accidental writes to the database from the MCP server.
    """

    def db_for_read(self, model, **hints):
        """All reads go to the default database.

        :param model: Model being queried.
        :param hints: Additional routing hints.
        :returns: Database alias.
        """
        return "default"

    def db_for_write(self, model, **hints):
        """Prevent all writes by returning None.

        :param model: Model being written.
        :param hints: Additional routing hints.
        :returns: None to prevent writes.
        """
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Prevent migrations.

        :param db: Database alias.
        :param app_label: App label.
        :param model_name: Model name.
        :param hints: Additional hints.
        :returns: False to prevent migrations.
        """
        return False


__all__ = ["setup_django", "ReadOnlyRouter"]
