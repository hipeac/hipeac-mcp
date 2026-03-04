"""Schemas for Vision RAG search tool."""

from pydantic import BaseModel, Field


class VisionReference(BaseModel):
    """A footnote reference cited in a Vision article."""

    code: str = Field(..., description="Short reference code (e.g., 'DraghiReport')")
    text: str = Field(..., description="Full citation text")


class VisionArticleResult(BaseModel):
    """A single Vision article search result."""

    slug: str = Field(..., description="Article slug identifier (used in resource URIs and URLs)")
    title: str = Field(..., description="Article title")
    section: str = Field(..., description="Vision section (e.g., 'Chapters', 'Recommendations')")
    summary: str = Field(..., description="Brief article summary")
    vision_year: int = Field(..., description="Vision year (e.g., 2025)")
    similarity_score: float = Field(..., description="Semantic similarity score (0-1)", ge=0, le=1)
    content_preview: str = Field(
        ...,
        description="Verbatim excerpt of the matching article content (~800 chars). "
        "This is the ONLY text that may be presented as a direct quote. "
        "Do not fabricate or reconstruct quotes beyond what appears here.",
    )
    references: list[VisionReference] = Field(
        default_factory=list, description="Footnote references cited in the matching content"
    )
    resource_uri: str = Field(
        ...,
        description="MCP resource URI for retrieving the full article markdown content. "
        "Use resources/read with this URI when a comprehensive answer requires the complete text "
        "(e.g. enumerating all recommendations, detailed technical content).",
    )
    url: str = Field(
        ...,
        description="Canonical article URL on hipeac.net. MUST be cited as a clickable link "
        "whenever this article's content is quoted, summarised, or referenced.",
    )


class VisionSearchResponse(BaseModel):
    """Response from Vision semantic search."""

    query: str = Field(..., description="The search query used")
    total_results: int = Field(..., description="Total number of articles found")
    articles: list[VisionArticleResult] = Field(..., description="Matching Vision articles ranked by relevance")
