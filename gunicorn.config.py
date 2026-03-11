"""Gunicorn configuration for the HiPEAC MCP server."""

import os


bind = f":{os.environ.get('PORT', 5000)}"
workers = int(os.environ.get("GUNICORN_WORKERS", 1))
worker_class = "uvicorn_worker.UvicornWorker"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 30))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", 30))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", 5))
