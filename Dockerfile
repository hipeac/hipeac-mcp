FROM python:3.15-slim AS builder

# uv is only needed at build time. It is copied to /usr/bin so the runtime stage
# can take /usr/local/bin wholesale (console scripts: gunicorn, huey_consumer)
# without dragging the uv binary into the final image.
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/bin/uv

WORKDIR /app

# Toolchain and MariaDB headers are needed only to compile mysqlclient, which
# ships no manylinux wheel. They stay in this stage.
RUN apt-get update && \
  apt-get install -y --no-install-recommends build-essential default-libmysqlclient-dev pkg-config && \
  rm -rf /var/lib/apt/lists/*

# Lockfile + project metadata only: a code change must never invalidate this layer.
COPY uv.lock pyproject.toml /app/
RUN /usr/bin/uv export --no-dev --no-emit-project | \
  /usr/bin/uv pip install --system --no-cache --compile-bytecode -r /dev/stdin

FROM python:3.15-slim

EXPOSE 5000

# Runtime half of default-libmysqlclient-dev: the shared library mysqlclient links against.
RUN apt-get update && \
  apt-get install -y --no-install-recommends libmariadb3 && \
  rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.15/site-packages /usr/local/lib/python3.15/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

COPY . /app
