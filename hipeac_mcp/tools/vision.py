"""MCP Tool for searching HiPEAC Vision documents."""

import asyncio

from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from hipeac_mcp import mcp
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


@mcp.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True))
@track_usage
async def search_vision(
    query: str,
    queries: list[str] | None = None,
    year: int | None = None,
    years: list[int] | None = None,
    limit: int = 4,
    ctx: Context = None,
) -> VisionSearchResponse:
    """Search HiPEAC Vision strategic documents using semantic search.

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
    For example:
    - User asks: "What does HiPEAC say about sustainable computing?"
      query:   "sustainability energy efficiency lifecycle IT"
      queries: ["carbon footprint embodied emissions hardware",
                "green computing policy Europe low power"]
    - User asks: "How should Europe tackle AI?"
      query:   "European AI strategy competitiveness"
      queries: ["AI accelerators hardware edge inference",
                "large language models orchestration distributed"]

    Keep each query short and keyword-dense (5-8 words). Avoid repeating the same
    terms across queries — each should probe a distinct semantic angle.

    **Table of Contents / Full Article Access:**
    When the user asks "what topics does the Vision cover?" or needs an enumeration of all
    articles, read the resource `hipeac://vision/{year}` — it contains the full TOC with
    summaries and download links. Each article result includes a `resource_uri`; use
    `resources/read` with that URI when a comprehensive answer requires complete article text.

    **Year-Specific Search:**
    - year=2025: Search only Vision 2025 (default: latest)
    - year=2024: Search only Vision 2024
    - years=[2024, 2025]: Search multiple years and compare perspectives

    **Use Cases:**
    - Current Trends: "What are the emerging trends in AI accelerators?"
    - Historical View: "What did Vision 2024 say about quantum computing?" (year=2024)
    - Evolution: "How has the vision on sustainability evolved?" (years=[2023, 2024, 2025])
    - Technology Adoption: "How should industry prepare for edge AI?"
    - Policy Guidance: "What recommendations exist for HPC infrastructure?"

    **Response Guidelines — Citation and Quoting:**
    When presenting results to the user, you MUST follow these rules:
    - Summaries and interpretations of the returned articles are encouraged and useful.
    - Direct quotes MUST be taken verbatim from the `content_preview` field only.
      Never fabricate, reconstruct, or paraphrase text as if it were a direct quote.
    - Every claim, quote, or interpretation MUST reference the source article using
      its `title` and `url`. Always present the URL as a clickable link.
    - If the `content_preview` does not contain enough text to support a specific
      claim, say so explicitly rather than inferring or inventing wording.

    :param query: Primary keyword-rich search query optimized for semantic similarity.
    :param queries: Up to 2 additional query variants probing different semantic angles.
    :param year: Specific Vision year to search (default: 2025, latest).
    :param years: List of years to search and compare (overrides year parameter).
    :param limit: Maximum number of articles to return (default: 4, max: 5).
    :returns: Structured search results with ranked articles.
    """
    actual_limit = min(limit, 5)
    all_queries = [query] + (queries[:2] if queries else [])

    if years:
        all_articles: list[VisionArticleResult] = []
        results_per_year = await asyncio.gather(
            *[_get_service(y).search_articles(all_queries, actual_limit) for y in years]
        )

        for response in results_per_year:
            all_articles.extend(response.articles)

        all_articles.sort(key=lambda a: a.similarity_score, reverse=True)

        return VisionSearchResponse(
            query=query,
            total_results=len(all_articles[:actual_limit]),
            articles=all_articles[:actual_limit],
        )

    search_year = year or 2025
    return await _get_service(search_year).search_articles(all_queries, actual_limit)
