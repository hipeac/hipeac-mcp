# HiPEAC MCP

[![github-tests-badge]][github-tests]
[![codecov-badge]][codecov]
[![license-badge]](LICENSE)

This MCP server provides intelligent search and discovery tools for the HiPEAC research network.

> **Full Documentation**: Please visit our **[Wiki](https://github.com/hipeac/hipeac-mcp/wiki)** for features, architecture, and integration guides.

## Development

The HiPEAC MCP uses the [MCP Python SDK][mcp] for the server implementation and [Django][django] ORM for (read-only) database access.

### Install the dependencies

The application uses [uv][uv] to manage application dependencies.

```bash
uv sync --upgrade --group dev
```

### Run the app in development mode

```bash
./run python manage.py runserver
```

### Run the tests

```bash
./run pytest --cov=hipeac_mcp --cov-report=term
```

### Style guide

Tab size is 4 spaces. Max line length is 120. You should run `ruff` before committing any change.

```bash
./run ruff format . && ./run ruff check hipeac_mcp
```

[github-tests]: https://github.com/hipeac/hipeac-mcp/actions/workflows/tests.yml
[github-tests-badge]: https://github.com/hipeac/hipeac-mcp/actions/workflows/tests.yml/badge.svg
[codecov]: https://codecov.io/gh/hipeac/hipeac-mcp
[codecov-badge]: https://codecov.io/gh/hipeac/hipeac-mcp/graph/badge.svg?token=WJ0VU42OON
[license-badge]: https://img.shields.io/badge/License-MIT-blue.svg

[django]: https://www.djangoproject.com/
[mcp]: https://modelcontextprotocol.github.io/python-sdk/
