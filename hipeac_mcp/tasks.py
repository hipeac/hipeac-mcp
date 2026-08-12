"""Background tasks using pure Huey with Redis.

Provides periodic tasks that check for reindex signals pushed
by hipeac-redux and trigger FAISS reindexing when needed.
"""

import asyncio
import json
import logging
import os

from asgiref.sync import sync_to_async
from huey import RedisHuey, crontab  # type: ignore[import-untyped]

from .db import ensure_connection_async, setup_django
from .models.events import Event
from .models.vision import VisionArticle
from .redis import get_redis_client
from .services.rags import EventRagService, VisionRagService


setup_django()

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
VISION_REINDEX_KEY = "hipeac:mcp:reindex:vision"
EVENT_REINDEX_KEY = "hipeac:mcp:reindex:event"

huey = RedisHuey("hipeac-mcp", url=f"{REDIS_URL}/0")


def _drain_redis_list(key: str) -> set[int]:
    """Drain a Redis list and return unique integer IDs.

    :param key: Redis list key to drain.
    :returns: Set of unique integer IDs from the JSON signals.
    """
    client = get_redis_client()

    if client is None:
        return set()

    ids: set[int] = set()

    while True:
        raw: str | None = client.lpop(key)  # type: ignore[no-untyped-call]
        if raw is None:
            break
        try:
            signal = json.loads(raw)
            value = signal.get("year") or signal.get("event_id")
            if value is not None:
                ids.add(int(value))
        except json.JSONDecodeError, KeyError, ValueError:
            logger.warning(f"Invalid reindex signal from {key}: {raw}")

    return ids


@huey.periodic_task(crontab(minute="*/5"))
def check_reindex_signals() -> dict[str, list[int]]:
    """Check Redis for reindex signals and trigger reindexing.

    Signals are pushed by hipeac-redux when content changes or when
    an admin triggers a manual reindex. Handles both Vision years
    and Event IDs.

    :returns: Dictionary with lists of reindexed and failed IDs.
    """
    reindexed: list[int] = []
    failed: list[int] = []

    vision_years = _drain_redis_list(VISION_REINDEX_KEY)

    if vision_years:
        logger.info(f"Vision reindex signals received for years: {vision_years}")
        for year in sorted(vision_years):
            try:
                asyncio.run(_reindex_vision_year(year))
                reindexed.append(year)
            except Exception:
                logger.exception(f"Failed to reindex Vision {year}")
                failed.append(year)

    event_ids = _drain_redis_list(EVENT_REINDEX_KEY)

    if event_ids:
        logger.info(f"Event reindex signals received for IDs: {event_ids}")
        for event_id in sorted(event_ids):
            try:
                asyncio.run(_reindex_event(event_id))
                reindexed.append(event_id)
            except Exception:
                logger.exception(f"Failed to reindex event {event_id}")
                failed.append(event_id)

    return {"reindexed": reindexed, "failed": failed}


async def _reindex_vision_year(year: int) -> None:
    """Reindex all Vision articles for a given year.

    Fetches articles from the database, generates embeddings via OpenAI,
    and rebuilds the FAISS index.

    Aborts before resetting the existing index if the embedding provider
    is unavailable (e.g. OpenAI quota exhausted), preserving the last good
    index for search.

    :param year: Vision year to reindex.
    """
    await ensure_connection_async()

    service = VisionRagService(year=year)

    if not await service.health_check():
        raise RuntimeError(
            f"Aborted reindex for Vision {year}: embedding provider is unavailable "
            f"(check OpenAI quota/billing). Existing index preserved."
        )

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


async def _reindex_event(event_id: int) -> None:
    """Reindex all activities for a given event.

    Fetches the event from the database, generates documents and embeddings,
    and rebuilds the FAISS index.

    Aborts before resetting the existing index if the embedding provider
    is unavailable (e.g. OpenAI quota exhausted), preserving the last good
    index for search.

    :param event_id: Event primary key to reindex.
    """
    await ensure_connection_async()

    event = await sync_to_async(Event.objects.get)(id=event_id)
    service = EventRagService(event_id=event_id)

    if not await service.health_check():
        raise RuntimeError(
            f"Aborted reindex for event {event_id} ({event.name}): embedding provider "
            f"is unavailable (check OpenAI quota/billing). Existing index preserved."
        )

    service.reset_index()

    logger.info(f"Reindexing event {event_id} ({event.name})")
    success = await service.index_event(event)

    if success:
        logger.info(f"Event {event_id} reindex complete")
    else:
        raise RuntimeError(f"Event {event_id} reindex failed")
