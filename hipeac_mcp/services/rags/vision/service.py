"""Vision RAG service for HiPEAC Vision document search and exploration."""

import logging
import re
import time
from typing import Any

from asgiref.sync import sync_to_async

from hipeac_mcp.db import ensure_connection_async
from hipeac_mcp.models.vision import VisionArticle
from hipeac_mcp.schemas.vision import VisionArticleResult, VisionReference, VisionSearchResponse
from hipeac_mcp.services.rags.base import BaseRagService

from .generator import VisionDocumentGenerator


logger = logging.getLogger(__name__)

HIPEAC_BASE_URL = "https://www.hipeac.net"


class VisionRagService(BaseRagService):
    """RAG service for HiPEAC Vision documents.

    Each Vision year gets its own FAISS index (e.g., vision_articles_2025).
    Returns structured ``VisionSearchResponse`` directly — no LLM post-processing,
    so the MCP client can synthesize its own answer from the raw data.
    """

    COLLECTION_DESCRIPTION = "HiPEAC Vision articles for semantic search and exploration"

    def __init__(self, year: int = 2025):
        """Initialize the Vision RAG service for a specific year.

        :param year: Vision year to search (default: 2025, the latest).
        """
        self.year = year
        self.COLLECTION_NAME = f"vision_articles_{year}"
        super().__init__()
        self.generator = VisionDocumentGenerator(chunk_size=1500)

    async def search_articles(self, query: str, limit: int = 10) -> VisionSearchResponse:
        """Search Vision articles and return a structured response.

        Performs FAISS semantic search, aggregates chunks by article, enriches
        with DB metadata (summary, URL), and returns a ``VisionSearchResponse``.

        :param query: Natural language search query.
        :param limit: Maximum number of articles to return (max: 5).
        :returns: Structured search response with ranked articles.
        """
        actual_limit = min(limit, 5)
        articles = await self.search(query, actual_limit)

        return VisionSearchResponse(
            query=query,
            total_results=len(articles),
            articles=[
                VisionArticleResult(
                    id=article["id"],
                    title=article["title"],
                    section=article["section"],
                    summary=article["summary"],
                    vision_year=article["vision_year"],
                    similarity_score=article["similarity_score"],
                    content_preview=article["content_preview"],
                    references=[VisionReference(code=r["code"], text=r["text"]) for r in article.get("references", [])],
                    url=f"{HIPEAC_BASE_URL}{article['url']}",
                )
                for article in articles
            ],
        )

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search for Vision article chunks and aggregate by article.

        :param query: Search query string.
        :param limit: Maximum number of articles to retrieve.
        :returns: List of aggregated article results.
        """
        start = time.time()
        try:
            base_results = await super().search(query, limit * 3)
            logger.info(f"FAISS search completed in {time.time() - start:.2f}s ({len(base_results)} chunks)")

            aggregated = self._aggregate_chunks(base_results)

            if aggregated:
                await self._enrich_from_database(aggregated)

            for result in aggregated.values():
                if result["section"] == "Chapters":
                    result["similarity_score"] = min(1.0, result["similarity_score"] + 0.1)

            formatted_results = sorted(aggregated.values(), key=lambda x: x["similarity_score"], reverse=True)[:limit]

            for result in formatted_results:
                full_text = " ".join(result["chunks"][:2])
                resolved = self._resolve_inline_references(full_text, result.get("references", []))
                result["content_preview"] = self._truncate_on_word_boundary(resolved, 800)
                result.pop("chunks", None)

            logger.info(f"Total search completed in {time.time() - start:.2f}s")
            return formatted_results

        except Exception as e:
            logger.error(f"Error searching Vision articles after {time.time() - start:.2f}s: {e}")
            return []

    def _aggregate_chunks(self, base_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Aggregate FAISS chunk results by article slug.

        :param base_results: Raw chunk-level search results.
        :returns: Dictionary of slug -> aggregated article data.
        """
        aggregated: dict[str, dict[str, Any]] = {}

        for result in base_results:
            meta = result["metadata"]
            slug = meta["slug"]
            vision_year = meta.get("vision_year", self.year)

            if slug not in aggregated:
                aggregated[slug] = {
                    "id": slug,
                    "title": meta["title"],
                    "section": meta["section"],
                    "summary": "",
                    "vision_year": vision_year,
                    "similarity_score": result["similarity_score"],
                    "chunks": [],
                    "url": f"/vision/{vision_year}/{slug}/",
                }
            else:
                aggregated[slug]["similarity_score"] = max(
                    aggregated[slug]["similarity_score"], result["similarity_score"]
                )

            aggregated[slug]["chunks"].append(result["content"])

        return aggregated

    async def _enrich_from_database(self, aggregated: dict[str, dict[str, Any]]) -> None:
        """Enrich aggregated results with summary, URL, authors, and references from the database.

        Fetches ``content_tree`` to extract author names and footnote references.
        References are filtered to only those cited in the matched chunks.

        :param aggregated: Mutable dictionary of slug -> article data.
        """
        db_start = time.time()
        try:
            await ensure_connection_async()

            from django.db.models import Q

            q_obj = Q()
            for article_data in aggregated.values():
                q_obj |= Q(slug=article_data["id"], section__vision__year=article_data["vision_year"])

            articles_qs = (
                VisionArticle.objects.filter(q_obj)
                .select_related("section__vision")
                .only("slug", "section__vision__year", "title", "summary", "ai_summary", "content_tree")
            )

            async for article_obj in articles_qs:
                if article_obj.slug not in aggregated:
                    continue

                entry = aggregated[article_obj.slug]
                entry["url"] = await sync_to_async(article_obj.get_absolute_url)()
                entry["summary"] = await sync_to_async(article_obj.get_summary)()

                tree = article_obj.content_tree or {}
                # Filter references to those cited in matched chunks
                all_refs = tree.get("references", [])
                if all_refs:
                    cited_codes = self._extract_reference_codes(entry.get("chunks", []))
                    entry["references"] = [r for r in all_refs if r.get("code") in cited_codes]
                else:
                    entry["references"] = []

            logger.info(f"DB enrichment completed in {time.time() - db_start:.2f}s")

        except Exception as e:
            logger.warning(f"Failed to enrich vision articles from DB: {e}")

    @staticmethod
    def _extract_reference_codes(chunks: list[str]) -> set[str]:
        """Extract footnote reference codes from chunk content.

        Looks for patterns like ``[SamAltman]`` or ``[CRA-EU]`` in the text.

        :param chunks: List of chunk text strings.
        :returns: Set of reference codes found in the chunks.
        """
        codes: set[str] = set()
        for chunk in chunks:
            codes.update(re.findall(r"\[([A-Za-z0-9_-]+)\]", chunk))
        return codes

    @staticmethod
    def _resolve_inline_references(text: str, references: list[dict[str, str]]) -> str:
        """Replace inline reference markers with markdown links.

        Converts ``[BBC-Willow]`` to ``[BBC-Willow](url)`` when the reference
        URL is available, so the LLM sees clickable sources in context.

        :param text: Content preview text with inline markers.
        :param references: List of reference dicts with ``code`` and ``text`` keys.
        :returns: Text with resolved reference links.
        """
        if not references:
            return text

        ref_urls: dict[str, str] = {}
        for ref in references:
            ref_text = ref.get("text", "")
            # Extract URL from reference text (may be just a URL, or text ending with one)
            url_match = re.search(r"https?://\S+", ref_text)
            if url_match:
                ref_urls[ref["code"]] = url_match.group(0)

        for code, url in ref_urls.items():
            text = text.replace(f"[{code}]", f"[{code}]({url})")

        return text

    @staticmethod
    def _truncate_on_word_boundary(text: str, max_length: int) -> str:
        """Truncate text on a word boundary, preserving markdown links.

        Cuts at the last space before ``max_length``. If that falls inside
        a ``[text](url)`` markdown link, backs up to before the opening ``[``.

        :param text: Text potentially containing markdown links.
        :param max_length: Maximum character length.
        :returns: Truncated text.
        """
        if len(text) <= max_length:
            return text

        cut = text.rfind(" ", 0, max_length)
        if cut == -1:
            cut = max_length

        # If we would cut inside a markdown link, extend to include it
        last_open = text.rfind("[", 0, max_length)
        if last_open != -1:
            closing_paren = text.find(")", last_open)
            if closing_paren != -1 and closing_paren >= cut:
                return text[: closing_paren + 1]

        return text[:cut]

    async def index_article(self, article: VisionArticle) -> bool:
        """Index a single vision article in the vector database.

        :param article: VisionArticle instance to index.
        :returns: True if successful, False otherwise.
        """
        try:
            if not self.generator.should_index_article(article, self.year):
                logger.warning(
                    f"Skipping article {article.slug} (year {article.section.vision.year}) "
                    f"- does not match service year {self.year}"
                )
                return False

            chunk_dicts = self.generator.generate_chunks(article)

            ids = [chunk["id"] for chunk in chunk_dicts]
            documents = [chunk["content"] for chunk in chunk_dicts]
            metadatas = [chunk["metadata"] for chunk in chunk_dicts]

            embeddings: list[list[float]] = []
            for chunk in chunk_dicts:
                embedding = await self.generate_embedding(chunk["content"])
                embeddings.append(embedding)

            success = self.upsert_documents(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)

            if success:
                logger.info(f"Successfully indexed {len(chunk_dicts)} chunks for vision article {article.pk}")
            return success

        except Exception as e:
            logger.error(f"Error indexing vision article {article.pk}: {e}")
            return False
