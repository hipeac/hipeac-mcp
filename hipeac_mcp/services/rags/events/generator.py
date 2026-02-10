"""Event document generator for RAG indexing.

Transforms Event database models into searchable synthetic documents.
Creates multiple documents: event overview + one per activity for granular search.
"""

import logging
import re
from typing import Any

from hipeac_mcp.db import ensure_connection_async
from hipeac_mcp.models.events import (
    Activity,
    ActivityUser,
    Event,
    EventInstitution,
    EventMetadata,
    EventUser,
    Place,
    RelatedInstitution,
    RelatedPlace,
    Room,
    activity_ct_id,
    event_ct_id,
    user_ct_id,
)


logger = logging.getLogger(__name__)

SPEAKER_TAG_RE = re.compile(r"\[speaker:(\d+)\]")
"""Regex to find ``[speaker:ID]`` tags in session program text."""

MAX_CHUNK_CHARS = 20_000
"""Safe character limit per chunk for ``text-embedding-3-small`` (8 192 tokens ≈ 28 k chars)."""


class EventDocumentGenerator:
    """Generates searchable synthetic documents from Event models.

     Creates multiple documents per event:
     - Event overview with schedule summary
    - One document per activity (keynote/course/workshop) with sessions
     Each document is chunked separately with specific metadata for linking.
    """

    def __init__(self):
        """Initialize the generator."""

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

        overview_header, overview_sections = await self._generate_overview_document(event)
        overview_chunks = self._create_section_aware_chunks(
            header=overview_header,
            sections=overview_sections,
            base_metadata={
                "event_id": event.id,
                "event_slug": event.slug,
                "event_name": event.name,
                "event_type": event.type,
                "event_year": event.year,
                "event_city": "Virtual" if event.is_virtual else event.city,
                "event_country": "" if event.is_virtual else event.country,
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

    def _create_section_aware_chunks(
        self,
        header: str,
        sections: list[str],
        base_metadata: dict[str, Any],
        id_prefix: str,
    ) -> list[dict[str, Any]]:
        """Create chunks from sections, prepending the header to each.

        Each section becomes one chunk when it fits within
        :data:`MAX_CHUNK_CHARS`. Oversized sections are split at sentence
        boundaries so that no chunk exceeds the embedding model's token
        limit while preserving as much semantic coherence as possible.

        :param header: Compact header (always prepended to every chunk).
        :param sections: List of section texts (description, schedule, etc.).
        :param base_metadata: Metadata for all chunks.
        :param id_prefix: Prefix for chunk IDs.
        :returns: List of chunk dictionaries.
        """
        chunks: list[dict[str, Any]] = []
        chunk_index = 0
        max_section_chars = MAX_CHUNK_CHARS - len(header) - 2  # account for "\n\n"

        for section in sections:
            section = section.strip()
            if not section:
                continue

            sub_sections = (
                self._split_section(section, max_section_chars) if len(section) > max_section_chars else [section]
            )

            for sub in sub_sections:
                content = f"{header}\n\n{sub}"
                metadata = {**base_metadata, "chunk_index": chunk_index}
                chunks.append({"id": f"{id_prefix}_chunk{chunk_index}", "content": content, "metadata": metadata})
                chunk_index += 1

        if not chunks:
            metadata = {**base_metadata, "chunk_index": 0}
            chunks.append({"id": f"{id_prefix}_chunk0", "content": header, "metadata": metadata})

        return chunks

    @staticmethod
    def _split_section(text: str, max_chars: int) -> list[str]:
        """Split a section into sub-chunks that fit within *max_chars*.

        Splits at sentence boundaries (`.` / `!` / `?` followed by a space)
        to preserve readability. Falls back to hard truncation only when a
        single sentence exceeds the limit.

        :param text: Section text to split.
        :param max_chars: Maximum character length per sub-chunk.
        :returns: List of sub-chunk strings.
        """
        if len(text) <= max_chars:
            return [text]

        sentences = re.split(r"(?<=[.!?]) +", text)
        sub_chunks: list[str] = []
        current = ""

        for sentence in sentences:
            if not current:
                current = sentence
            elif len(current) + 1 + len(sentence) <= max_chars:
                current += " " + sentence
            else:
                sub_chunks.append(current.strip())
                current = sentence

        if current:
            sub_chunks.append(current.strip())

        # Safety: hard-split any sub-chunk that still exceeds the limit
        # (single sentence longer than max_chars).
        final: list[str] = []
        for chunk in sub_chunks:
            while len(chunk) > max_chars:
                final.append(chunk[:max_chars])
                chunk = chunk[max_chars:]
            if chunk:
                final.append(chunk)

        return final

    async def _generate_overview_document(self, event: Event) -> tuple[str, list[str]]:
        """Generate event overview as a header + semantically meaningful sections.

        Produces 2–3 intentional chunks (never randomly split):

        1. **Description** — what the event is about (complete).
        2. **Practical information** — venue, logistics, registration, fees.
        3. **Schedule** — activity listing by type and date.

        :param event: Event model instance.
        :returns: Tuple of (header, sections) for section-aware chunking.
        """
        header_parts = [event.name]
        header_parts.append(f"Type: {event.type}")
        if event.is_virtual:
            header_parts.append("Location: Virtual (online)")
        elif event.city:
            location = event.city
            if event.country:
                location += f", {event.country}"
            header_parts.append(f"Location: {location}")
        header_parts.append(f"Dates: {event.start_date.strftime('%B %d')} - {event.end_date.strftime('%B %d, %Y')}")
        header = "\n".join(header_parts)

        sections = []

        if event.description:
            sections.append(f"Overview\n\n{event.description}")

        practical_parts = []
        venue_section = await self._format_venues(event)
        if venue_section:
            practical_parts.append(venue_section.strip())
        logistics_section = self._format_logistics(event)
        if logistics_section:
            practical_parts.append(logistics_section.strip())
        registration_section = self._format_registration(event)
        if registration_section:
            practical_parts.append(registration_section.strip())
        if practical_parts:
            sections.append("\n\n".join(practical_parts))

        schedule_summary = await self._format_schedule_summary(event)
        if schedule_summary:
            sections.append(schedule_summary.strip())

        return header, sections

    async def _generate_activity_documents(self, event: Event) -> list[dict[str, Any]]:
        """Generate one document per activity.

        :param event: Event model instance.
        :returns: List of chunks from all activity documents.
        """
        all_chunks = []

        activities = [activity async for activity in event.activities.prefetch_related("sessions").order_by("id")]

        if not activities:
            return []

        metadata_ids = {activity.type_id for activity in activities if activity.type_id}
        metadata_cache = await self._fetch_metadata(metadata_ids)

        activity_ids = [activity.id for activity in activities]
        activity_users = await self._fetch_activity_users(activity_ids)

        all_user_ids: set[int] = set()
        for user_list in activity_users.values():
            for rel in user_list:
                all_user_ids.add(rel.user_id)

        users_cache, institutions_cache = await self._fetch_users_and_institutions(all_user_ids)

        room_ids = {a.room_id for a in activities if a.room_id}
        rooms_cache = await self._fetch_rooms(room_ids)

        for activity in activities:
            rel_users = activity_users.get(activity.id, [])
            header, sections = await self._format_activity_document(
                activity,
                rel_users,
                metadata_cache,
                users_cache,
                institutions_cache,
                event,
                rooms_cache,
            )

            activity_type = metadata_cache.get(activity.type_id, "activity").lower()

            chunks = self._create_section_aware_chunks(
                header=header,
                sections=sections,
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

    async def _fetch_activity_users(
        self,
        activity_ids: list[int],
    ) -> dict[int, list[ActivityUser]]:
        """Fetch activity–user relations for a batch of activities.

        Queries ``hipeac_rel_users`` filtered by the Activity content type.

        :param activity_ids: Activity IDs to fetch relations for.
        :returns: Mapping of activity_id → list of ActivityUser rows.
        """
        result: dict[int, list[ActivityUser]] = {}
        if not activity_ids:
            return result

        qs = ActivityUser.objects.filter(
            content_type_id=activity_ct_id(),
            object_id__in=activity_ids,
        ).order_by("position")

        async for rel in qs:
            result.setdefault(rel.object_id, []).append(rel)

        return result

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
        self,
        user_ids: set[int],
    ) -> tuple[dict[int, EventUser], dict[int, EventInstitution]]:
        """Fetch users and their primary institutions.

        Institution lookup goes through ``hipeac_rel_institutions``
        (generic relation filtered by the User content type, ``position = 0``
        for the primary affiliation).

        :param user_ids: Set of user IDs to fetch.
        :returns: Tuple of (users_cache, institutions_cache).
        """
        users_cache: dict[int, EventUser] = {}
        if not user_ids:
            return users_cache, {}

        async for user in EventUser.objects.filter(id__in=user_ids):
            users_cache[user.id] = user

        user_institution_map: dict[int, int] = {}
        async for rel in RelatedInstitution.objects.filter(
            content_type_id=user_ct_id(),
            object_id__in=user_ids,
            position=0,
        ):
            user_institution_map[rel.object_id] = rel.institution_id

        institution_ids = set(user_institution_map.values())
        institutions_cache: dict[int, EventInstitution] = {}
        if institution_ids:
            async for inst in EventInstitution.objects.filter(id__in=institution_ids):
                institutions_cache[inst.id] = inst

        self._user_institution_map = user_institution_map
        return users_cache, institutions_cache

    async def _fetch_rooms(self, room_ids: set[int]) -> dict[int, Room]:
        """Fetch rooms with their parent places pre-loaded.

        :param room_ids: Set of room IDs to fetch.
        :returns: Mapping of room_id → Room (with ``place`` populated).
        """
        if not room_ids:
            return {}

        rooms_cache: dict[int, Room] = {}
        async for room in Room.objects.select_related("place").filter(id__in=room_ids):
            rooms_cache[room.id] = room

        return rooms_cache

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
        rel_users: list[ActivityUser],
        metadata_cache: dict[int, str],
        users_cache: dict[int, EventUser],
        institutions_cache: dict[int, EventInstitution],
        event: Event,
        rooms_cache: dict[int, Room] | None = None,
    ) -> tuple[str, list[str]]:
        """Format a complete document for a single activity.

        Returns a compact header (always prepended to every chunk) and a list
        of content sections that will become separate chunks. This ensures
        the LLM always sees core identity info regardless of which chunk matches.

        :param activity: Activity instance.
        :param rel_users: Pre-fetched user relations for this activity.
        :param metadata_cache: Metadata ID → value mapping.
        :param users_cache: User ID → EventUser mapping.
        :param institutions_cache: Institution ID → EventInstitution mapping.
        :param event: Parent event (used to determine role labels).
        :param rooms_cache: Room ID → Room mapping (with place pre-fetched).
        :returns: Tuple of (header string, list of section strings).
        """
        header_parts = []

        activity_type = metadata_cache.get(activity.type_id, "Activity")
        header_parts.append(f"{activity.title}\nType: {activity_type}")

        if activity.room_id and rooms_cache:
            room = rooms_cache.get(activity.room_id)
            if room:
                header_parts.append(f"Room: {room.name} — {room.place.name}")

        if activity.ai_summary:
            header_parts.append(f"Summary: {activity.ai_summary}")

        people_by_role = self._classify_people(rel_users, users_cache, institutions_cache, event)
        for role_label, people_strings in people_by_role.items():
            header_parts.append(f"{role_label}: {', '.join(people_strings)}")

        sessions = [session async for session in activity.sessions.all()]
        if sessions:
            for session in sessions:
                date_str = session.start_at.strftime("%B %d, %Y")
                time_str = session.start_at.strftime("%I:%M %p")
                end_time_str = session.end_at.strftime("%I:%M %p")
                session_label = f"Session: {session.title}" if session.title else "Session"
                header_parts.append(f"{session_label}\nWhen: {date_str}, {time_str} - {end_time_str}")

        header = "\n".join(header_parts)

        sections = []

        if activity.description:
            sections.append(f"Description\n\n{activity.description}")

        if sessions:
            for session in sessions:
                if session.program:
                    resolved = self._resolve_speaker_tags(session.program, users_cache)
                    title = session.title or "Program"
                    sections.append(f"{title}\n\n{resolved}")

        return header, sections

    def _classify_people(
        self,
        rel_users: list[ActivityUser],
        users_cache: dict[int, EventUser],
        institutions_cache: dict[int, EventInstitution],
        event: Event,
    ) -> dict[str, list[str]]:
        """Group activity users by role.

        For conferences, roles come from ``extra_data`` boolean flags.
        For ACACES, users with empty ``extra_data`` are treated as teachers.

        :param rel_users: Activity–user relations.
        :param users_cache: User ID → EventUser mapping.
        :param institutions_cache: Institution ID → EventInstitution mapping.
        :param event: Parent event for type-aware role inference.
        :returns: Ordered mapping of role_label → list of formatted name strings.
        """
        roles: dict[str, list[str]] = {}
        is_acaces = event.type == Event.ACACES

        for rel in rel_users:
            user = users_cache.get(rel.user_id)
            if not user:
                continue

            person_str = self._format_person(user, institutions_cache)
            extra = rel.extra_data or {}

            if extra.get("is_main_speaker"):
                roles.setdefault("Main speaker", []).append(person_str)
            elif extra.get("is_speaker"):
                roles.setdefault("Speaker(s)", []).append(person_str)
            elif extra.get("is_organizer"):
                roles.setdefault("Organizer(s)", []).append(person_str)
            elif is_acaces:
                roles.setdefault("Teacher(s)", []).append(person_str)

        return roles

    def _format_person(
        self,
        user: EventUser,
        institutions_cache: dict[int, EventInstitution],
    ) -> str:
        """Format a person's name with optional institution.

        :param user: EventUser instance.
        :param institutions_cache: Institution ID → EventInstitution mapping.
        :returns: ``"Name (Institution)"`` or just ``"Name"``.
        """
        institution_id = getattr(self, "_user_institution_map", {}).get(user.id)
        if institution_id and institution_id in institutions_cache:
            return f"{user.name} ({institutions_cache[institution_id]})"
        return user.name

    @staticmethod
    def _resolve_speaker_tags(
        text: str,
        users_cache: dict[int, EventUser],
    ) -> str:
        """Replace ``[speaker:ID]`` tags with actual speaker names.

        :param text: Program text that may contain speaker tags.
        :param users_cache: User ID → EventUser mapping.
        :returns: Text with tags replaced by names.
        """

        def _replace(match: re.Match) -> str:
            user_id = int(match.group(1))
            user = users_cache.get(user_id)
            return user.name if user else match.group(0)

        return SPEAKER_TAG_RE.sub(_replace, text)

    async def _format_venues(self, event: Event) -> str:
        """Format venue and location information.

        Events always have one primary venue. Some activities (social events,
        individual courses) may take place at a secondary venue.
        Virtual events have no physical venue.

        :param event: Event instance.
        :returns: Formatted venue section.
        """
        if event.is_virtual:
            return "## Venue & Location\n\nThis is a virtual event (online).\n\n"

        try:
            place_rels = [
                rel
                async for rel in RelatedPlace.objects.filter(
                    content_type_id=event_ct_id(),
                    object_id=event.id,
                ).order_by("-is_primary", "position")
            ]

            if not place_rels:
                return ""

            place_ids = [rel.place_id for rel in place_rels]
            places_by_id: dict[int, Place] = {}
            async for place in Place.objects.filter(id__in=place_ids):
                places_by_id[place.id] = place

            if not places_by_id:
                return ""

            primary_rel = next((r for r in place_rels if r.is_primary), place_rels[0])
            main_venue = places_by_id.get(primary_rel.place_id)
            if not main_venue:
                return ""

            parts = ["## Venue & Location\n\n"]
            parts.append(f"The main venue is {main_venue.name}")
            if main_venue.address:
                parts.append(f" ({main_venue.address})")
            if event.city:
                parts.append(f" in {event.city}")
                if event.country:
                    parts.append(f", {event.country}")
            parts.append(".\n\n")

            secondary = [
                places_by_id[r.place_id] for r in place_rels if not r.is_primary and r.place_id in places_by_id
            ]
            if secondary:
                parts.append("Some activities may take place at:\n\n")
                for place in secondary:
                    parts.append(f"- {place.name}")
                    if place.address:
                        parts.append(f" ({place.address})")
                    if place.city and place.city != event.city:
                        parts.append(f", {place.city}")
                    parts.append("\n")
                parts.append("\n")

            return "".join(parts)

        except Exception as e:
            logger.warning(f"Error formatting venues for event {event.slug}: {e}")
            return ""

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

        Fee keys are at the top level of ``event.config``
        (e.g. ``fee``, ``fee_early``, ``fee_student``, ``fee_student_early``).

        :param event: Event instance.
        :returns: Formatted registration section.
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
            fee = event.config.get("fee")
            fee_early = event.config.get("fee_early")
            fee_student = event.config.get("fee_student")
            fee_student_early = event.config.get("fee_student_early")

            fee_lines = []
            if fee:
                label = f"€{fee}"
                if fee_early:
                    label += f" (early: €{fee_early})"
                fee_lines.append(f"- Registration fee: {label}\n")
            if fee_student:
                label = f"€{fee_student}"
                if fee_student_early:
                    label += f" (early: €{fee_student_early})"
                fee_lines.append(f"- Student fee: {label}\n")

            if fee_lines:
                parts.append("\n")
                parts.extend(fee_lines)

        return "".join(parts)
