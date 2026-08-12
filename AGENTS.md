# Agent guidance for hipeac-mcp

This file is the canonical source of truth for AI coding agents working in this repo.
Aliases: `CLAUDE.md` and `.github/copilot-instructions.md` are symlinks to this file.

## Core philosophy

- **Proactive collaboration**: do not blindly follow instructions. If a request is ambiguous, overly complex, or risky, challenge it and suggest a better alternative.
- **Maintainability first**: prioritise code that is easy to read, understand, and modify.
- **Simplicity (KISS & YAGNI)**: favour the most straightforward solution. Do not add functionality that has not been explicitly requested.
- **Consistency over novelty**: follow existing codebase conventions. Only introduce new patterns when clearly justified.

## Code generation style

- **Self-documenting code**: clear, unabbreviated names. Decompose into single-purpose functions. Use type hints.
- **Strategic commenting**: avoid comments explaining _what_ code does. Only comment _why_ when not obvious.
- **Testability**: write code that is easy to test. Prefer pure functions and clear interfaces.

## Stack

- **Backend**: MCP server (official `mcp` Python SDK, Streamable HTTP transport), Python 3.14, managed with uv.
- **ORM**: Django 6 used purely as the ORM layer — **read-only**. Models belong to the `hipeac-redux` project; this repo only reads them. MySQL in production (read-only, SSL, `CONN_MAX_AGE=0`), SQLite in-memory in dev.
- **Vector search**: FAISS (`faiss-cpu`) + OpenAI embeddings, index stored at `HIPEAC_FAISS_INDEX_PATH` (`/storage/faiss` in prod, `.faiss` in dev).
- **Background jobs**: huey (Redis-backed) for periodic FAISS reindexing (`hipeac_mcp/tasks.py`).
- **Cache/queue**: Redis (huey + reindex signals pushed by hipeac-redux).
- **Observability**: Sentry SDK (`sentry-sdk[mcp]`).

## Commands

A `./run` wrapper exists (`uv run --env-file .env "$@"`). **All project commands must be prefixed with `./run`** — it loads `.env` and invokes `uv run`. Do not call `uv` / `pytest` / `python manage.py` directly.

## Commit conventions

Conventional Commits. Short form: `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`, `test: ...`, `chore: ...`, `perf: ...`.
Optional scope: `type(scope): description` (e.g. `fix(tools): handle missing vision year`).
Imperative mood, lowercase, no trailing period.
Breaking change: `feat!: ...` or a `BREAKING CHANGE:` footer.
Never use vague messages like `wip` or `update`.

## Python

### General

- All code must be PEP 8 compliant.
- All function signatures must use type hints.

### Docstring format (reStructuredText)

- All public functions, methods, and modules **must** have a docstring.
- Format must be reStructuredText (reST) to be compatible with Sphinx.
- Provide clear descriptions for parameters, return values, and any exceptions raised.
- Do not include type information — it is already in the function signature.
- All `:param`, `:returns`, and `:raises` descriptions must end with a period (`.`) for consistency.

```python
def get_user_by_id(user_id: int, is_active: bool = True) -> User | None:
    """Fetch a user from the database by their primary key.

    :param user_id: The primary key of the user to retrieve.
    :param is_active: If True, only search for active users.
    :returns: The User object or None if not found.
    :raises User.DoesNotExist: If no user with the given ID is not found.
    """
```

### Commands

```
./run pytest --cov=hipeac_mcp --cov-report=term      # full test suite with coverage
./run ruff format .                                   # format
./run ruff check hipeac_mcp                            # lint (must be clean before commit)
```

### Testing (pytest)

We test **behaviour**, not functions. We test **boundaries**, not external libraries.

- All new code requires tests.
- Tests live in `tests/` (subdirs: `integration/`, `models/`, `resources/`, `services/`, `tools/`), never inline next to source.
- Structure tests using the Arrange-Act-Assert (AAA) pattern.
- Use `@pytest.fixture` for setup and `@pytest.mark.parametrize` for testing multiple inputs.
- `pytest-asyncio` is in `auto` mode — async tests need no marker.
- Anything touching the filesystem or external services must be guarded/mocked. Never hit the production DB or live APIs in tests.
- Coverage config lives in `pyproject.toml` (`[tool.coverage.*]`); `--cov=hipeac_mcp` is set in `[tool.pytest.ini_options].addopts`.
- `tests/conftest.py` auto-setups Django (via `setup_django()`) before any test runs. The `redis_client` session fixture skips integration tests when Redis is unreachable.

#### Test-review workflow

When asked to review, audit, or add tests to existing code, apply this sequence:

1. **Read the tests first.** Critically evaluate each test: does the assertion actually verify the claimed behaviour, or is it trivially true? Are edge cases and failure paths covered? Are there implicit assumptions that could make the test fragile?
2. **Adjust the tests** to fix any identified weaknesses before running them.
3. **Run the adjusted suite.** A failing test after adjustment is valuable — it reveals a real bug in production code.
4. **Fix the production code** to make failing tests pass — never weaken a test to force it green.

### Ruff

- Ruff handles both linting and formatting. Config lives in `pyproject.toml` (`target-version = "py314"`, `line-length = 120`).
- Selected rule sets, per-file ignores (`tests/**` ignores `S101`, `S108`, `D`, `T201`), and isort config are declared there — do not inline-ignore without a justification comment.
- Run `./run ruff format . && ./run ruff check hipeac_mcp` before committing.

## MCP server + Django ORM

### ORM — Django (read-only)

This project uses the **Django ORM** for models, but **read-only** — the models belong to `hipeac-redux`. There is no FastAPI/REST layer; the HTTP surface is the MCP server.

- Models live in `hipeac_mcp/models/` (Django models, grouped by domain). Business logic belongs in models, managers, or `services/` — tools stay thin.
- `DJANGO_SETTINGS_MODULE = "hipeac_mcp.settings"`; call `setup_django()` (from `hipeac_mcp/db.py`) once before any model use. It also pre-populates the content-type cache for async safety.
- **Never create or run migrations in this repo.** `ReadOnlyRouter` (`db.py`) returns `False` from `allow_migrate` and `None` from `db_for_write`. There are no migrations to edit.
- `CONN_MAX_AGE = 0` — connections are not persisted across async thread-pool calls.

### Async tools and the (sync) Django ORM

The Django ORM is synchronous. MCP tool handlers are `async def` and run on the event loop.

- Use async ORM methods (`afirst()`, `acount()`, async queryset iteration) or wrap sync ORM calls with `sync_to_async`.
- **Call `ensure_connection_async()` before DB operations in async contexts.** It closes stale thread-local connections and prevents transient MySQL errors (2006/2026) after long-running AI/FAISS operations.
- `DatabaseConnectionMiddleware` in `server.py` closes stale connections before/after each request — do not remove it.
- **Do not write sync ORM queries directly inside `async def` tool handlers.**

### Tool definitions

- Tools live in `hipeac_mcp/tools/<name>.py` and are registered on the `mcp` `MCPServer` instance (constructed in `hipeac_mcp/__init__.py`) via `@mcp.tool()`.
- Each MCP tool is a thin wrapper: validate inputs, call a service, return a structured result. **No business logic in tool bodies** — push it into `services/`.
- Tool inputs and outputs use Pydantic models (`hipeac_mcp/schemas/`) for type safety and auto-generated schemas. Use `structured_output=True` and `ToolAnnotations(readOnlyHint=True)` where appropriate.
- MCP resources live in `hipeac_mcp/resources/` (e.g. `hipeac://vision/{year}/{slug}`).
- `@track_usage` (from `services/analytics.py`) wraps tools for usage analytics.
- `services/` **must not** import from `tools/` or the server entrypoint.

### MCP tool docstrings (critical)

MCP tool docstrings are **not** documentation for human developers — they are instructions sent verbatim to the LLM as the tool's system prompt. Write them accordingly:

- **Opening line**: tell the model *when* to call the tool ("Call this when…"), not what it returns.
- **Body**: explain how to *interpret and act on* the result — which fields to prioritise, what decisions to make, what to avoid.
- **`:param` lines**: keep these as usage instructions (how to call correctly), not prose descriptions.
- **Avoid passive voice** like "Returns a list of…" — the model already sees the return type.
- **Tone**: direct second-person.

`hipeac_mcp/tools/vision.py` is the reference example — match its style for new tools.

### Settings

- Django settings in `hipeac_mcp/settings.py` (minimal, read-only ORM config).
- MCP HTTP path via `MCP_HTTP_PATH` env (default `/`).
- FAISS index path via `HIPEAC_FAISS_INDEX_PATH` env.
- Secrets from env vars (`.env` in dev via `./run`, platform config in prod). Never hardcode.

### Entrypoint

- ASGI app in `hipeac_mcp/server.py` (`mcp.streamable_http_app()` + `DatabaseConnectionMiddleware`), served by gunicorn (`gunicorn hipeac_mcp.server:app --config gunicorn.config.py`).
- `hipeac_mcp/__main__.py` runs the MCP server via stdio transport (dev/CLI).
- `hipeac_mcp/__init__.py` constructs the `MCPServer` instance, initialises Sentry, calls `setup_django()`, then imports `resources` and `tools` to register them.

### Commands (MCP / Django management)

```
./run python -m hipeac_mcp                                       # run MCP server via stdio (dev/CLI)
./run gunicorn hipeac_mcp.server:app --config gunicorn.config.py # prod ASGI (or `./run` + Procfile)
./run huey_consumer hipeac_mcp.tasks.huey -w 2 -q                # huey worker (FAISS reindexing)
./run python manage.py index_vision <year>                      # index a Vision year
./run python manage.py index_event <event_id>                    # index an Event
./run python manage.py index_all_visions                        # index all Vision editions
./run python manage.py preview_event_document <event_id>        # preview an Event document
```

### Things to avoid (MCP-specific)

- Do not import `tools/` or the server entrypoint from `services/`, `models/`, or `tasks/`.
- Do not create migrations or attempt writes — the database is read-only by router.

## Niche domain docs

- MCP tools & resources contract: `docs/` (`Tools.md`, `Resources.md`, `Integrations.md`).

## Error monitoring (Sentry)

You have access to the Sentry MCP server. Use it to investigate errors proactively when debugging issues.

- **`regionUrl`**: `https://de.sentry.io`
- **`organizationSlug`**: `ea06`
- **`projectSlugOrId`**: `hipeac-mcp` (backend service)

When resolving issues, prefer **`resolvedInNextRelease`** over `resolved` — this signals the fix is in the next deployment rather than already live.

### Bug fix workflow

When a Sentry issue reveals a bug that is not covered by an existing test, always add a regression test before (or alongside) the fix:

1. **Reproduce first**: write a test that fails against the current code, confirming you have isolated the root cause.
2. **Fix the code**: make the test pass.
3. **Verify no new gaps**: confirm no related paths are left uncovered.

Never close a Sentry bug without a corresponding regression test. The fix lives in the code; the test ensures it stays fixed.