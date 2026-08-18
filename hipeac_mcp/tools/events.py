"""MCP tools for searching HiPEAC events."""

from asgiref.sync import sync_to_async
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from hipeac_mcp import mcp
from hipeac_mcp.db import ensure_connection_async
from hipeac_mcp.models.events import Event
from hipeac_mcp.schemas.events import EventListResponse, EventSearchResponse, EventSummary
from hipeac_mcp.services.analytics import track_usage
from hipeac_mcp.services.rags import EventRagService


HIPEAC_BASE_URL = "https://www.hipeac.net"

_service_cache: dict[int, EventRagService] = {}


def _get_service(event_id: int) -> EventRagService:
    """Get a cached EventRagService for the given event ID.

    :param event_id: Event primary key.
    :returns: Cached service instance.
    """
    if event_id not in _service_cache:
        _service_cache[event_id] = EventRagService(event_id=event_id)
    return _service_cache[event_id]


@mcp.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True))
@track_usage
async def get_events(
    event_type: str | None = None,
    year: int | None = None,
    limit: int = 20,
    ctx: Context = None,
) -> EventListResponse:
    """Get available HiPEAC events (conferences and ACACES summer schools).

    Returns a list of events with their IDs, which can be used with the
    ``search_event`` tool for detailed searches. Only conferences and ACACES
    events are included (CSW events are legacy and excluded).

    :param event_type: Filter by event type: 'conference' or 'acaces'. Omit for both.
    :param year: Filter to events starting in this year. Omit for the most recent events.
    :param limit: Maximum number of events to return (default: 20, max: 50).
    :returns: Structured list of available events.
    """
    await ensure_connection_async()

    event_types = [event_type] if event_type else [Event.CONFERENCE, Event.ACACES]
    events_qs = Event.objects.filter(type__in=event_types)
    if year is not None:
        events_qs = events_qs.filter(start_date__year=year)
    events_qs = events_qs.order_by("-start_date")[: min(limit, 50)]

    events = []
    async for event in events_qs:
        events.append(
            EventSummary(
                id=event.id,
                name=event.name,
                type=event.type,
                is_virtual=event.is_virtual,
                city=event.city or "",
                country=event.country or "",
                start_date=event.start_date.isoformat(),
                end_date=event.end_date.isoformat(),
                url=f"{HIPEAC_BASE_URL}{event.get_absolute_url()}",
            )
        )

    return EventListResponse(total=len(events), events=events)


@mcp.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True))
@track_usage
async def search_event(
    query: str,
    queries: list[str] | None = None,
    event_id: int | None = None,
    limit: int = 5,
    ctx: Context = None,
) -> EventSearchResponse:
    """Search HiPEAC event activities using semantic search.

    Returns ranked activities with summaries, speakers/organizers, and content
    previews. Call ``get_events`` first to get a valid ``event_id``.

    This is direct embedding-based vector search with no LLM interpretation
    layer: rephrase the user's question into a concise, keyword-rich query
    (topic + activity type, e.g. "compiler optimization workshop"). For
    multi-faceted questions, pass up to 2 extra angle-specific variants via
    ``queries`` — all are searched in parallel and merged.

    :param query: Primary natural language question or topic to search for.
    :param queries: Up to 2 additional query variants for multi-angle search.
    :param event_id: Event ID to search (from ``get_events``). Defaults to latest conference.
    :param limit: Maximum number of results to return (default: 5, max: 10).
    :returns: Structured search results with ranked activities.
    """
    if event_id is None:
        await ensure_connection_async()
        latest = await sync_to_async(Event.objects.filter(type=Event.CONFERENCE).order_by("-start_date").first)()
        if latest is None:
            return EventSearchResponse(query=query, event_name="", event_id=0, total_results=0, results=[])
        event_id = latest.id

    all_queries = [query] + (queries[:2] if queries else [])
    service = _get_service(event_id)
    return await service.search_activities(all_queries, limit=limit)
