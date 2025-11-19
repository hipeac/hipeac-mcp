"""MCP Tools for searching and analyzing HiPEAC members.

These tools provide intelligent search and discovery of network members
based on research interests, location, and institutional affiliation.
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from mcp.types import ToolAnnotations
from pydantic import HttpUrl

from hipeac_mcp import mcp

from ..models import RelApplicationArea, RelInstitution, RelTopic, User
from ..schemas.members import Institution, Member, MemberSearchResponse
from ..schemas.metadata import MembershipType, MetadataItem


# Cache for metadata to avoid repeated queries
_metadata_cache: dict[str, dict[int, MetadataItem]] = {}


async def _ensure_metadata_cache():
    """Ensure metadata cache is populated."""
    if _metadata_cache:
        return

    from ..models import Metadata

    # Load all metadata into cache
    async for item in Metadata.objects.all().only("id", "type", "value"):
        cache_key = item.type.strip()
        if cache_key not in _metadata_cache:
            _metadata_cache[cache_key] = {}
        _metadata_cache[cache_key][item.id] = MetadataItem(id=item.id, value=item.value)  # type: ignore


def _get_metadata_item(type_key: str, item_id: int) -> MetadataItem | None:
    """Get a metadata item from cache."""
    return _metadata_cache.get(type_key, {}).get(item_id)


@mcp.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True))
async def search_members(
    query: str | None = None,
    topic_ids: list[int] | None = None,
    application_area_ids: list[int] | None = None,
    countries: list[str] | None = None,
    institution_type_ids: list[int] | None = None,
    membership_types: list[MembershipType] | None = None,
    limit: int = 20,
) -> MemberSearchResponse:
    """Search HiPEAC network members by research interests, location, and institution.

    Returns detailed member profiles including current affiliation, research topics,
    and contact information.

    **IMPORTANT**: Before using this tool, call `get_metadata` to retrieve valid IDs
    for topics, application_areas, and institution_types. The metadata tool returns
    structured data with all available options and their corresponding IDs.

    :param query: Text search in member names, emails, or institutions.
    :param topic_ids: Filter by research topic IDs (get from get_metadata tool).
    :param application_area_ids: Filter by application area IDs (get from get_metadata tool).
    :param countries: Filter by ISO country codes (e.g., ['BE', 'ES', 'DE']).
    :param institution_type_ids: Filter by institution type IDs (get from get_metadata tool).
    :param membership_types: Filter by membership type keys: 'member', 'associated_member',
        'affiliated_member', 'affiliated_phd' (get from get_metadata tool).
    :param limit: Maximum number of results to return (max: 100).
    :returns: Structured search results with member profiles.
    """
    user_ct = await ContentType.objects.aget(app_label="hipeac", model="user")
    queryset = User.objects.filter(memberships__end_date__isnull=True).distinct()

    if query:
        queryset = queryset.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(username__icontains=query)
        )

    if topic_ids:
        topic_user_ids = [
            id
            async for id in RelTopic.objects.filter(content_type=user_ct, topic_id__in=topic_ids).values_list(
                "object_id", flat=True
            )
        ]
        if topic_user_ids:
            queryset = queryset.filter(id__in=topic_user_ids)

    if application_area_ids:
        area_user_ids = [
            id
            async for id in RelApplicationArea.objects.filter(
                content_type=user_ct, application_area_id__in=application_area_ids
            ).values_list("object_id", flat=True)
        ]
        if area_user_ids:
            queryset = queryset.filter(id__in=area_user_ids)

    if countries:
        country_user_ids = [
            id
            async for id in RelInstitution.objects.filter(
                content_type=user_ct, institution__country__in=[c.upper() for c in countries]
            ).values_list("object_id", flat=True)
        ]
        if country_user_ids:
            queryset = queryset.filter(id__in=country_user_ids)

    if institution_type_ids:
        type_user_ids = [
            id
            async for id in RelInstitution.objects.filter(
                content_type=user_ct, institution__type_id__in=institution_type_ids
            ).values_list("object_id", flat=True)
        ]
        if type_user_ids:
            queryset = queryset.filter(id__in=type_user_ids)

    if membership_types:
        queryset = queryset.filter(memberships__type__in=membership_types)

    actual_limit = min(limit, 100)
    members = [m async for m in queryset.select_related().prefetch_related("memberships")[:actual_limit]]

    if not members:
        return MemberSearchResponse(total=0, limit=actual_limit, members=[])

    # Ensure metadata cache is populated
    await _ensure_metadata_cache()

    # Build structured member profiles
    member_profiles = []

    for user in members:
        # Fetch institutions
        rel_institutions = [
            rel
            async for rel in RelInstitution.objects.filter(
                content_type=user_ct,
                object_id=user.id,  # type: ignore
            ).select_related("institution")
        ]
        institutions = [
            Institution(
                name=rel.institution.name,
                country=rel.institution.country,
                type=(
                    _get_metadata_item("institution_type", rel.institution.type_id)  # type: ignore
                    if hasattr(rel.institution, "type_id") and rel.institution.type_id  # type: ignore
                    else None
                ),
            )
            for rel in rel_institutions
        ]

        # Fetch topics with metadata
        rel_topics = [
            rel
            async for rel in RelTopic.objects.filter(content_type=user_ct, object_id=user.id).select_related(  # type: ignore
                "topic"
            )
        ]
        topics_list = [
            item
            for rel in rel_topics
            if (item := _get_metadata_item("topic", rel.topic_id)) is not None  # type: ignore
        ]
        topics = topics_list if topics_list else None

        # Fetch application areas with metadata
        rel_areas = [
            rel
            async for rel in RelApplicationArea.objects.filter(
                content_type=user_ct,
                object_id=user.id,  # type: ignore
            ).select_related("application_area")
        ]
        areas_list = [
            item
            for rel in rel_areas
            if (item := _get_metadata_item("application_area", rel.application_area_id)) is not None  # type: ignore
        ]
        application_areas = areas_list if areas_list else None

        # Fetch active membership (only one active membership per user)
        membership = None
        async for m in user.memberships.filter(end_date__isnull=True):  # type: ignore
            membership = MembershipType(m.type)
            break  # Only take the first active membership

        member_profiles.append(
            Member(
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                profile_url=HttpUrl(f"https://www.hipeac.net/~{user.username}/"),
                institutions=institutions if institutions else None,
                topics=topics,
                application_areas=application_areas,
                membership=membership,
            )
        )

    return MemberSearchResponse(total=len(member_profiles), limit=actual_limit, members=member_profiles)
