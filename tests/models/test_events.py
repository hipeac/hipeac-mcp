"""Tests for Event model properties."""

from datetime import date

from hipeac_mcp.models.events import (
    Activity,
    Event,
    EventInstitution,
    EventMetadata,
    EventUser,
    Place,
    Room,
    Session,
    activity_ct_id,
    event_ct_id,
    user_ct_id,
)


def _make_event(event_type: str, month: int = 1) -> Event:
    """Build an Event instance without database access.

    :param event_type: Event type (acaces, conference, csw).
    :param month: Month for start_date.
    :returns: An Event with fields set directly.
    """
    event = Event.__new__(Event)
    event.type = event_type
    event.is_virtual = False
    event.slug = "test-event"
    event.start_date = date(2025, month, 15)
    event.end_date = date(2025, month, 20)
    return event


class TestEventStr:
    """Tests for Event.__str__."""

    def test_str_delegates_to_name(self):
        """__str__ returns the computed name."""
        assert str(_make_event(Event.ACACES)) == "ACACES 2025"


class TestEventName:
    """Tests for Event.name property."""

    def test_acaces_name(self):
        """ACACES events are named 'ACACES YYYY'."""
        assert _make_event(Event.ACACES).name == "ACACES 2025"

    def test_conference_name(self):
        """Conference events are named 'HiPEAC YYYY'."""
        assert _make_event(Event.CONFERENCE).name == "HiPEAC 2025"

    def test_csw_spring_name(self):
        """CSW before June is labelled Spring."""
        assert _make_event(Event.CSW, month=3).name == "CSW Spring 2025"

    def test_csw_autumn_name(self):
        """CSW from June onwards is labelled Autumn."""
        assert _make_event(Event.CSW, month=10).name == "CSW Autumn 2025"

    def test_unknown_type_name(self):
        """Unknown type falls through to 'type YYYY'."""
        assert _make_event("workshop").name == "workshop 2025"


class TestEventYear:
    """Tests for Event.year property."""

    def test_returns_start_date_year(self):
        """Year is extracted from start_date."""
        assert _make_event(Event.CONFERENCE).year == 2025


class TestEventGetAbsoluteUrl:
    """Tests for Event.get_absolute_url."""

    def test_acaces_url(self):
        """ACACES URL uses year only."""
        assert _make_event(Event.ACACES).get_absolute_url() == "/acaces/2025/"

    def test_conference_url(self):
        """Conference URL includes year and slug."""
        assert _make_event(Event.CONFERENCE).get_absolute_url() == "/conference/2025/test-event/"

    def test_csw_url(self):
        """CSW URL includes year and slug."""
        assert _make_event(Event.CSW).get_absolute_url() == "/csw/2025/test-event/"

    def test_unknown_type_url(self):
        """Unknown type returns '#'."""
        assert _make_event("other").get_absolute_url() == "#"


class TestActivityGetAbsoluteUrl:
    """Tests for Activity.get_absolute_url."""

    def test_formats_url_with_id_and_slug(self):
        """URL uses activity ID and slug."""
        activity = Activity.__new__(Activity)
        activity.id = 8240
        activity.slug = "dasip-2026"
        assert activity.get_absolute_url() == "/activity/8240/dasip-2026/"


class TestEventUserName:
    """Tests for EventUser.name property."""

    def test_full_name(self):
        """Name combines first and last name."""
        user = EventUser.__new__(EventUser)
        user.first_name = "Alice"
        user.last_name = "Smith"
        assert user.name == "Alice Smith"

    def test_str_matches_name(self):
        """__str__ returns the same as name."""
        user = EventUser.__new__(EventUser)
        user.first_name = "Bob"
        user.last_name = "Jones"
        assert str(user) == "Bob Jones"


class TestEventInstitutionStr:
    """Tests for EventInstitution.__str__."""

    def test_uses_colloquial_name_when_set(self):
        """Prefers colloquial_name over full name."""
        inst = EventInstitution.__new__(EventInstitution)
        inst.name = "Katholieke Universiteit Leuven"
        inst.colloquial_name = "KU Leuven"
        assert str(inst) == "KU Leuven"

    def test_falls_back_to_name(self):
        """Uses full name when colloquial_name is empty."""
        inst = EventInstitution.__new__(EventInstitution)
        inst.name = "MIT"
        inst.colloquial_name = ""
        assert str(inst) == "MIT"


class TestContentTypeHelpers:
    """Tests for content type ID lookup helpers."""

    def test_activity_ct_id_calls_helper(self, monkeypatch):
        """activity_ct_id delegates to get_content_type_id."""
        monkeypatch.setattr("hipeac_mcp.models.events.get_content_type_id", lambda a, m: 39)
        assert activity_ct_id() == 39

    def test_event_ct_id_calls_helper(self, monkeypatch):
        """event_ct_id delegates to get_content_type_id."""
        monkeypatch.setattr("hipeac_mcp.models.events.get_content_type_id", lambda a, m: 18)
        assert event_ct_id() == 18

    def test_user_ct_id_calls_helper(self, monkeypatch):
        """user_ct_id delegates to get_content_type_id."""
        monkeypatch.setattr("hipeac_mcp.models.events.get_content_type_id", lambda a, m: 25)
        assert user_ct_id() == 25


class TestPlaceStr:
    """Tests for Place.__str__."""

    def test_str_returns_place_name(self):
        """__str__ returns the place name."""
        place = Place(name="ICE Kraków")
        assert str(place) == "ICE Kraków"


class TestRoomStr:
    """Tests for Room.__str__."""

    def test_str_returns_room_name(self):
        """__str__ returns the room name."""
        room = Room.__new__(Room)
        room.name = "Auditorium"
        assert str(room) == "Auditorium"


class TestActivityStr:
    """Tests for Activity.__str__."""

    def test_str_returns_title(self):
        """__str__ returns the activity title."""
        activity = Activity.__new__(Activity)
        activity.title = "RISC-V Tutorial"
        assert str(activity) == "RISC-V Tutorial"


class TestSessionStr:
    """Tests for Session.__str__."""

    def test_str_returns_title_when_set(self):
        """__str__ returns the session title when it is non-empty."""
        session = Session.__new__(Session)
        session.title = "Morning Session"
        session.id = 5
        assert str(session) == "Morning Session"

    def test_str_falls_back_to_session_id(self):
        """__str__ returns 'Session N' when title is empty."""
        session = Session.__new__(Session)
        session.title = ""
        session.id = 8
        assert str(session) == "Session 8"


class TestEventMetadataStr:
    """Tests for EventMetadata.__str__."""

    def test_str_returns_value(self):
        """__str__ returns the metadata value."""
        metadata = EventMetadata.__new__(EventMetadata)
        metadata.value = "Workshop"
        assert str(metadata) == "Workshop"


class TestDbTableNames:
    """Tests that models point to the correct database tables."""

    def test_event_table(self):
        """Event maps to hipeac_event."""
        assert Event._meta.db_table == "hipeac_event"

    def test_event_user_table(self):
        """EventUser maps to hipeac_user, not auth_user."""
        assert EventUser._meta.db_table == "hipeac_user"

    def test_institution_table(self):
        """EventInstitution maps to hipeac_institution."""
        assert EventInstitution._meta.db_table == "hipeac_institution"

    def test_activity_table(self):
        """Activity maps to hipeac_event_activity."""
        assert Activity._meta.db_table == "hipeac_event_activity"
