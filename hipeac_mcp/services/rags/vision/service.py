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


MIN_SIMILARITY_SCORE = 0.45
"""Minimum cosine similarity required for an article to appear in results.

Articles whose best-matching chunk scores below this value are dropped from
the response.  Calibrated against 10-query smoke tests: relevant queries
return 0.48–0.73, off-topic queries (blockchain, food) produce 0.27–0.41.
Raised from 0.42 to 0.45 to filter borderline false positives (e.g. Cybersecurity
appearing for compiler/tooling queries).
"""

FALLBACK_SIMILARITY_SCORE = 0.35
"""Lower threshold used when the primary search returns zero results.

Rare or coined terms (e.g. acronyms, proper nouns) embed to sparse vectors
that can fall just below MIN_SIMILARITY_SCORE even when the concept exists in
the corpus. This threshold gives the model something to reason from rather than
a silent empty response. Results returned under this threshold include a lower
similarity score so the model can still signal low confidence if needed.
"""

AGGREGATE_SCORE_PENALTY = 0.85
"""Score multiplier applied to aggregate articles (``is_aggregate=True``).

Articles like ``Recommendations`` are cross-cutting compilations that duplicate
content from every chapter.  Without a penalty they appear in almost every
result set, pushing out genuinely relevant chapter articles.  0.85 suppresses
them enough to rank below the primary chapter unless there is no better match.
"""

MAX_CHUNKS_PER_ARTICLE = 2
"""Maximum chunks accepted per article from the raw FAISS candidate pool.

Broad articles (e.g. "New Hardware", "Recommendations") have many chunks
covering diverse topics and can consume the entire candidate pool, preventing
narrower but more relevant articles from surfacing.  Capping at 2 ensures
fair representation across all articles in the index.
"""


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

    async def search_articles(self, queries: list[str] | str) -> VisionSearchResponse:
        """Search Vision articles and return a structured response.

        Accepts one or more queries. Multiple queries are searched in parallel
        against FAISS and their raw chunk results are merged (keeping the
        highest score per chunk) before aggregation, so each distinct semantic
        angle has a fair chance to surface relevant articles.

        :param queries: One query string or a list of up to 3 query strings.
        :returns: Structured search response with ranked articles.
        """
        primary_query = queries[0] if isinstance(queries, list) else queries
        articles, is_fallback = await self.search(queries)

        return VisionSearchResponse(
            query=primary_query,
            total_results=len(articles),
            is_fallback=is_fallback,
            articles=[
                VisionArticleResult(
                    slug=article["slug"],
                    title=article["title"],
                    section=article["section"],
                    summary=article["summary"],
                    vision_year=article["vision_year"],
                    is_draft=article["is_draft"],
                    similarity_score=article["similarity_score"],
                    content_preview=article["content_preview"],
                    references=[VisionReference(code=r["code"], text=r["text"]) for r in article.get("references", [])],
                    resource_uri=f"hipeac://vision/{article['vision_year']}/{article['slug']}",
                    url=f"{HIPEAC_BASE_URL}{article['url']}",
                )
                for article in articles
            ],
        )

    async def search(self, queries: list[str] | str) -> tuple[list[dict[str, Any]], bool]:
        """Search for Vision article chunks and aggregate by article.

        Accepts one or more query strings.  When multiple queries are given
        they are searched in parallel and their chunk results merged before
        aggregation, giving each semantic angle an equal opportunity to surface
        relevant articles.

        :param queries: One or more search query strings.
        :returns: Tuple of (aggregated article results, is_fallback flag).
        """
        query_list = [queries] if isinstance(queries, str) else queries
        start = time.time()
        try:
            # Fetch enough FAISS chunks to cover all articles at max chunks each.
            # Vision documents have ~15 articles × MAX_CHUNKS_PER_ARTICLE chunks.
            candidate_pool = 15 * MAX_CHUNKS_PER_ARTICLE * len(query_list)
            base_results = await self._multi_query_search(query_list, candidate_pool)
            logger.info(
                f"FAISS search ({len(query_list)} quer{'y' if len(query_list) == 1 else 'ies'}) "
                f"completed in {time.time() - start:.2f}s ({len(base_results)} chunks)"
            )

            aggregated = self._aggregate_chunks(base_results)

            if aggregated:
                await self._enrich_from_database(aggregated)

            qualifying = {
                slug: data for slug, data in aggregated.items() if data["similarity_score"] >= MIN_SIMILARITY_SCORE
            }

            # If nothing passes the primary threshold (e.g. a rare coined term whose
            # embedding is sparse), retry with the fallback threshold so the model has
            # something to reason from rather than a silent empty response.
            is_fallback = False
            if not qualifying and aggregated:
                qualifying = {
                    slug: data
                    for slug, data in aggregated.items()
                    if data["similarity_score"] >= FALLBACK_SIMILARITY_SCORE
                }
                is_fallback = bool(qualifying)

            formatted_results = sorted(qualifying.values(), key=lambda x: x["similarity_score"], reverse=True)

            for result in formatted_results:
                # chunks are stored in descending FAISS score order; use only the
                # best-matching chunk so the preview is focused and clearly relevant.
                best_chunk = result["chunks"][0] if result["chunks"] else ""
                resolved = self._resolve_inline_references(best_chunk, result.get("references", []))
                result["content_preview"] = self._truncate_on_word_boundary(resolved, 800)
                result.pop("chunks", None)

            logger.info(f"Total search completed in {time.time() - start:.2f}s")
            return formatted_results, is_fallback

        except Exception as e:
            logger.error(f"Error searching Vision articles after {time.time() - start:.2f}s: {e}")
            return [], False

    def _aggregate_chunks(self, base_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Aggregate FAISS chunk results by article slug.

        Processes chunks in descending FAISS score order (as returned by the base
        search). Caps each article at ``MAX_CHUNKS_PER_ARTICLE`` chunks so that
        large articles with many chunks cannot monopolise the candidate pool and
        crowd out narrower but more relevant articles.

        :param base_results: Raw chunk-level search results, sorted by score desc.
        :returns: Dictionary of slug -> aggregated article data.
        """
        aggregated: dict[str, dict[str, Any]] = {}

        for result in base_results:
            meta = result["metadata"]
            slug = meta["slug"]
            vision_year = meta.get("vision_year", self.year)

            if slug not in aggregated:
                aggregated[slug] = {
                    "slug": slug,
                    "title": meta["title"],
                    "section": meta["section"],
                    "summary": "",
                    "vision_year": vision_year,
                    "is_draft": False,
                    "similarity_score": result["similarity_score"],
                    "chunks": [],
                    "url": f"/vision/{vision_year}/{slug}/",
                }
            else:
                aggregated[slug]["similarity_score"] = max(
                    aggregated[slug]["similarity_score"], result["similarity_score"]
                )

            if len(aggregated[slug]["chunks"]) < MAX_CHUNKS_PER_ARTICLE:
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
                q_obj |= Q(slug=article_data["slug"], section__vision__year=article_data["vision_year"])

            articles_qs = (
                VisionArticle.objects.filter(q_obj)
                .select_related("section__vision")
                .only(
                    "slug",
                    "section__vision__year",
                    "section__vision__is_draft",
                    "title",
                    "summary",
                    "ai_summary",
                    "content_tree",
                    "is_aggregate",
                )
            )

            async for article_obj in articles_qs:
                if article_obj.slug not in aggregated:
                    continue

                entry = aggregated[article_obj.slug]
                entry["url"] = await sync_to_async(article_obj.get_absolute_url)()
                entry["summary"] = await sync_to_async(article_obj.get_summary)()
                entry["is_draft"] = article_obj.section.vision.is_draft
                if article_obj.is_aggregate:
                    entry["similarity_score"] *= AGGREGATE_SCORE_PENALTY

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

            if not chunk_dicts:
                logger.warning(f"No chunks generated for vision article {article.pk}")
                return False

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
