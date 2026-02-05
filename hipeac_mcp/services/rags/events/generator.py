"""Event document generator for RAG indexing.

Transforms Event database models into searchable synthetic documents.
Creates multiple documents: event overview + one per activity for granular search.
"""

import logging
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import Prefetch

from hipeac_mcp.db import ensure_connection_async
from hipeac_mcp.models.events import (
    Activity,
    ActivityUser,
    Event,
    EventInstitution,
    EventMetadata,
    EventUser,
    Place,
    RelatedPlace,
    Session,
)
from hipeac_mcp.services.document_processor import DocumentProcessor


logger = logging.getLogger(__name__)


class EventDocumentGenerator:
    """Generates searchable synthetic documents from Event models.

     Creates multiple documents per event:
     - Event overview with schedule summary
    - One document per activity (keynote/course/workshop) with sessions
     Each document is chunked separately with specific metadata for linking.
    """

    def __init__(self, chunk_size: int = 1500):
        """Initialize the generator.

        :param chunk_size: Target size for text chunks in characters
        """
        self.processor = DocumentProcessor()
        self.chunk_size = chunk_size

    async def generate_chunks(self, event: Event) -> list[dict[str, Any]]:
        """Generate searchable chunks from an event.

        Creates multiple documents:
        1. Event overview with schedule
        2. One document per activity with detailed information

        :param event: Event model instance
        :returns: List of chunk dictionaries with content and metadata
        """
        await ensure_connection_async()

        all_chunks = []

        overview_doc = await self._generate_overview_document(event)
        overview_chunks = self._create_chunks(
            content=overview_doc,
            base_metadata={
                "event_id": event.id,
                "event_slug": event.slug,
                "event_name": event.name,
                "event_type": event.type,
                "event_year": event.year,
                "event_city": event.city,
                "event_country": event.country,
                "event_url": event.get_absolute_url(),
                "document_type": "overview",
            },
            id_prefix=f"event_{event.year}_{event.slug}_overview",
        )
        all_chunks.extend(overview_chunks)

        activities_chunks = await self._generate_activity_documents(event)
        all_chunks.extend(activities_chunks)

        logger.debug(f"Generated {len(all_chunks)} total chunks for event '{event.slug}'")
        return all_chunks

    def _create_chunks(
        self,
        content: str,
        base_metadata: dict[str, Any],
        id_prefix: str,
    ) -> list[dict[str, Any]]:
        """Create chunks from content with metadata.

        :param content: Document content
        :param base_metadata: Metadata for all chunks
        :param id_prefix: Prefix for chunk IDs
        :returns: List of chunk dictionaries
        """
        return self.processor.prepare_chunks_for_embedding(
            content=content,
            base_metadata=base_metadata,
            id_prefix=id_prefix,
            chunk_size=self.chunk_size,
        )

    async def _generate_overview_document(self, event: Event) -> str:
        """Generate event overview document with schedule summary.

        :param event: Event model instance
        :returns: Markdown-formatted overview document
        """
        sections = []

        sections.append(f"# {event.name}\n")

        if event.description:
            sections.append(f"## Overview\n\n{event.description}\n")

        venue_section = await self._format_venues(event)
        if venue_section:
            sections.append(venue_section)

        schedule_summary = await self._format_schedule_summary(event)
        if schedule_summary:
            sections.append(schedule_summary)

        logistics_section = self._format_logistics(event)
        if logistics_section:
            sections.append(logistics_section)

        registration_section = self._format_registration(event)
        if registration_section:
            sections.append(registration_section)

        return "\n".join(sections)

    async def _generate_activity_documents(self, event: Event) -> list[dict[str, Any]]:
        """Generate one document per activity.

        :param event: Event model instance
        :returns: List of chunks from all activity documents
        """
        all_chunks = []

        activities_qs = (
            event.activities.select_related()
            .prefetch_related(
                Prefetch("sessions", queryset=Session.objects.all().order_by("start_at")),
                Prefetch("rel_users", queryset=ActivityUser.objects.all()),
            )
            .order_by("id")
        )

        activities = [activity async for activity in activities_qs]

        if not activities:
            return []

        metadata_ids = {activity.type_id for activity in activities if activity.type_id}
        metadata_cache = await self._fetch_metadata(metadata_ids)

        user_ids = set()
        for activity in activities:
            async for rel_user in activity.rel_users.all():
                user_ids.add(rel_user.user_id)

        users_cache, institutions_cache = await self._fetch_users_and_institutions(user_ids)

        for activity in activities:
            document = await self._format_activity_document(activity, metadata_cache, users_cache, institutions_cache)

            activity_type = metadata_cache.get(activity.type_id, "activity").lower()

            chunks = self._create_chunks(
                content=document,
                base_metadata={
                    "event_id": event.id,
                    "event_slug": event.slug,
                    "event_name": event.name,
                    "event_type": event.type,
                    "event_year": event.year,
                    "document_type": "activity",
                    "activity_id": activity.id,
                    "activity_slug": activity.slug,
                    "activity_type": activity_type,
                    "activity_url": activity.get_absolute_url(),
                },
                id_prefix=f"event_{event.year}_{event.slug}_activity_{activity.id}",
            )
            all_chunks.extend(chunks)

        return all_chunks

    async def _fetch_metadata(self, metadata_ids: set[int]) -> dict[int, str]:
        """Fetch activity type metadata.

        :param metadata_ids: Set of metadata IDs to fetch
        :returns: Dictionary mapping ID to value
        """
        metadata_cache = {}
        if metadata_ids:
            async for meta in EventMetadata.objects.filter(id__in=metadata_ids, type=EventMetadata.SESSION_TYPE):
                metadata_cache[meta.id] = meta.value
        return metadata_cache

    async def _fetch_users_and_institutions(
        self, user_ids: set[int]
    ) -> tuple[dict[int, EventUser], dict[int, EventInstitution]]:
        """Fetch users and their institutions.

        :param user_ids: Set of user IDs to fetch
        :returns: Tuple of (users_cache, institutions_cache)
        """
        users_cache = {}
        if user_ids:
            async for user in EventUser.objects.filter(id__in=user_ids).select_related():
                users_cache[user.id] = user

        institution_ids = {user.institution_id for user in users_cache.values() if user.institution_id}
        institutions_cache = {}
        if institution_ids:
            async for inst in EventInstitution.objects.filter(id__in=institution_ids):
                institutions_cache[inst.id] = inst

        return users_cache, institutions_cache

    def should_index_event(self, event: Event, event_type: str | None = None) -> bool:
        """Check if event should be indexed.

        :param event: Event to check
        :param event_type: Optional event type filter (acaces, conference, csw)
        :returns: True if event should be indexed
        """
        return not (event_type and event.type != event_type)

    async def _format_schedule_summary(self, event: Event) -> str:
        """Format high-level schedule summary for overview.

        :param event: Event instance
        :returns: Formatted schedule summary
        """
        try:
            activities_with_sessions = []
            async for activity in event.activities.prefetch_related("sessions").order_by("id"):
                sessions = [session async for session in activity.sessions.all()]
                if sessions:
                    activities_with_sessions.append((activity, sessions))

            if not activities_with_sessions:
                return ""

            parts = ["## Schedule\n\n"]

            metadata_ids = {a.type_id for a, _ in activities_with_sessions if a.type_id}
            metadata_cache = await self._fetch_metadata(metadata_ids)

            schedule_by_type = {}
            for activity, sessions in activities_with_sessions:
                activity_type = metadata_cache.get(activity.type_id, "Activity")
                if activity_type not in schedule_by_type:
                    schedule_by_type[activity_type] = []
                schedule_by_type[activity_type].append((activity, sessions))

            for activity_type, activities_list in schedule_by_type.items():
                parts.append(f"### {activity_type}s\n\n")
                for activity, sessions in activities_list:
                    if len(sessions) == 1:
                        session = sessions[0]
                        date_str = session.start_at.strftime("%B %d")
                        parts.append(f"- **{activity.title}** ({date_str})\n")
                    else:
                        parts.append(f"- **{activity.title}** ({len(sessions)} sessions)\n")
                parts.append("\n")

            return "".join(parts)

        except Exception as e:
            logger.warning(f"Error formatting schedule summary for event {event.slug}: {e}")
            return ""

    async def _format_activity_document(
        self,
        activity: Activity,
        metadata_cache: dict[int, str],
        users_cache: dict[int, EventUser],
        institutions_cache: dict[int, EventInstitution],
    ) -> str:
        """Format a complete document for a single activity.

        :param activity: Activity instance
        :param metadata_cache: Metadata cache
        :param users_cache: Users cache
        :param institutions_cache: Institutions cache
        :returns: Formatted activity document
        """
        parts = []

        activity_type = metadata_cache.get(activity.type_id, "Activity")
        parts.append(f"# {activity.title}\n\n")
        parts.append(f"**Type:** {activity_type}\n\n")

        speakers = []
        async for rel_user in activity.rel_users.all():
            if rel_user.extra_data and rel_user.extra_data.get("is_speaker"):
                user = users_cache.get(rel_user.user_id)
                if user:
                    speaker_str = user.name
                    if user.institution_id and user.institution_id in institutions_cache:
                        inst = institutions_cache[user.institution_id]
                        speaker_str += f" ({inst})"
                    speakers.append(speaker_str)

        if speakers:
            parts.append(f"**Speaker(s):** {', '.join(speakers)}\n\n")

        if activity.description:
            parts.append(f"## Description\n\n{activity.description}\n\n")

        sessions = [session async for session in activity.sessions.all()]
        if sessions:
            parts.append("## Schedule\n\n")
            for i, session in enumerate(sessions, 1):
                date_str = session.start_at.strftime("%B %d, %Y")
                time_str = session.start_at.strftime("%I:%M %p")
                end_time_str = session.end_at.strftime("%I:%M %p")

                if session.title:
                    parts.append(f"### Session {i}: {session.title}\n\n")
                else:
                    parts.append(f"### Session {i}\n\n")

                parts.append(f"**When:** {date_str}, {time_str} - {end_time_str}\n\n")

                if session.program:
                    parts.append(f"**Program:**\n{session.program}\n\n")

        elif activity.summary:
            parts.append(f"## Summary\n\n{activity.summary}\n\n")

        return "".join(parts)

    async def _format_venues(self, event: Event) -> str:
        """Format venue and location information.

        :param event: Event instance
        :returns: Formatted venue section
        """
        venue_parts = []

        try:
            event_ct = await ContentType.objects.aget(app_label="hipeac_mcp", model="event")
            place_rels = [
                rel
                async for rel in RelatedPlace.objects.filter(content_type_id=event_ct.id, object_id=event.id).order_by(
                    "-is_primary", "position"
                )
            ]

            if not place_rels:
                return ""

            place_ids = [rel.place_id for rel in place_rels]
            places = []
            async for place in Place.objects.filter(id__in=place_ids):
                places.append(place)

            if not places:
                return ""

            venue_parts.append("## Venue & Location\n\n")

            if len(places) == 1:
                place = places[0]
                venue_parts.append(f"The event takes place at {place.name}")
                if place.address:
                    venue_parts.append(f", located at {place.address}")
                if place.city and event.city:
                    venue_parts.append(f" in {event.city}")
                    if event.country:
                        venue_parts.append(f", {event.country}")
                venue_parts.append(".\n\n")
            else:
                venue_parts.append(f"The event takes place at multiple venues in {event.city}:\n\n")
                for place in places:
                    venue_parts.append(f"- {place.name}")
                    if place.address:
                        venue_parts.append(f" ({place.address})")
                    venue_parts.append("\n")
                venue_parts.append("\n")

        except Exception as e:
            logger.warning(f"Error formatting venues for event {event.slug}: {e}")

        return "".join(venue_parts)

    def _format_logistics(self, event: Event) -> str:
        """Format logistics information.

        :param event: Event instance
        :returns: Formatted logistics section
        """
        if not event.logistics:
            return ""

        return f"## Travel & Logistics\n\n{event.logistics}\n\n"

    def _format_registration(self, event: Event) -> str:
        """Format registration and deadline information.

        :param event: Event instance
        :returns: Formatted registration section
        """
        parts = ["## Registration & Deadlines\n\n"]

        if event.registration_start_date:
            parts.append(f"- Registration opens: {event.registration_start_date.strftime('%B %d, %Y')}\n")

        if event.registration_early_deadline:
            parts.append(
                f"- Early registration deadline: "
                f"{event.registration_early_deadline.strftime('%B %d, %Y at %I:%M %p')}\n"
            )

        if event.registration_deadline:
            parts.append(f"- Registration deadline: {event.registration_deadline.strftime('%B %d, %Y at %I:%M %p')}\n")

        if event.config:
            fees = event.config.get("fees", {})
            if fees and isinstance(fees, dict):
                fee = fees.get("fee")
                if fee:
                    parts.append(f"\nRegistration fee: €{fee}\n")

        return "".join(parts)
