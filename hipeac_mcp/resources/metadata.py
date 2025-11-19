"""MCP Resources for exposing HiPEAC metadata.

Resources allow AI agents to discover what topics, application areas,
and other metadata exist in the HiPEAC database before making tool calls.
"""

from hipeac_mcp import mcp

from ..models import Metadata


@mcp.resource("hipeac://metadata/application-areas")
def application_areas() -> str:
    """Application domains where HiPEAC research is applied.

    :returns: Formatted list of application areas with IDs.
    """
    areas = Metadata.objects.filter(type=Metadata.APPLICATION_AREA).order_by("position", "value").only("id", "value")

    lines = ["# Application Areas\n"]
    lines.append("These are the domains where HiPEAC research is applied.\n")
    lines.append("When searching for members, use the application area ID or name.\n")

    for area in areas:
        lines.append(f"- **{area.value}** (ID: {area.id})")  # type: ignore

    return "\n".join(lines)


@mcp.resource("hipeac://metadata/topics")
def topics() -> str:
    """Research topics used in the HiPEAC network for categorizing members.

    :returns: Formatted list of topics with IDs.
    """
    topics = Metadata.objects.filter(type=Metadata.TOPIC).order_by("position", "value").only("id", "value")

    lines = ["# Research Topics\n"]
    lines.append("These topics are used to categorize research interests of members, projects, and publications.\n")
    lines.append("When searching for members, use the topic ID or name.\n")

    for topic in topics:
        lines.append(f"- {topic.value} (ID: {topic.id})")  # type: ignore

    return "\n".join(lines)


@mcp.resource("hipeac://metadata/institution-types")
def institution_types() -> str:
    """Types of institutions in the HiPEAC network.

    :returns: Formatted list of institution types with IDs.
    """
    types = Metadata.objects.filter(type=Metadata.INSTITUTION_TYPE).order_by("position", "value").only("id", "value")

    lines = ["# Institution Types\n"]
    lines.append("Types of organizations in the HiPEAC network.\n")
    lines.append("When filtering members, use the institution type ID or name.\n")

    for inst_type in types:
        lines.append(f"- {inst_type.value} (ID: {inst_type.id})")  # type: ignore

    return "\n".join(lines)


@mcp.resource("hipeac://metadata/membership-types")
def membership_types() -> str:
    """Different membership levels in HiPEAC.

    :returns: Formatted text describing membership types.
    """
    lines = ["# Membership Types\n"]
    lines.append("Different levels of membership in the HiPEAC network:\n")
    lines.append("- `member`: Full member (from EU)")
    lines.append("- `associated_member`: Associated member (from non-EU countries)")
    lines.append("- `affiliated_member`: Affiliated member")
    lines.append("- `affiliated_phd`: Affiliated PhD student")

    return "\n".join(lines)
