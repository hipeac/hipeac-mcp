web: gunicorn hipeac_mcp.server:app --config gunicorn.config.py
worker: huey_consumer.py hipeac_mcp.tasks.huey -w 2 -q
