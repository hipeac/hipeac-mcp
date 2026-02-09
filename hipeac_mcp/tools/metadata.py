"""MCP Tool for retrieving HiPEAC metadata.

Provides structured metadata used by other tools in the MCP server.
"""

from mcp.server.fastmcp import Context
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
