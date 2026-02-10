"""Tests for EventDocumentGenerator."""

from datetime import date

import pytest

from hipeac_mcp.models.events import ActivityUser, Event, EventInstitution, EventUser
from hipeac_mcp.services.rags.events.generator import MAX_CHUNK_CHARS, EventDocumentGenerator


@pytest.fixture
def generator():
    """Create an EventDocumentGenerator instance.

    :returns: Generator with default chunk size.
    """
    return EventDocumentGenerator()


def _make_event(event_type: str = Event.CONFERENCE) -> Event:
    """Build an Event without database access.

    :param event_type: Event type.
    :returns: Minimal Event instance.
    """
    event = Event.__new__(Event)
    event.type = event_type
    event.is_virtual = False
    event.slug = "test-event"
    event.start_date = date(2025, 1, 15)
    event.end_date = date(2025, 1, 20)
    event.city = "Brussels"
    event.country = "BE"
    event.description = "Test event"
    event.logistics = ""
    event.config = {}
    event.registration_start_date = date(2024, 10, 1)
    event.registration_early_deadline = None
    event.registration_deadline = None
    return event


def _make_user(user_id: int, first: str, last: str) -> EventUser:
    """Build an EventUser without database access.

    :param user_id: User PK.
    :param first: First name.
    :param last: Last name.
    :returns: Minimal EventUser instance.
    """
    user = EventUser.__new__(EventUser)
    user.id = user_id
    user.first_name = first
    user.last_name = last
    return user


def _make_institution(inst_id: int, name: str, colloquial: str = "") -> EventInstitution:
    """Build an EventInstitution without database access.

    :param inst_id: Institution PK.
    :param name: Full name.
    :param colloquial: Colloquial name.
    :returns: Minimal EventInstitution instance.
    """
    inst = EventInstitution.__new__(EventInstitution)
    inst.id = inst_id
    inst.name = name
    inst.colloquial_name = colloquial
    return inst


def _make_activity_user(
    user_id: int,
    object_id: int = 1,
    extra_data: dict | None = None,
    position: int = 0,
) -> ActivityUser:
    """Build an ActivityUser without database access.

    :param user_id: User PK.
    :param object_id: Activity PK.
    :param extra_data: Role data.
    :param position: Sort order.
    :returns: Minimal ActivityUser instance.
    """
    rel = ActivityUser.__new__(ActivityUser)
    rel.content_type_id = 39  # doesn't matter for unit tests — no DB queries
    rel.object_id = object_id
    rel.user_id = user_id
    rel.position = position
    rel.extra_data = extra_data or {}
    return rel


class TestClassifyPeople:
    """Tests for _classify_people role grouping."""

    def test_speaker_role(self, generator):
        """Users with is_speaker=True are grouped as speakers."""
        users = {1: _make_user(1, "Alice", "A")}
        rels = [_make_activity_user(1, extra_data={"is_speaker": True})]
        event = _make_event(Event.CONFERENCE)

        roles = generator._classify_people(rels, users, {}, event)

        assert "Speaker(s)" in roles
        assert roles["Speaker(s)"] == ["Alice A"]

    def test_main_speaker_role(self, generator):
        """Users with is_main_speaker=True are grouped separately."""
        users = {1: _make_user(1, "Bob", "B")}
        rels = [_make_activity_user(1, extra_data={"is_main_speaker": True})]
        event = _make_event(Event.CONFERENCE)

        roles = generator._classify_people(rels, users, {}, event)

        assert "Main speaker" in roles
        assert "Speaker(s)" not in roles

    def test_organizer_role(self, generator):
        """Users with only is_organizer=True are grouped as organizers."""
        users = {1: _make_user(1, "Carol", "C")}
        rels = [_make_activity_user(1, extra_data={"is_organizer": True})]
        event = _make_event(Event.CONFERENCE)

        roles = generator._classify_people(rels, users, {}, event)

        assert "Organizer(s)" in roles

    def test_acaces_teacher_fallback(self, generator):
        """ACACES users with empty extra_data are treated as teachers."""
        users = {1: _make_user(1, "Dan", "D")}
        rels = [_make_activity_user(1, extra_data={})]
        event = _make_event(Event.ACACES)

        roles = generator._classify_people(rels, users, {}, event)

        assert "Teacher(s)" in roles
        assert roles["Teacher(s)"] == ["Dan D"]

    def test_conference_empty_extra_data_ignored(self, generator):
        """Conference users with empty extra_data get no role."""
        users = {1: _make_user(1, "Eve", "E")}
        rels = [_make_activity_user(1, extra_data={})]
        event = _make_event(Event.CONFERENCE)

        roles = generator._classify_people(rels, users, {}, event)

        assert len(roles) == 0

    def test_missing_user_skipped(self, generator):
        """Relations for users not in cache are silently skipped."""
        rels = [_make_activity_user(999, extra_data={"is_speaker": True})]
        event = _make_event(Event.CONFERENCE)

        roles = generator._classify_people(rels, {}, {}, event)

        assert len(roles) == 0

    def test_multiple_roles_in_order(self, generator):
        """Multiple people with different roles produce separate groups."""
        users = {
            1: _make_user(1, "Alice", "A"),
            2: _make_user(2, "Bob", "B"),
        }
        rels = [
            _make_activity_user(1, extra_data={"is_speaker": True}),
            _make_activity_user(2, extra_data={"is_organizer": True}),
        ]
        event = _make_event(Event.CONFERENCE)

        roles = generator._classify_people(rels, users, {}, event)

        assert "Speaker(s)" in roles
        assert "Organizer(s)" in roles


class TestFormatPerson:
    """Tests for _format_person name formatting."""

    def test_name_only(self, generator):
        """Without institution mapping, returns plain name."""
        user = _make_user(1, "Alice", "Smith")
        assert generator._format_person(user, {}) == "Alice Smith"

    def test_name_with_institution(self, generator):
        """With institution mapping, appends institution in parentheses."""
        user = _make_user(1, "Alice", "Smith")
        inst = _make_institution(10, "KU Leuven", "KU Leuven")
        generator._user_institution_map = {1: 10}

        result = generator._format_person(user, {10: inst})

        assert result == "Alice Smith (KU Leuven)"

    def test_institution_id_not_in_cache(self, generator):
        """Falls back to name if institution not in cache."""
        user = _make_user(1, "Bob", "Jones")
        generator._user_institution_map = {1: 999}

        result = generator._format_person(user, {})

        assert result == "Bob Jones"


class TestResolveSpeakerTags:
    """Tests for _resolve_speaker_tags."""

    def test_replaces_known_speaker(self):
        """Known speaker IDs are replaced with names."""
        users = {42: _make_user(42, "John", "Doe")}
        text = "10:00 – Talk by [speaker:42] - 15 Mins"

        result = EventDocumentGenerator._resolve_speaker_tags(text, users)

        assert result == "10:00 – Talk by John Doe - 15 Mins"

    def test_preserves_unknown_speaker_tags(self):
        """Unknown speaker IDs are left as-is."""
        text = "10:00 – Talk by [speaker:999]"

        result = EventDocumentGenerator._resolve_speaker_tags(text, {})

        assert result == "10:00 – Talk by [speaker:999]"

    def test_replaces_multiple_tags(self):
        """Multiple speaker tags in one text are all resolved."""
        users = {
            1: _make_user(1, "Alice", "A"),
            2: _make_user(2, "Bob", "B"),
        }
        text = "[speaker:1] and [speaker:2] present"

        result = EventDocumentGenerator._resolve_speaker_tags(text, users)

        assert result == "Alice A and Bob B present"

    def test_no_tags_returns_unchanged(self):
        """Text without speaker tags is returned unchanged."""
        text = "Just a normal program line"

        result = EventDocumentGenerator._resolve_speaker_tags(text, {})

        assert result == text


class TestFormatRegistration:
    """Tests for _format_registration."""

    def test_includes_fees_from_config(self, generator):
        """Fees at top level of config are formatted."""
        event = _make_event()
        event.config = {"fee": 750, "fee_early": 650}

        result = generator._format_registration(event)

        assert "€750" in result
        assert "early: €650" in result

    def test_includes_student_fees(self, generator):
        """Student fees are shown separately."""
        event = _make_event()
        event.config = {"fee": 750, "fee_student": 550, "fee_student_early": 450}

        result = generator._format_registration(event)

        assert "Student fee" in result
        assert "€550" in result

    def test_empty_config_no_fees(self, generator):
        """Empty config produces no fee lines."""
        event = _make_event()
        event.config = {}

        result = generator._format_registration(event)

        assert "€" not in result


class TestFormatLogistics:
    """Tests for _format_logistics."""

    def test_returns_empty_for_no_logistics(self, generator):
        """Empty logistics returns empty string."""
        event = _make_event()
        event.logistics = ""

        assert generator._format_logistics(event) == ""

    def test_wraps_logistics_in_section(self, generator):
        """Non-empty logistics is wrapped in a Travel section."""
        event = _make_event()
        event.logistics = "Take bus 300 from airport."

        result = generator._format_logistics(event)

        assert "## Travel & Logistics" in result
        assert "bus 300" in result


class TestShouldIndexEvent:
    """Tests for should_index_event guard."""

    def test_matches_event_type(self, generator):
        """Returns True when event type matches filter."""
        event = _make_event(Event.CONFERENCE)
        assert generator.should_index_event(event, Event.CONFERENCE) is True

    def test_rejects_wrong_type(self, generator):
        """Returns False when event type does not match filter."""
        event = _make_event(Event.CONFERENCE)
        assert generator.should_index_event(event, Event.ACACES) is False

    def test_no_filter_accepts_all(self, generator):
        """Returns True when no type filter is given."""
        event = _make_event(Event.CSW)
        assert generator.should_index_event(event) is True


class TestCreateSectionAwareChunks:
    """Tests for _create_section_aware_chunks chunking logic."""

    def test_small_sections_stay_whole(self, generator):
        """Sections shorter than the limit produce one chunk each."""
        chunks = generator._create_section_aware_chunks(
            header="Header",
            sections=["Short section."],
            base_metadata={"event_id": 1},
            id_prefix="test",
        )

        assert len(chunks) == 1
        assert chunks[0]["content"] == "Header\n\nShort section."

    def test_empty_sections_fallback_to_header(self, generator):
        """When all sections are empty, a single header-only chunk is returned."""
        chunks = generator._create_section_aware_chunks(
            header="Header",
            sections=["", "  "],
            base_metadata={"event_id": 1},
            id_prefix="test",
        )

        assert len(chunks) == 1
        assert chunks[0]["content"] == "Header"

    def test_oversized_section_is_split(self, generator):
        """A section exceeding MAX_CHUNK_CHARS is split into multiple chunks."""
        header = "H"
        max_section = MAX_CHUNK_CHARS - len(header) - 2
        # Build a section with many sentences that exceeds the limit.
        sentence = "This is a test sentence. "
        big_section = sentence * (max_section // len(sentence) + 100)
        assert len(big_section) > max_section

        chunks = generator._create_section_aware_chunks(
            header=header,
            sections=[big_section],
            base_metadata={"event_id": 1},
            id_prefix="test",
        )

        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk["content"].startswith("H\n\n")
            # Each chunk's body should respect the limit.
            body = chunk["content"][len("H\n\n") :]
            assert len(body) <= max_section

    def test_chunk_ids_are_sequential(self, generator):
        """Chunk IDs are sequential across split sections."""
        header = "H"
        max_section = MAX_CHUNK_CHARS - len(header) - 2
        sentence = "Sentence here. "
        big_section = sentence * (max_section // len(sentence) + 100)

        chunks = generator._create_section_aware_chunks(
            header=header,
            sections=["Small section.", big_section],
            base_metadata={"event_id": 1},
            id_prefix="test",
        )

        for i, chunk in enumerate(chunks):
            assert chunk["id"] == f"test_chunk{i}"
            assert chunk["metadata"]["chunk_index"] == i


class TestSplitSection:
    """Tests for _split_section static method."""

    def test_short_text_returns_single(self):
        """Text within the limit is returned as-is."""
        result = EventDocumentGenerator._split_section("Short text.", 1000)

        assert result == ["Short text."]

    def test_splits_at_sentence_boundaries(self):
        """Splitting respects sentence-ending punctuation."""
        text = "First sentence. Second sentence. Third sentence."
        result = EventDocumentGenerator._split_section(text, 35)

        assert len(result) >= 2
        assert result[0].endswith(".")

    def test_hard_split_on_huge_sentence(self):
        """A single sentence longer than max_chars is hard-truncated."""
        text = "A" * 500
        result = EventDocumentGenerator._split_section(text, 200)

        assert len(result) == 3
        assert all(len(chunk) <= 200 for chunk in result)
