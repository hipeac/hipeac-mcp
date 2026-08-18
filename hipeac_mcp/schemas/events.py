"""Pydantic schemas for event tools."""

from pydantic import BaseModel, Field


class EventSummary(BaseModel):
    """Basic event information returned by list_events."""

    id: int = Field(..., description="Event ID, used as identifier for search_in_event")
    name: str = Field(..., description="Event name (e.g., 'HiPEAC 2026', 'ACACES 2025')")
    type: str = Field(..., description="Event type: 'conference' or 'acaces'")
    is_virtual: bool = Field(False, description="Whether the event was held online (no physical location)")
    city: str = Field("", description="Host city (empty for virtual events)")
    country: str = Field("", description="ISO country code (empty for virtual events)")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    url: str = Field(..., description="Event URL on hipeac.net")


class EventListResponse(BaseModel):
    """Response from list_events tool."""

    total: int = Field(..., description="Total number of events returned")
    events: list[EventSummary] = Field(..., description="List of events")


class EventPerson(BaseModel):
    """A person associated with an event activity."""

    id: int = Field(..., description="User ID")
    name: str = Field(..., description="Full name")
    institution: str = Field("", description="Primary institution name")
    role: str = Field(..., description="Role: 'speaker', 'main_speaker', 'organizer', or 'teacher'")


class EventActivityResult(BaseModel):
    """A single event activity search result."""

    activity_id: int = Field(..., description="Activity ID")
    title: str = Field(..., description="Activity title")
    activity_type: str = Field(..., description="Activity type (e.g., 'Workshop', 'Course', 'Keynote')")
    room: str = Field("", description="Room and venue (e.g., 'S2 (L0) — ICE Kraków')")
    summary: str = Field("", description="AI-generated activity summary")
    similarity_score: float = Field(..., description="Semantic similarity score (0-1)", ge=0, le=1)
    content_preview: str = Field(..., description="Preview of matching content")
    people: list[EventPerson] = Field(
        default_factory=list, description="Speakers, organizers, or teachers for this activity"
    )
    event_name: str = Field(..., description="Parent event name")
    event_id: int = Field(..., description="Parent event ID")
    event_year: int = Field(..., description="Event year")
    url: str = Field(..., description="Activity URL on hipeac.net")


class EventSearchResponse(BaseModel):
    """Response from search_in_event tool."""

    query: str = Field(..., description="The search query used")
    event_name: str = Field(..., description="Event name searched")
    event_id: int = Field(..., description="Event ID searched")
    total_results: int = Field(..., description="Total number of results found")
    results: list[EventActivityResult] = Field(..., description="Matching activities ranked by relevance")
