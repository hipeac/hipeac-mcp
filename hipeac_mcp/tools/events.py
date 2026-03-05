"""MCP tools for searching HiPEAC events."""

from asgiref.sync import sync_to_async
from mcp.server.fastmcp import Context
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
async def get_events(ctx: Context = None) -> EventListResponse:
    """Get available HiPEAC events (conferences and ACACES summer schools).

    Returns a list of events with their IDs, which can be used with the
    ``search_event`` tool for detailed searches. Only conferences and ACACES
    events are included (CSW events are legacy and excluded).

    :returns: Structured list of available events.
    """
    await ensure_connection_async()

    events_qs = Event.objects.filter(type__in=[Event.CONFERENCE, Event.ACACES]).order_by("-start_date")[:20]

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
    previews. The MCP client should synthesize insights from the returned data.

    **IMPORTANT**: Before using this tool, call ``get_events`` to retrieve valid
    event IDs. Pass the ``event_id`` for the event you want to search.

    **Query Optimization:**
    This tool performs direct embedding-based vector search — there is no LLM
    interpretation layer. You MUST rephrase the user's question into a concise,
    keyword-rich search query optimized for semantic similarity matching.
    Strip conversational framing and retain only the topic keywords, activity type,
    and any relevant context (e.g. speaker role, session format, logistics).

    **Use Cases:**
    - Finding sessions on a topic: topic keywords + activity type (workshop, tutorial…)
    - Speaker lookup: person name or role + topic domain
    - Schedule / logistics: session format keyword + time or venue term

    **Multi-Query Strategy:**
    For complex or multi-faceted questions, pass up to 2 extra query variants
    via ``queries`` to improve recall across different semantic angles.
    Each variant should probe a distinct dimension of the question (e.g. one targeting
    the technical topic, another targeting the application domain or event format).

    :param query: Primary natural language question or topic to search for.
    :param queries: Up to 2 additional query variants for multi-angle search.
    :param event_id: Event ID to search (from ``get_events``). Defaults to latest conference.
    :param limit: Maximum number of results to return (default: 5, max: 10).
    :returns: Structured search results with ranked activities.
    """
    if event_id is None:
        await ensure_connection_async()
        try:
            latest = await sync_to_async(Event.objects.filter(type=Event.CONFERENCE).order_by("-start_date").first)()
            if latest:
                event_id = latest.id
            else:
                return EventSearchResponse(query=query, event_name="", event_id=0, total_results=0, results=[])
        except Exception:
            return EventSearchResponse(query=query, event_name="", event_id=0, total_results=0, results=[])

    all_queries = [query] + (queries[:2] if queries else [])
    service = _get_service(event_id)
    return await service.search_activities(all_queries, limit=limit)
