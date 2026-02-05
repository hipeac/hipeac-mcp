"""Schemas for Vision RAG search tool."""

from pydantic import BaseModel, Field


class VisionReference(BaseModel):
    """A footnote reference cited in a Vision article."""

    code: str = Field(..., description="Short reference code (e.g., 'DraghiReport')")
    text: str = Field(..., description="Full citation text")


class VisionArticleResult(BaseModel):
    """A single Vision article search result."""

    id: str = Field(..., description="Article slug identifier")
    title: str = Field(..., description="Article title")
    section: str = Field(..., description="Vision section (e.g., 'Chapters', 'Recommendations')")
    summary: str = Field(..., description="Brief article summary")
    vision_year: int = Field(..., description="Vision year (e.g., 2025)")
    similarity_score: float = Field(..., description="Semantic similarity score (0-1)", ge=0, le=1)
    content_preview: str = Field(..., description="Preview of matching content (first ~400 chars)")
    references: list[VisionReference] = Field(
        default_factory=list, description="Footnote references cited in the matching content"
    )
    url: str = Field(..., description="Full article URL on hipeac.net")


class VisionSearchResponse(BaseModel):
    """Response from Vision semantic search."""

    query: str = Field(..., description="The search query used")
    total_results: int = Field(..., description="Total number of articles found")
    articles: list[VisionArticleResult] = Field(..., description="Matching Vision articles ranked by relevance")
