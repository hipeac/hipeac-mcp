"""MCP Tool for searching HiPEAC Vision documents."""

import asyncio

from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from hipeac_mcp import mcp
from hipeac_mcp.db import ensure_connection_async
from hipeac_mcp.models.vision import Vision
from hipeac_mcp.resources.vision import get_vision_article as _get_article
from hipeac_mcp.resources.vision import get_vision_overview as _get_overview
from hipeac_mcp.schemas.vision import VisionArticleResult, VisionSearchResponse
from hipeac_mcp.services.analytics import track_usage
from hipeac_mcp.services.rags import VisionRagService


_service_cache: dict[int, VisionRagService] = {}


def _get_service(year: int) -> VisionRagService:
    """Get a cached VisionRagService for the given year.

    :param year: Vision year.
    :returns: Cached service instance.
    """
    if year not in _service_cache:
        _service_cache[year] = VisionRagService(year=year)
    return _service_cache[year]


async def _get_latest_published_year() -> int:
    """Resolve the latest published Vision year from the database.

    :returns: Latest published Vision year.
    :raises ValueError: If no published Vision edition exists.
    """
    await ensure_connection_async()

    latest = await Vision.objects.filter(status=Vision.PUBLISHED).order_by("-year").only("year").afirst()
    if latest is None:
        raise ValueError("No published Vision edition found.")

    return latest.year


@mcp.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True))
@track_usage
async def search_vision(
    query: str,
    queries: list[str] | None = None,
    year: int | None = None,
    years: list[int] | None = None,
    ctx: Context = None,
) -> VisionSearchResponse:
    """Search HiPEAC Vision strategic documents using semantic search.

    Entry point for any Vision content question — call this before
    ``get_vision_article``, even if you already have a slug from earlier in
    the conversation. Returns ranked articles with summaries and content
    previews for you to synthesize an answer from.

    This is direct embedding-based vector search with no LLM interpretation
    layer: rephrase the user's question into concise, keyword-rich queries.
    A single query embedding averages all concepts, so for multi-faceted
    questions pass up to 2 extra angle-specific variants via ``queries``
    (e.g. one on the core technology, one on the application domain) — all
    are searched in parallel and merged. For a single unfamiliar term
    (acronym, coined word, proper noun), don't rephrase the same term —
    instead search for concepts it likely relates to.

    For a full table of contents / article enumeration, use
    ``get_vision_overview`` instead. Each result has a ``resource_uri`` and
    ``slug``; only call ``get_vision_article`` after a search confirms the
    article is relevant and ``content_preview`` isn't enough.

    :param query: Primary keyword-rich search query optimized for semantic similarity.
    :param queries: Up to 2 additional query variants probing different semantic angles.
    :param year: Specific Vision year to search, including drafts. Omit for the latest published edition.
    :param years: Explicit list of years to search (overrides ``year``), merged by relevance.
    :returns: Structured search results with ranked articles. Each has ``similarity_score``
        (0–1; results are dropped below 0.35) and ``is_draft`` — tell the user when true.
        ``is_fallback=true`` on the response means no strong match existed above 0.45.
    """
    all_queries = [query] + (queries[:2] if queries else [])

    if years:
        search_years = years
    elif year is not None:
        search_years = [year]
    else:
        search_years = [await _get_latest_published_year()]

    if len(search_years) == 1:
        return await _get_service(search_years[0]).search_articles(all_queries)

    all_articles: list[VisionArticleResult] = []
    results_per_year = await asyncio.gather(*[_get_service(y).search_articles(all_queries) for y in search_years])
    for response in results_per_year:
        all_articles.extend(response.articles)

    all_articles.sort(key=lambda a: a.similarity_score, reverse=True)

    return VisionSearchResponse(
        query=query,
        total_results=len(all_articles),
        articles=all_articles,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
@track_usage
async def get_vision_article(slug: str, year: int | None = None, ctx: Context = None) -> str:
    """Retrieve the full markdown content of a HiPEAC Vision article.

    Requires a ``slug`` from a ``search_vision`` result in the current session
    — never from memory or prior conversation context, since it may be stale.
    Prefer ``resources/read`` with the result's ``resource_uri`` if your
    client supports MCP resources; this tool is the fallback. Only call this
    when the search's ``content_preview`` isn't enough to answer the question.

    :param slug: Article slug from a ``search_vision`` result in the current session.
    :param year: Vision year. Omit to use the latest published edition.
    :returns: Full article content as Markdown, starting with the title and summary.
        Tell the user if the article is from a draft edition.
    :raises ValueError: If no article matches the given slug and year.
    """
    if year is None:
        year = await _get_latest_published_year()

    return await _get_article(year=year, slug=slug)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
@track_usage
async def get_vision_overview(year: int | None = None, ctx: Context = None) -> str:
    """Retrieve the table of contents and download links for a HiPEAC Vision year.

    Prefer ``resources/read`` with URI ``hipeac://vision/{year}`` if your
    client supports MCP resources; this tool is the fallback. Use this when
    the user asks what topics the Vision covers, wants a full article list,
    or needs the PDF/EPUB download URL. Always tell the user which year you're
    showing.

    :param year: Vision year to retrieve. Omit to use the latest published edition.
    :returns: JSON-encoded overview with sections, article summaries and file URLs.
        Tell the user if ``is_draft`` is true.
    :raises ValueError: If no Vision document exists for the given year.
    """
    if year is None:
        year = await _get_latest_published_year()

    return await _get_overview(year=year)
