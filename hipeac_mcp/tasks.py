"""Background tasks using pure Huey with Redis.

Provides a periodic task that checks for Vision reindex signals pushed
by hipeac-redux and triggers FAISS reindexing when needed.
"""

import asyncio
import json
import logging
import os

from asgiref.sync import sync_to_async
from huey import RedisHuey, crontab  # type: ignore[import-untyped]

from .db import ensure_connection_async, setup_django
from .models.vision import VisionArticle
from .redis import get_redis_client
from .services.rags import VisionRagService


setup_django()

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
REINDEX_KEY = "hipeac:mcp:reindex:vision"

huey = RedisHuey("hipeac-mcp", url=f"{REDIS_URL}/0")


@huey.periodic_task(crontab(minute="*/5"))
def check_reindex_signals() -> dict[str, list[int]]:
    """Check Redis for Vision reindex signals and trigger reindexing.

    Signals are pushed by hipeac-redux when VisionArticle content changes.
    Each signal is a JSON object with a ``year`` field indicating which
    Vision year needs reindexing.

    :returns: Dictionary with lists of reindexed and failed years.
    """
    client = get_redis_client()

    if client is None:
        return {"reindexed": [], "failed": []}

    years_to_reindex: set[int] = set()

    while True:
        raw: str | None = client.lpop(REINDEX_KEY)  # type: ignore[no-untyped-call]
        if raw is None:
            break
        try:
            signal = json.loads(raw)
            years_to_reindex.add(int(signal["year"]))
        except json.JSONDecodeError, KeyError, ValueError:
            logger.warning(f"Invalid reindex signal: {raw}")

    if not years_to_reindex:
        return {"reindexed": [], "failed": []}

    logger.info(f"Reindex signals received for years: {years_to_reindex}")

    reindexed: list[int] = []
    failed: list[int] = []

    for year in sorted(years_to_reindex):
        try:
            asyncio.run(_reindex_year(year))
            reindexed.append(year)
        except Exception:
            logger.exception(f"Failed to reindex Vision {year}")
            failed.append(year)

    return {"reindexed": reindexed, "failed": failed}


async def _reindex_year(year: int) -> None:
    """Reindex all Vision articles for a given year.

    Fetches articles from the database, generates embeddings via OpenAI,
    and rebuilds the FAISS index.

    :param year: Vision year to reindex.
    """
    await ensure_connection_async()

    service = VisionRagService(year=year)
    service.reset_index()

    queryset = VisionArticle.objects.filter(section__vision__year=year).select_related("section__vision")
    total = await sync_to_async(queryset.count)()
    logger.info(f"Reindexing {total} articles for Vision {year}")

    indexed = 0

    async for article in queryset:
        try:
            await service.index_article(article)
            indexed += 1
        except Exception:
            logger.exception(f"Failed to index article {article.slug}")

    logger.info(f"Vision {year} reindex complete: {indexed}/{total} articles indexed")
