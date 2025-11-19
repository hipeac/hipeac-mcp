# HiPEAC MCP

[![github-tests-badge]][github-tests]
[![codecov-badge]][codecov]
[![license-badge]](LICENSE)

This MCP server provides intelligent search and discovery tools for the HiPEAC research network.

## Features

### Resources (Discoverable Metadata)

Agents can browse these resources to understand what data is available:

- `hipeac://metadata/topics` - All research topics in the network
- `hipeac://metadata/application-areas` - Application domains (Healthcare, Automotive, etc.)
- `hipeac://metadata/institution-types` - Types of organizations (academia, industry, SME, etc.)
- `hipeac://metadata/membership-types` - Membership levels and definitions

### Tools

**search_members**: Search network members with filters

- Text search in names, emails, institutions
- Filter by research topics and application areas
- Filter by country, institution type, membership type
- Returns detailed member profiles with affiliations

**find_experts**: Discover experts in specific research areas

- Find members by expertise (topics or application areas)
- Optional geographic filtering
- Returns top experts ranked by relevance

## How Agents Discover Metadata

The MCP protocol provides two complementary mechanisms:

### 1. Resources (Pull Model)

Agents can list and read resources to discover available options:

```python
# Agent workflow:
# 1. List available resources
resources = await client.list_resources()

# 2. Read specific metadata
topics = await client.read_resource("hipeac://metadata/topics")
# Returns formatted list: "Machine Learning (ID: 42)", etc.

# 3. Use discovered IDs in tool calls
await client.call_tool("search_members", {
    "topics": ["42", "Machine Learning"],  # Can use ID or name
    "limit": 10
})
```

### 2. Tool Schemas (Push Model)

Tool input schemas guide agents with inline descriptions:

```json
{
  "name": "search_members",
  "inputSchema": {
    "properties": {
      "topics": {
        "type": "array",
        "description": "Filter by research topic IDs or names. Use hipeac://metadata/topics resource to discover available topics."
      }
    }
  }
}
```

The descriptions explicitly reference resources, creating a discovery loop.

## Setup

1. Set environment variables:

   ```bash
   export DATABASE_URL="mysql://user:pass@host:port/dbname"
   export SENTRY_MCP_DSN="https://your-sentry-dsn@sentry.io/project"  # Optional
   export GIT_REV="v1.0.0"  # Optional, for release tracking
   ```

2. Install dependencies:

   ```bash
   uv sync
   ```

3. Run the server:
   ```bash
   ./run python -m hipeac_mcp
   ```

## Integration with Claude Desktop

### Using the Remote Server (Recommended)

Once deployed, users can connect to the server by adding this to their Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json`):

**Streamable HTTP transport** (recommended):

```json
{
  "mcpServers": {
    "hipeac": {
      "url": "https://mcp.hipeac.net/stream"
    }
  }
}
```

**SSE transport** (alternative):

```json
{
  "mcpServers": {
    "hipeac": {
      "url": "https://mcp.hipeac.net/sse"
    }
  }
}
```

The server provides multiple transport endpoints:

- `/stream` - Streamable HTTP (POST-based, recommended)
- `/sse` - Server-Sent Events transport
- `/` - Health check endpoint

## Development

### Install the dependencies

The application uses [uv][uv] to manage application dependencies.

```bash
uv sync --upgrade --group dev
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

## Design Philosophy

This MCP server focuses on **intelligence and synthesis** rather than CRUD operations:

- ✅ Search and discover members by research interests
- ✅ Find collaborators with complementary expertise
- ✅ Analyze network structure and research communities
- ❌ Create/update/delete member records (use the web API for that)

The goal is to provide value that goes beyond what the REST API offers: contextual recommendations, multi-dimensional searches, and intelligent matchmaking.

### Architecture

- **Django ORM** for type-safe, composable database queries (read-only mode)
- **Embedded models** - minimal model definitions mirroring hipeac-redux schema
- **Self-contained** - no runtime dependency on hipeac-redux project
- **Multi-layer write protection** - database, router, and model-level safeguards

See `.copilot/architecture.md` for detailed design decisions.

## Deployment (Dokku)

This server can be deployed to any Dokku instance:

```bash
# On your Dokku server
dokku apps:create mcp
dokku mysql:link hipeac-db mcp
dokku config:set mcp DATABASE_URL=mysql://user:pass@host:port/hipeac
dokku config:set mcp SENTRY_MCP_DSN=https://your-sentry-dsn@sentry.io/project  # Optional
dokku config:set mcp GIT_REV=$(git rev-parse --short HEAD)  # Optional

# Push to deploy
git remote add dokku dokku@your-server:mcp
git push dokku master
```

The server uses **Uvicorn with multiple workers** for production deployment. By default, it runs 2 worker processes. You can adjust this via the `Procfile` or by setting `WEB_CONCURRENCY` environment variable.

### Production Architecture

- **Server**: Uvicorn (async ASGI server)
- **Workers**: 2 worker processes (configurable)
- **Transports**:
  - Streamable HTTP at `/stream` (POST-based MCP protocol)
  - SSE at `/sse` (Server-Sent Events)
  - Health check at `/`
- **Concurrency**: Multiple workers for multi-core CPU utilization

### Client Configuration

The server provides multiple endpoints for different MCP transports:

**Streamable HTTP** (recommended):

```json
{
  "mcpServers": {
    "hipeac": {
      "url": "https://mcp.hipeac.net/stream"
    }
  }
}
```

**SSE** (alternative):

```json
{
  "mcpServers": {
    "hipeac": {
      "url": "https://mcp.hipeac.net/sse"
    }
  }
}
```

### Local Development

For local development with stdio transport:

```bash
./run python -m hipeac_mcp
```

For testing the SSE server locally:

```bash
./run python -m hipeac_mcp.server
```

[codecov]: https://app.codecov.io/gh/hipeac/hipeac-mcp
[codecov-badge]: https://codecov.io/gh/hipeac/hipeac-mcp/branch/main/graph/badge.svg?token=xZLoEWNzgu
[github-tests]: https://github.com/hipeac/hipeac-mcp/actions?query=workflow%3Atests
[github-tests-badge]: https://github.com/hipeac/hipeac-mcp/actions/workflows/tests.yml/badge.svg?branch=main
[license-badge]: https://img.shields.io/badge/license-MIT-blue.svg
[mcp]: https://github.com/modelcontextprotocol/python-sdk
[uv]: https://docs.astral.sh/uv/
