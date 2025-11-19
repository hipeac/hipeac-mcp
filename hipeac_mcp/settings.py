"""Django settings for HiPEAC MCP server.

Minimal Django configuration for read-only database access.
We only need the ORM, not the web framework.
"""

import os
from urllib.parse import urlparse


db = urlparse(os.environ.get("DATABASE_URL"))

DATABASES = {
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
        },
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
