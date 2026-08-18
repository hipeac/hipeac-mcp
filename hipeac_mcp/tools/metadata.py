"""MCP Tool for retrieving HiPEAC metadata.

Provides structured metadata used by other tools in the MCP server.
"""

from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from hipeac_mcp import mcp
from hipeac_mcp.db import ensure_connection_async
from hipeac_mcp.services.analytics import track_usage

from ..models import Metadata
from ..schemas.metadata import (
    MembershipType,
    MembershipTypeItem,
    MetadataItem,
    MetadataResponse,
    MetadataType,
)


async def fetch_metadata_items() -> dict[str, dict[int, MetadataItem]]:
    """Fetch all metadata rows fresh from the database, grouped by type.

    Shared by ``get_metadata`` and ``search_members`` so both always see the
    same, current data — no separate cache to fall out of sync.

    :returns: Mapping of metadata type key (e.g. ``"topic"``) to {item id: MetadataItem}.
    """
    await ensure_connection_async()

    result: dict[str, dict[int, MetadataItem]] = {}
    async for item in Metadata.objects.all().only("id", "type", "value"):
        key = item.type.strip()
        result.setdefault(key, {})[item.id] = MetadataItem(id=item.id, value=item.value)  # type: ignore
    return result


@mcp.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True))
@track_usage
async def get_metadata(ctx: Context = None) -> MetadataResponse:
    """Get available metadata as structured JSON.

    Returns all metadata categories including topics, application areas,
    institution types, and membership types. Used by other tools in the MCP server.

    :returns: Structured metadata with all categories
    """
    await ensure_connection_async()

    type_mapping = {
        MetadataType.TOPIC.value: "topics",
        MetadataType.APPLICATION_AREA.value: "application_areas",
        MetadataType.INSTITUTION_TYPE.value: "institution_types",
    }

    response_data = {key: [] for key in type_mapping.values()}

    async for item in (
        Metadata.objects.filter(type__in=type_mapping.keys())
        .order_by("type", "position", "value")
        .only("id", "value", "type")
    ):
        key = type_mapping.get(item.type.strip())
        if key:
            response_data[key].append(MetadataItem(id=item.id, value=item.value))  # type: ignore

    response_data["membership_types"] = [
        MembershipTypeItem(key=MembershipType.MEMBER, label="Full member (from EU)"),
        MembershipTypeItem(key=MembershipType.ASSOCIATED_MEMBER, label="Associated member (non-EU)"),
        MembershipTypeItem(key=MembershipType.AFFILIATED_MEMBER, label="Affiliated member"),
        MembershipTypeItem(key=MembershipType.AFFILIATED_PHD, label="Affiliated PhD student"),
    ]

    return MetadataResponse(**response_data)
