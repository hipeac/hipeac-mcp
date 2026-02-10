"""Event RAG service for HiPEAC event search."""

import logging
import time
from typing import Any

from hipeac_mcp.db import ensure_connection_async
from hipeac_mcp.models.events import (
    Activity,
    ActivityUser,
    Event,
    EventInstitution,
    EventUser,
    RelatedInstitution,
    Room,
    activity_ct_id,
    user_ct_id,
)
from hipeac_mcp.schemas.events import EventActivityResult, EventPerson, EventSearchResponse
from hipeac_mcp.services.rags.base import BaseRagService

from .generator import EventDocumentGenerator


logger = logging.getLogger(__name__)

HIPEAC_BASE_URL = "https://www.hipeac.net"


class EventRagService(BaseRagService):
    """RAG service for HiPEAC event data.

    Each event gets its own FAISS index (e.g., ``event_6816``).
    Returns structured ``EventSearchResponse`` — no LLM post-processing,
    so the MCP client synthesizes its own answer from the raw data.
    """

    COLLECTION_DESCRIPTION = "HiPEAC event activities for semantic search"

    def __init__(self, event_id: int):
        """Initialize the Event RAG service for a specific event.

        :param event_id: Primary key of the event to search.
        """
        self.event_id = event_id
        self.COLLECTION_NAME = f"event_{event_id}"
        super().__init__()
        self.generator = EventDocumentGenerator()

    async def search_activities(self, query: str, limit: int = 5) -> EventSearchResponse:
        """Search event activities and return a structured response.

        Performs FAISS search, aggregates chunks by activity, enriches
        with DB metadata (people, summary), and returns an ``EventSearchResponse``.

        :param query: Natural language search query.
        :param limit: Maximum number of results to return (max: 10).
        :returns: Structured search response with ranked activities.
        """
        actual_limit = min(limit, 10)
        results = await self.search(query, actual_limit)

        event_name = ""
        event_id = self.event_id
        if results:
            event_name = results[0].get("event_name", "")

        return EventSearchResponse(
            query=query,
            event_name=event_name,
            event_id=event_id,
            total_results=len(results),
            results=[
                EventActivityResult(
                    activity_id=r["activity_id"],
                    title=r["title"],
                    activity_type=r["activity_type"],
                    room=r.get("room", ""),
                    summary=r.get("summary", ""),
                    similarity_score=r["similarity_score"],
                    content_preview=r["content_preview"],
                    people=[
                        EventPerson(id=p["id"], name=p["name"], institution=p.get("institution", ""), role=p["role"])
                        for p in r.get("people", [])
                    ],
                    event_name=r.get("event_name", ""),
                    event_id=r.get("event_id", event_id),
                    event_year=r.get("event_year", 0),
                    url=f"{HIPEAC_BASE_URL}{r['url']}",
                )
                for r in results
            ],
        )

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search for event chunks and aggregate by activity.

        :param query: Search query string.
        :param limit: Maximum number of activities to retrieve.
        :returns: List of aggregated activity results.
        """
        start = time.time()
        try:
            base_results = await super().search(query, limit * 3)
            logger.info(f"FAISS search completed in {time.time() - start:.2f}s ({len(base_results)} chunks)")

            aggregated = self._aggregate_chunks(base_results)

            if aggregated:
                await self._enrich_from_database(aggregated)

            formatted_results = sorted(aggregated.values(), key=lambda x: x["similarity_score"], reverse=True)[:limit]

            for result in formatted_results:
                full_text = " ".join(result["chunks"][:2])
                result["content_preview"] = full_text[:800].rsplit(" ", 1)[0] if len(full_text) > 800 else full_text
                result.pop("chunks", None)

            logger.info(f"Total search completed in {time.time() - start:.2f}s")
            return formatted_results

        except Exception as e:
            logger.error(f"Error searching event activities after {time.time() - start:.2f}s: {e}")
            return []

    def _aggregate_chunks(self, base_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Aggregate FAISS chunk results by activity or overview.

        :param base_results: Raw chunk-level search results.
        :returns: Dictionary of key → aggregated result data.
        """
        aggregated: dict[str, dict[str, Any]] = {}

        for result in base_results:
            meta = result["metadata"]
            doc_type = meta.get("document_type", "activity")

            if doc_type == "overview":
                key = "overview"
                if key not in aggregated:
                    aggregated[key] = {
                        "activity_id": 0,
                        "title": f"{meta.get('event_name', '')} Overview",
                        "activity_type": "Overview",
                        "event_name": meta.get("event_name", ""),
                        "event_id": meta.get("event_id", self.event_id),
                        "event_year": meta.get("event_year", 0),
                        "url": meta.get("event_url", ""),
                        "similarity_score": result["similarity_score"],
                        "chunks": [],
                    }
                else:
                    aggregated[key]["similarity_score"] = max(
                        aggregated[key]["similarity_score"], result["similarity_score"]
                    )
            else:
                activity_id = meta.get("activity_id", 0)
                key = str(activity_id)
                if key not in aggregated:
                    aggregated[key] = {
                        "activity_id": activity_id,
                        "title": "",
                        "activity_type": meta.get("activity_type", "activity").title(),
                        "event_name": meta.get("event_name", ""),
                        "event_id": meta.get("event_id", self.event_id),
                        "event_year": meta.get("event_year", 0),
                        "url": meta.get("activity_url", ""),
                        "similarity_score": result["similarity_score"],
                        "chunks": [],
                    }
                else:
                    aggregated[key]["similarity_score"] = max(
                        aggregated[key]["similarity_score"], result["similarity_score"]
                    )

            aggregated[key]["chunks"].append(result["content"])

        return aggregated

    async def _enrich_from_database(self, aggregated: dict[str, dict[str, Any]]) -> None:
        """Enrich aggregated results with activity details and people from the database.

        :param aggregated: Mutable dictionary of key → activity data.
        """
        db_start = time.time()
        try:
            await ensure_connection_async()

            activity_ids = [v["activity_id"] for v in aggregated.values() if v["activity_id"]]

            if not activity_ids:
                return

            activities: dict[int, Activity] = {}
            async for activity in Activity.objects.filter(id__in=activity_ids):
                activities[activity.id] = activity

            for _key, entry in aggregated.items():
                aid = entry["activity_id"]
                if aid and aid in activities:
                    activity = activities[aid]
                    entry["title"] = activity.title
                    entry["summary"] = activity.ai_summary or activity.summary or ""

            room_ids = {a.room_id for a in activities.values() if a.room_id}
            rooms: dict[int, Room] = {}

            if room_ids:
                async for room in Room.objects.select_related("place").filter(id__in=room_ids):
                    rooms[room.id] = room

            for _key, entry in aggregated.items():
                aid = entry["activity_id"]
                if aid and aid in activities:
                    activity = activities[aid]
                    if activity.room_id and activity.room_id in rooms:
                        room = rooms[activity.room_id]
                        entry["room"] = f"{room.name} \u2014 {room.place.name}"

            all_user_ids: set[int] = set()
            activity_user_rels: dict[int, list[ActivityUser]] = {}
            async for rel in ActivityUser.objects.filter(
                content_type_id=activity_ct_id(),
                object_id__in=activity_ids,
            ).order_by("position"):
                activity_user_rels.setdefault(rel.object_id, []).append(rel)
                all_user_ids.add(rel.user_id)

            if not all_user_ids:
                return

            users: dict[int, EventUser] = {}
            async for user in EventUser.objects.filter(id__in=all_user_ids):
                users[user.id] = user

            user_institution_map: dict[int, int] = {}
            async for rel in RelatedInstitution.objects.filter(
                content_type_id=user_ct_id(),
                object_id__in=all_user_ids,
                position=0,
            ):
                user_institution_map[rel.object_id] = rel.institution_id

            institution_ids = set(user_institution_map.values())
            institutions: dict[int, EventInstitution] = {}
            if institution_ids:
                async for inst in EventInstitution.objects.filter(id__in=institution_ids):
                    institutions[inst.id] = inst

            event_type = aggregated.get("overview", {}).get("event_name", "")
            is_acaces = "ACACES" in event_type

            for _key, entry in aggregated.items():
                aid = entry["activity_id"]
                if not aid:
                    continue

                rels = activity_user_rels.get(aid, [])
                people = []
                for rel in rels:
                    user = users.get(rel.user_id)
                    if not user:
                        continue

                    extra = rel.extra_data or {}
                    if extra.get("is_main_speaker"):
                        role = "main_speaker"
                    elif extra.get("is_speaker"):
                        role = "speaker"
                    elif extra.get("is_organizer"):
                        role = "organizer"
                    elif is_acaces:
                        role = "teacher"
                    else:
                        continue

                    inst_id = user_institution_map.get(user.id)
                    inst_name = str(institutions[inst_id]) if inst_id and inst_id in institutions else ""

                    people.append({"id": user.id, "name": user.name, "institution": inst_name, "role": role})

                entry["people"] = people

            logger.info(f"DB enrichment completed in {time.time() - db_start:.2f}s")

        except Exception as e:
            logger.warning(f"Failed to enrich event activities from DB: {e}")

    async def index_event(self, event: Event) -> bool:
        """Index all activities for an event into the vector store.

        :param event: Event model instance to index.
        :returns: True if successful, False otherwise.
        """
        try:
            chunk_dicts = await self.generator.generate_chunks(event)

            if not chunk_dicts:
                logger.warning(f"No chunks generated for event {event.id}")
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
                logger.info(f"Indexed {len(chunk_dicts)} chunks for event {event.id} ({event.name})")
            return success

        except Exception as e:
            logger.error(f"Error indexing event {event.id}: {e}")
            return False
