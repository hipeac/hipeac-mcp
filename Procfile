web: gunicorn hipeac_mcp.server:app --workers 1 --worker-class uvicorn_worker.UvicornWorker --bind 0.0.0.0:$PORT
worker: huey_consumer.py hipeac_mcp.tasks.huey -w 2 -q
