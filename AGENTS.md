# Agent guidance for hipeac-mcp

Canonical source of truth for AI coding agents in this repo. `CLAUDE.md` and `.github/copilot-instructions.md` are symlinks to this file.

## Core philosophy

- Challenge ambiguous, complex, or risky requests; suggest better alternative. Don't follow blindly.
- Maintainability first; KISS & YAGNI; consistency over novelty; self-documenting code, type hints everywhere, comments only for non-obvious _why_.

## Stack

- **Backend**: MCP server (official `mcp` Python SDK, Streamable HTTP transport), Python 3.14, uv.
- **ORM**: Django 6 as ORM layer only — **read-only**; models belong to `hipeac-redux`. MySQL in production (read-only, SSL), SQLite in-memory in dev.
- **Vector search**: FAISS (`faiss-cpu`) + OpenAI embeddings; index at `HIPEAC_FAISS_INDEX_PATH` (`/storage/faiss` prod, `.faiss` dev).
- **Jobs**: huey (Redis-backed) for periodic FAISS reindexing (`hipeac_mcp/tasks.py`); reindex signals pushed by hipeac-redux via Redis.
- **Observability**: Sentry SDK (`sentry-sdk[mcp]`).

## Commands

All project commands via `./run` (loads `.env`, invokes `uv run`). Never call `uv` / `pytest` / `python manage.py` directly.

## Commit conventions

Conventional Commits: `type(scope): description` — imperative, lowercase, no trailing period, one line, no attribution trailers. Types: `feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `perf`. Breaking: `feat!:` / `BREAKING CHANGE:` footer. Never vague (`wip`, `update`).

## Git workflow

Branch + PR for sensitive areas — auth, permissions, serializers / schemas, payments, security settings, CI workflows — or when in doubt; everything else may go straight to `main`. Never merge your own PR.

## Specs

Shared OpenSpec store `hipeac-specs` (`openspec context` for path): specs + changes live there, not in this repo.

## Python

- PEP 8; type hints on all signatures.
- Docstrings (public functions/methods/modules): reST, Sphinx-compatible, no type info; `:param` / `:returns` / `:raises` end with period.
- `./run ruff format . && ./run ruff check hipeac_mcp` clean before commit; config in `pyproject.toml`; no inline ignores without justification comment.
- All new code needs tests. Tests in `tests/`, never inline. Suite: `./run pytest --cov=hipeac_mcp --cov-report=term`.
- `pytest-asyncio` in `auto` mode — async tests need no marker. `tests/conftest.py` runs `setup_django()` first; `redis_client` session fixture skips integration tests when Redis is unreachable.
- Mock/guard filesystem + external services; never production DB or live APIs.

### Test-review workflow

1. Read tests first; fix weak assertions before running.
2. Run adjusted suite — failure after adjustment = real bug.
3. Fix production code; never weaken a test to force green.

## Tools

- `MCPServer` instance in `hipeac_mcp/__init__.py`; tools in `hipeac_mcp/tools/<name>.py` via `@mcp.tool()`, resources in `hipeac_mcp/resources/` (e.g. `hipeac://vision/{year}/{slug}`).
- Tools = thin wrappers: validate input, call service, return structured result. Business logic in models/managers or `services/`; `services/` / `models/` / `tasks/` **must not** import `tools/` or server entrypoint.
- Inputs / outputs as Pydantic models in `hipeac_mcp/schemas/`; `structured_output=True`, `ToolAnnotations(readOnlyHint=True)` where appropriate.
- `@track_usage` (`services/analytics.py`) wraps tools for usage analytics.

## MCP tool docstrings (critical)

Tool docstrings are sent verbatim to the LLM as the tool's prompt — not human docs:

- Opening line: _when_ to call ("Call this when…"), not what it returns.
- Body: how to interpret / act on result — fields to prioritise, decisions, what to avoid.
- `:param` lines: usage instructions, not descriptions.
- Direct second person; no passive "Returns a list of…".

`hipeac_mcp/tools/vision.py` is the reference example — match its style for new tools.

## ORM — Django (read-only)

- Models in `hipeac_mcp/models/`, grouped by domain.
- `DJANGO_SETTINGS_MODULE = "hipeac_mcp.settings"`; call `setup_django()` (`hipeac_mcp/db.py`) once before any model use — also pre-populates content-type cache for async safety.
- **Read-only DB: never create or run migrations, never write.** `ReadOnlyRouter` (`db.py`: `allow_migrate` → `False`, `db_for_write` → `None`) enforces it.
- `CONN_MAX_AGE = 0` — connections not persisted across async thread-pool calls.

### Async tools and the (sync) Django ORM

Tool handlers are `async def` on the event loop; Django ORM is synchronous:

- Async ORM methods (`afirst()`, `acount()`, async iteration) or wrap sync calls with `sync_to_async`.
- **Call `ensure_connection_async()` before DB operations in async contexts** — closes stale thread-local connections, prevents MySQL 2006/2026 after long AI/FAISS operations.
- Keep `DatabaseConnectionMiddleware` (`server.py`) on the ASGI app — closes stale connections per request.
- **Never write sync ORM queries directly inside `async def` tool handlers.**

## Settings

- Django settings in `hipeac_mcp/settings.py` (minimal, read-only ORM config).
- `MCP_HTTP_PATH` env (default `/`); `HIPEAC_FAISS_INDEX_PATH` env.
- Secrets from env vars (`.env` dev via `./run`, platform config prod); never hardcode.

## Entrypoint

- `hipeac_mcp/server.py`: `mcp.streamable_http_app()` + `DatabaseConnectionMiddleware`, served by gunicorn (`gunicorn.config.py`).
- `hipeac_mcp/__main__.py`: stdio transport for dev/CLI.
- `hipeac_mcp/__init__.py`: builds `MCPServer`, inits Sentry, calls `setup_django()`, then imports `resources` + `tools` to register them.
- Indexing management commands (`index_vision`, `index_event`, `index_all_visions`, `preview_event_document`) under `hipeac_mcp/management/commands/`.

## Error monitoring (Sentry)

Use the Sentry MCP server to investigate errors proactively when debugging.

- **`regionUrl`**: `https://de.sentry.io`
- **`organizationSlug`**: `ea06`
- **`projectSlugOrId`**: `hipeac-mcp` (backend service)

Prefer **`resolvedInNextRelease`** over `resolved` — fix ships with next deployment.

### Bug fix workflow

Sentry issue reveals a bug not covered by an existing test — add regression test before/alongside the fix:

1. Reproduce first: failing test against current code, confirming root cause.
2. Fix code to pass.
3. Verify no related paths left uncovered.

Never close a Sentry bug without a corresponding regression test.

## Niche domain docs

- MCP tools & resources contract: `docs/` (`Tools.md`, `Resources.md`, `Integrations.md`).
