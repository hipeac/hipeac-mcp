"""MCP Tool for searching HiPEAC Vision documents."""

import asyncio

from mcp.server.fastmcp import Context
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

    **Entry point — always start here for any Vision content question.**
    Call this tool first whenever the user asks about HiPEAC Vision content,
    recommendations, technology trends, or strategies — even if you have seen
    Vision slugs or article titles earlier in the conversation. Prior context
    is not a substitute for a live search; use it only to phrase better queries.
    Do NOT call ``get_vision_article`` before running at least one search.

    Returns ranked articles with summaries and content previews.
    The MCP client should synthesize insights from the returned data.

    **Important — Query Optimization:**
    This tool performs direct embedding-based vector search — there is no LLM
    interpretation layer. You MUST rephrase the user's question into concise,
    keyword-rich search queries optimized for semantic similarity matching.

    **Multi-Query Strategy (strongly recommended):**
    A single embedding vector averages all concepts and can miss narrower articles.
    Use the `queries` parameter to provide up to 2 additional angle-specific variants
    alongside the primary `query`. All are searched in parallel and merged, so each
    article is found via its strongest matching angle.

    Each query variant should target a *different semantic angle* of the user's question:
    one might focus on the core technology, another on the application domain, another on
    the socio-economic or policy dimension. Keep each short and keyword-dense (5-8 words).
    Avoid repeating the same terms across variants — diversity is what improves recall.

    **Searching for unknown or rare terms (names, acronyms, coined words):**
    If the query is a single unfamiliar term (e.g. a coined word, acronym, or proper noun),
    do NOT create variants that just rephrase or append words to the same term — they will
    embed to the same sparse vector and find nothing. Instead, think about what the term
    likely *means* or *relates to* and use those surrounding concepts as your additional
    queries to find the context in which it appears.

    **Table of Contents / Full Article Access:**
    When the user asks "what topics does the Vision cover?" or needs an enumeration of all
    articles, call ``get_vision_overview``. Each article result includes a ``resource_uri``
    and a ``slug``; call ``get_vision_article(slug, year)`` only after a search has confirmed
    the article is relevant and the ``content_preview`` alone is insufficient (e.g., to
    enumerate all recommendations, extract detailed technical content, or answer follow-up
    questions that cannot be answered from the preview).

    **Year-Specific Search:**
    - (no year): The tool resolves the latest published Vision edition from
        the database and searches only that edition.
    - year=<year>: Search only the requested edition, even if it is still a draft.
    - years=[...]: Search the explicitly requested editions and merge by relevance.

    **Use Cases:**
    - Open-ended question (no year mentioned): omit both ``year`` and ``years`` so the tool
        uses the latest published Vision edition.
    - User explicitly asks for a specific year: pass ``year=<year>`` to scope the search,
        including draft editions when requested.
    - Explicit cross-edition comparison: pass ``years=[...]``.

    **Draft editions:**
    If a requested ``year`` or any year in ``years`` refers to a draft Vision edition,
    you MUST explicitly tell the user that the content is draft and may change.
    Each result includes an ``is_draft`` flag for this purpose.

    **Interpreting similarity scores:**
    Each result includes a ``similarity_score`` (cosine similarity, 0–1):
    - ≥ 0.45: strong match — answer with confidence.
    - 0.35–0.44: weak match returned as a fallback because no strong match existed.
      Treat these with lower confidence: signal to the user that the match is approximate
      and offer to search again with different keywords.
    - Results below 0.35 are never returned.

    **Response Guidelines — Citation and Quoting:**
    When presenting results to the user, you MUST follow these rules:
    - Summaries and interpretations of the returned articles are encouraged and useful.
    - Direct quotes MUST be verbatim from `content_preview` when working from search
      results. Never fabricate, reconstruct, or paraphrase text as if it were a direct
      quote. If the preview does not contain enough text, call ``get_vision_article``
      to obtain the full article — do not invent wording to fill the gap.
    - Every claim, quote, or interpretation MUST reference the source article using
      its `title` and `url`. Always present the URL as a clickable link.

    :param query: Primary keyword-rich search query optimized for semantic similarity.
    :param queries: Up to 2 additional query variants probing different semantic angles.
    :param year: Specific Vision year to search. Omit to search the latest published edition.
    :param years: Explicit list of years to search (overrides ``year``).
    :returns: Structured search results with ranked articles.
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

    **PREREQUISITE — you MUST call ``search_vision`` first.**
    The ``slug`` parameter MUST come from a ``search_vision`` result returned in the
    current session. Never call this tool with a slug taken from memory, prior
    conversation context, or inference — always run a search first to obtain a live,
    confirmed slug. If you already have a slug from earlier in the conversation,
    call ``search_vision`` again to verify it and retrieve fresh context.

    **Prefer ``resources/read`` if your client supports MCP resources** — use
    the ``resource_uri`` field from ``search_vision`` results directly. This tool
    exists as a fallback for clients that do not support the resources protocol.

    Only call this when ``search_vision`` confirmed the article exists and the
    ``content_preview`` alone is insufficient to answer the user's question.

    Each ``search_vision`` result includes a ``resource_uri`` of the form
    ``hipeac://vision/{year}/{slug}`` — the ``slug`` and ``year`` values map
    directly to the parameters of this tool.

    If ``year`` is omitted, the tool resolves the latest published Vision edition
    from the database. If you request a draft year explicitly, you MUST tell the
    user that the article content is draft and may change.

    :param slug: Article slug from a ``search_vision`` result in the current session.
    :param year: Vision year. Omit to use the latest published edition.
    :returns: Full article content as Markdown, starting with the title and summary.
    :raises ValueError: If no article matches the given slug and year.
    """
    if year is None:
        year = await _get_latest_published_year()

    return await _get_article(year=year, slug=slug)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
@track_usage
async def get_vision_overview(year: int | None = None, ctx: Context = None) -> str:
    """Retrieve the table of contents and download links for a HiPEAC Vision year.

    **Prefer ``resources/read`` with URI ``hipeac://vision/{year}`` if your client
    supports MCP resources.** This tool exists as a fallback for clients that do
    not support the resources protocol.

    Returns a JSON document with all sections and articles (title, slug, summary,
    resource URI, URL) plus PDF and EPUB download links. Use this when the user
    asks what topics the Vision covers, requests a full list of articles, or needs
    the document download URL.

    Always tell the user which year's overview you are showing. If ``year`` is
    omitted, the tool resolves the latest published Vision edition from the
    database. The returned JSON includes an ``is_draft`` flag; when it is true,
    you MUST explicitly tell the user the edition is draft and may change.

    :param year: Vision year to retrieve. Omit to use the latest published edition.
    :returns: JSON-encoded overview with sections, article summaries and file URLs.
    :raises ValueError: If no Vision document exists for the given year.
    """
    if year is None:
        year = await _get_latest_published_year()

    return await _get_overview(year=year)
