FROM python:3.13-slim

EXPOSE 5000

RUN apt-get update && \
  apt-get install -y --no-install-recommends build-essential default-libmysqlclient-dev pkg-config && \
  rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY uv.lock pyproject.toml /app/
RUN uv export --no-dev --no-emit-project > requirements.txt && \
    uv pip install --system --no-cache -r requirements.txt && \
    rm requirements.txt

COPY . /app
