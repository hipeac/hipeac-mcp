"""Database utilities for HiPEAC MCP server."""

import logging
import os
import time
from typing import Any

import django
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections, connection
from django.db.models import Model


_content_type_cache: dict[str, int] = {}


logger = logging.getLogger(__name__)


def setup_django():
    """Initialize Django ORM for standalone use.

    This configures Django to use the hipeac-redux models in read-only mode.
    Call this once at startup before using any models.
    Also pre-populates the content type cache for async safety.
    """
    if not settings.configured:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hipeac_mcp.settings")
        django.setup()

    _preload_content_types()


def _preload_content_types() -> None:
    """Pre-populate the content type cache from the database.

    Called during ``setup_django`` so that ``get_content_type_id``
    never needs to query the database at runtime (safe for async).
    """
    if _content_type_cache:
        return

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, app_label, model FROM django_content_type")
            for row in cursor.fetchall():
                _content_type_cache[f"{row[1]}.{row[2]}"] = row[0]
        logger.debug(f"Preloaded {len(_content_type_cache)} content types")
    except Exception as e:
        logger.warning(f"Could not preload content types: {e}")


# MySQL error codes that indicate a dropped or broken connection.
_MYSQL_RECONNECT_CODES = {
    2002,  # CR_CONNECTION_ERROR – can't connect (TCP timeout / server briefly unreachable)
    2006,  # CR_SERVER_GONE_ERROR – server has gone away
    2026,  # CR_SSL_CONNECTION_ERROR – TLS/SSL error (unexpected EOF, etc.)
}


def ensure_connection():
    """Ensure database connection is alive and healthy.

    Retries once with a short backoff on transient MySQL SSL/connection errors
    (codes 2006 and 2026) that are common with remote servers.
    Call this before database operations or after long-running operations.

    :raises: Exception if connection cannot be established after retry.
    """
    for attempt in range(2):
        try:
            connection.ensure_connection()
            return
        except Exception as e:
            error_code = e.args[0] if e.args else None
            is_transient = error_code in _MYSQL_RECONNECT_CODES

            if attempt == 0 and is_transient:
                logger.warning(f"Transient MySQL error ({error_code}), reconnecting: {e}")
                close_old_connections()
                time.sleep(0.2)
            elif attempt == 0:
                logger.warning(f"Database connection lost, reconnecting: {e}")
                close_old_connections()
            else:
                raise


async def ensure_connection_async():
    """Async-safe version of ensure_connection.

    Closes all stale thread-local connections before delegating to
    ``ensure_connection``.  Django's async ORM dispatches queries via
    ``sync_to_async`` thread workers; each worker has its own thread-local
    connection that may have been dropped by the MySQL server while idle.
    Calling ``close_old_connections()`` here, *before* entering the thread
    pool, ensures every worker starts with a fresh connection instead of
    inheriting a dead one.

    Use this in async contexts before database queries to prevent transient MySQL
    connection errors (server gone away, TLS/SSL drops), especially after
    long-running operations (FAISS searches, AI generation).
    """
    await sync_to_async(close_old_connections)()
    await sync_to_async(ensure_connection)()


class ReadOnlyRouter:
    """Database router that enforces read-only access.

    This prevents accidental writes to the database from the MCP server.
    """

    def db_for_read(self, model: type[Model], **hints: Any) -> str:
        """All reads go to the default database.

        :param model: Model being queried.
        :param hints: Additional routing hints.
        :returns: Database alias.
        """
        return "default"

    def db_for_write(self, model: type[Model], **hints: Any) -> str | None:
        """Prevent all writes by returning None.

        :param model: Model being written.
        :param hints: Additional routing hints.
        :returns: None to prevent writes.
        """
        return None

    def allow_migrate(self, db: str, app_label: str, model_name: str | None = None, **hints: Any) -> bool:
        """Prevent migrations.

        :param db: Database alias.
        :param app_label: App label.
        :param model_name: Model name.
        :param hints: Additional hints.
        :returns: False to prevent migrations.
        """
        return False


def get_content_type_id(app_label: str, model: str) -> int:
    """Look up a content type ID from the ``django_content_type`` table.

    Results are cached in memory to avoid repeated queries.
    The cache is pre-populated by ``setup_django``, so this is safe
    to call from async contexts.

    :param app_label: The application label (e.g. ``"hipeac"``).
    :param model: The model name in lowercase (e.g. ``"activity"``).
    :returns: The primary key of the matching content type.
    :raises KeyError: If the content type is not in the cache and cannot be loaded.
    """
    key = f"{app_label}.{model}"

    if key not in _content_type_cache:
        # The cache should have been pre-populated by setup_django.
        # A miss here means preloading failed; falling back to a live query is
        # not async-safe — log a warning so the gap is visible in production.
        logger.warning(f"ContentType cache miss for {key!r} — preload may have failed")

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM django_content_type WHERE app_label = %s AND model = %s",
                [app_label, model],
            )
            row = cursor.fetchone()

        if row is None:
            raise KeyError(f"ContentType not found: {app_label}.{model}")

        _content_type_cache[key] = row[0]

    return _content_type_cache[key]


def clear_content_type_cache() -> None:
    """Clear the content type cache.

    Only needed in tests.
    """
    _content_type_cache.clear()


__all__ = [
    "setup_django",
    "ensure_connection",
    "ensure_connection_async",
    "get_content_type_id",
    "clear_content_type_cache",
    "ReadOnlyRouter",
]
