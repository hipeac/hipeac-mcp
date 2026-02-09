"""Django settings for HiPEAC MCP server.

Minimal Django configuration for read-only database access.
We only need the ORM, not the web framework.
"""

import os
from urllib.parse import urlparse


_database_url = os.environ.get("DATABASE_URL")

if _database_url:
    db = urlparse(_database_url)
    DATABASES = {  # type: ignore
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": db.path[1:],
            "USER": db.username,
            "PASSWORD": db.password,
            "HOST": db.hostname,
            "PORT": db.port,
            "OPTIONS": {
                "charset": "utf8mb4",
                "ssl_mode": "REQUIRED",
                "init_command": "SET SESSION TRANSACTION READ ONLY; SET sql_mode='STRICT_TRANS_TABLES';",
                "connect_timeout": 3,
                "read_timeout": 30,  # Prevent timeout during long AI operations
                "write_timeout": 30,
            },
            "CONN_MAX_AGE": 0,  # Don't persist connections with sync_to_async thread pools
            "CONN_HEALTH_CHECKS": True,  # Django 4.1+ - verify connection before each query
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "hipeac_mcp",
]

SECRET_KEY = os.environ.get("SECRET_KEY", "SECRET_KEY_NOT_USED_FOR_CRYPTO")

DEBUG = False
USE_TZ = True
TIME_ZONE = "UTC"

DATABASE_ROUTERS = ["hipeac_mcp.db.ReadOnlyRouter"]

# AI and RAG Configuration
# FAISS vector index storage path
# In production (Dokku), use /storage/faiss (persistent across deployments)
# In development, use .faiss in project root
FAISS_INDEX_PATH = os.environ.get(
    "HIPEAC_FAISS_INDEX_PATH", "/storage/faiss" if os.path.exists("/storage") else ".faiss"
)
