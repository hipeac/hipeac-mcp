"""Tests for Event model properties."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from hipeac_mcp.models.events import Event


def _make_event(event_type: str, month: int = 1) -> Event:
    """Build an Event instance without database access.

    :param event_type: Event type (acaces, conference, csw).
    :param month: Month for start_date.
    :returns: An Event with fields set directly.
    """
    event = Event.__new__(Event)
    event.type = event_type
    event.slug = "test-event"
    event.start_date = date(2025, month, 15)
    event.end_date = date(2025, month, 20)
    return event


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
