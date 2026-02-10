"""Integration tests using the OpenAI Agents SDK to call the MCP server.

These tests spin up the real MCP server (via its ASGI app) and connect an
OpenAI Agent via ``MCPServerStreamableHttp``.  They verify the full round-trip:
Agent → MCP transport → tool execution → structured response.

Requirements:
    - ``OPENAI_API_KEY`` environment variable set.
    - ``DATABASE_URL`` environment variable set (for real data).
    - ``pip install openai-agents`` (added to [dependency-groups] dev).

Run:
    ./run pytest tests/integration/ -v
"""

import asyncio
import re

import pytest


agents = pytest.importorskip("agents", reason="openai-agents not installed")

from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp


TEST_TIMEOUT_SECONDS = 60
MAX_AGENT_TURNS = 5


class TestAgentToolDiscovery:
    """Verify the agent can discover and list MCP tools."""

    @pytest.mark.asyncio(loop_scope="session")
    async def test_agent_lists_tools(self, mcp_url):
        """Agent discovers all registered MCP tools."""
        async with asyncio.timeout(TEST_TIMEOUT_SECONDS):
            async with MCPServerStreamableHttp(
                name="HiPEAC MCP",
                params={"url": mcp_url},
                cache_tools_list=True,
            ) as server:
                tools = await server.list_tools()
                tool_names = {t.name for t in tools}
                assert "get_metadata" in tool_names
                assert "search_members" in tool_names
                assert "search_vision" in tool_names


class TestAgentGetMetadata:
    """Verify the agent can call get_metadata via MCP."""

    @pytest.mark.asyncio(loop_scope="session")
    async def test_agent_calls_get_metadata(self, mcp_url):
        """Agent calls get_metadata and receives structured metadata."""
        async with asyncio.timeout(TEST_TIMEOUT_SECONDS):
            async with MCPServerStreamableHttp(
                name="HiPEAC MCP",
                params={"url": mcp_url},
                cache_tools_list=True,
            ) as server:
                agent = Agent(
                    name="Test Agent",
                    instructions=(
                        "Call the get_metadata tool and report how many topics, application areas, "
                        "and institution types are available. Reply with only those three numbers, "
                        "separated by commas, like: 42, 15, 8"
                    ),
                    mcp_servers=[server],
                )
                result = await Runner.run(agent, "Get the metadata.", max_turns=MAX_AGENT_TURNS)

                assert result.final_output is not None
                # The output should contain numbers (the counts).
                parts = result.final_output.replace(" ", "").split(",")
                assert len(parts) >= 3
                assert all(p.strip().isdigit() for p in parts[:3])


class TestAgentSearchMembers:
    """Verify the agent can search for HiPEAC members via MCP."""

    @pytest.mark.asyncio(loop_scope="session")
    async def test_agent_searches_by_country(self, mcp_url):
        """Agent uses search_members with a country filter."""
        async with asyncio.timeout(TEST_TIMEOUT_SECONDS):
            async with MCPServerStreamableHttp(
                name="HiPEAC MCP",
                params={"url": mcp_url},
                cache_tools_list=True,
            ) as server:
                agent = Agent(
                    name="Test Agent",
                    instructions=(
                        "Search for HiPEAC members in Belgium (country code BE). "
                        "Report the total number of results found as a single integer."
                    ),
                    mcp_servers=[server],
                )
                result = await Runner.run(agent, "Find members in Belgium.", max_turns=MAX_AGENT_TURNS)

                assert result.final_output is not None
                # There should be at least some members in Belgium.
                numbers = re.findall(r"\d+", result.final_output)
                assert len(numbers) >= 1
                assert int(numbers[0]) > 0
