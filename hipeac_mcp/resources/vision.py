"""MCP resources for HiPEAC Vision articles and documents."""

import json

from hipeac_mcp import mcp
from hipeac_mcp.db import ensure_connection_async, get_content_type_id
from hipeac_mcp.models.vision import HIPEAC_BASE_URL, VisionArticle, VisionFile, VisionSection


@mcp.resource(
    "hipeac://vision/{year}/{slug}",
    mime_type="text/markdown",
    name="Vision Article",
    description=(
        "Full markdown content of a HiPEAC Vision article. "
        "Use this when a comprehensive answer requires the complete article text, "
        "such as enumerating all recommendations or detailed technical content."
    ),
)
async def get_vision_article(year: int, slug: str) -> str:
    """Return the full content of a Vision article as Markdown.

    :param year: The Vision year (e.g. 2025).
    :param slug: The article slug.
    :returns: Article content formatted as Markdown.
    :raises ValueError: If no article matches the given year and slug.
    """
    await ensure_connection_async()
    try:
        article = await VisionArticle.objects.select_related("section__vision").aget(
            slug=slug, section__vision__year=year
        )
    except VisionArticle.DoesNotExist:
        raise ValueError(f"Vision article '{slug}' not found for year {year}.") from None

    summary = article.get_summary()

    header_parts = [f"# {article.title}", ""]
    if article.section.vision.is_draft:
        header_parts.extend(
            [
                "> Draft Vision content. This edition is not yet published and may change.",
                "",
            ]
        )
    if summary:
        header_parts.extend([f"> {summary}", ""])
    header_parts.extend(["---", ""])

    return "\n".join(header_parts) + (article.content or "")


@mcp.resource(
    "hipeac://vision/{year}",
    mime_type="application/json",
    name="Vision Overview",
    description=(
        "Table of contents and download links (PDF, EPUB) for a HiPEAC Vision year. "
        "Use this when listing all sections and articles, or when the user needs the document download URL."
    ),
)
async def get_vision_overview(year: int) -> str:
    """Return metadata, TOC and download links for a Vision year as JSON.

    :param year: The Vision year (e.g. 2025).
    :returns: JSON-encoded overview with sections, articles and file URLs.
    :raises ValueError: If no Vision document exists for the given year.
    """
    await ensure_connection_async()

    sections_qs = (
        VisionSection.objects.select_related("vision")
        .prefetch_related("articles")
        .filter(vision__year=year)
        .order_by("position")
    )
    sections = [s async for s in sections_qs]

    if not sections:
        raise ValueError(f"No Vision document found for year {year}.")

    vision = sections[0].vision

    files_qs = VisionFile.objects.filter(
        content_type_id=get_content_type_id("hipeac", "vision"),
        object_id=vision.pk,
        is_public=True,
    )
    files = {f.file_type: f.absolute_url async for f in files_qs}

    toc = [
        {
            "section": section.name,
            "articles": [
                {
                    "title": article.title,
                    "slug": article.slug,
                    "summary": article.get_summary(),
                    "resource_uri": f"hipeac://vision/{year}/{article.slug}",
                    "url": f"{HIPEAC_BASE_URL}/vision/{year}/{article.slug}/",
                }
                async for article in section.articles.order_by("position").all()
            ],
        }
        for section in sections
    ]

    return json.dumps(
        {
            "year": year,
            "title": f"HiPEAC Vision {year}",
            "is_draft": vision.is_draft,
            "pdf_url": files.get("pdf"),
            "epub_url": files.get("epub"),
            "sections": toc,
        },
        indent=2,
    )
