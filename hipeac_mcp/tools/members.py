"""MCP Tools for searching and analyzing HiPEAC members.

These tools provide intelligent search and discovery of network members
based on research interests, location, and institutional affiliation.
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import HttpUrl

from hipeac_mcp import mcp
from hipeac_mcp.db import ensure_connection_async
from hipeac_mcp.services.analytics import track_usage

from ..models import RelApplicationArea, RelInstitution, RelTopic, User
from ..schemas.members import Institution, Member, MemberSearchResponse
from ..schemas.metadata import MembershipType, MetadataItem
from .metadata import fetch_metadata_items


@mcp.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True))
@track_usage
async def search_members(
    query: str | None = None,
    topic_ids: list[int] | None = None,
    application_area_ids: list[int] | None = None,
    countries: list[str] | None = None,
    institution_type_ids: list[int] | None = None,
    membership_types: list[MembershipType] | None = None,
    limit: int = 50,
    ctx: Context = None,
) -> MemberSearchResponse:
    """Search HiPEAC network members by research interests, location, and institution.

    Returns detailed member profiles including current affiliation, research topics,
    and contact information.

    **Mandatory workflow**:
    1. Always call `get_metadata` first to get the full list of valid topic, area,
       and institution type IDs with their exact names.
    2. Find the topic(s) whose name exactly matches (or is closest to) the user's
       request. Use those IDs in `topic_ids` — do NOT substitute with broader or
       related topics on the first attempt.
    3. If the result is empty, then use the full topic list to identify related
       topics and present them to the user as alternatives, offering to search again.

    :param query: Text search on person names and emails only — do NOT use this for research topics or areas.
    :param topic_ids: Filter by research topic IDs (get from get_metadata tool).
    :param application_area_ids: Filter by application area IDs (get from get_metadata tool).
    :param countries: Filter by ISO country codes (e.g., ['BE', 'ES', 'DE']).
    :param institution_type_ids: Filter by institution type IDs (get from get_metadata tool).
    :param membership_types: Filter by membership type keys: 'member', 'associated_member',
        'affiliated_member', 'affiliated_phd' (get from get_metadata tool).
        Defaults to member, associated_member, and affiliated_member (excludes affiliated_phd).
    :param limit: Maximum number of results to return (max: 100).
    :returns: Structured search results with member profiles.
    """
    await ensure_connection_async()

    user_ct = await ContentType.objects.aget(app_label="hipeac", model="user")
    active_types = membership_types or [
        MembershipType.MEMBER,
        MembershipType.ASSOCIATED_MEMBER,
        MembershipType.AFFILIATED_MEMBER,
    ]
    queryset = User.objects.filter(
        memberships__end_date__isnull=True,
        memberships__type__in=active_types,
    ).distinct()

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
        queryset = queryset.filter(id__in=topic_user_ids)

    if application_area_ids:
        area_user_ids = [
            id
            async for id in RelApplicationArea.objects.filter(
                content_type=user_ct, application_area_id__in=application_area_ids
            ).values_list("object_id", flat=True)
        ]
        queryset = queryset.filter(id__in=area_user_ids)

    if countries:
        country_user_ids = [
            id
            async for id in RelInstitution.objects.filter(
                content_type=user_ct, institution__country__in=[c.upper() for c in countries]
            ).values_list("object_id", flat=True)
        ]
        queryset = queryset.filter(id__in=country_user_ids)

    if institution_type_ids:
        type_user_ids = [
            id
            async for id in RelInstitution.objects.filter(
                content_type=user_ct, institution__type_id__in=institution_type_ids
            ).values_list("object_id", flat=True)
        ]
        queryset = queryset.filter(id__in=type_user_ids)

    actual_limit = min(limit, 100)
    members = [m async for m in queryset.prefetch_related("memberships")[:actual_limit]]

    if not members:
        return MemberSearchResponse(total=0, limit=actual_limit, members=[])

    metadata_items = await fetch_metadata_items()

    def get_metadata_item(type_key: str, item_id: int) -> MetadataItem | None:
        return metadata_items.get(type_key, {}).get(item_id)

    # Batch-fetch all related data for the returned members in 3 queries instead of N×3.
    user_ids = [user.id for user in members]

    institutions_by_user: dict[int, list] = {uid: [] for uid in user_ids}
    async for rel in RelInstitution.objects.filter(content_type=user_ct, object_id__in=user_ids).select_related(
        "institution"
    ):
        institutions_by_user[rel.object_id].append(rel)  # type: ignore

    topics_by_user: dict[int, list] = {uid: [] for uid in user_ids}
    async for rel in RelTopic.objects.filter(content_type=user_ct, object_id__in=user_ids).select_related("topic"):
        topics_by_user[rel.object_id].append(rel)  # type: ignore

    areas_by_user: dict[int, list] = {uid: [] for uid in user_ids}
    async for rel in RelApplicationArea.objects.filter(content_type=user_ct, object_id__in=user_ids).select_related(
        "application_area"
    ):
        areas_by_user[rel.object_id].append(rel)  # type: ignore

    # Build structured member profiles using the batched data.
    member_profiles = []

    for user in members:
        institutions = [
            Institution(
                name=rel.institution.name,
                country=rel.institution.country,
                type=(
                    get_metadata_item("institution_type", rel.institution.type_id)  # type: ignore
                    if hasattr(rel.institution, "type_id") and rel.institution.type_id  # type: ignore
                    else None
                ),
            )
            for rel in institutions_by_user[user.id]  # type: ignore
        ]

        topics_list = [
            item
            for rel in topics_by_user[user.id]  # type: ignore
            if (item := get_metadata_item("topic", rel.topic_id)) is not None  # type: ignore
        ]
        topics = topics_list if topics_list else None

        areas_list = [
            item
            for rel in areas_by_user[user.id]  # type: ignore
            if (item := get_metadata_item("application_area", rel.application_area_id)) is not None  # type: ignore
        ]
        application_areas = areas_list if areas_list else None

        # Use the prefetched memberships cache — avoid re-querying with .filter().
        active = next((m for m in user.memberships.all() if m.end_date is None), None)  # type: ignore
        membership = MembershipType(active.type) if active else None

        member_profiles.append(
            Member(
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                profile_url=HttpUrl(f"https://www.hipeac.net/~{user.handle}/"),
                institutions=institutions if institutions else None,
                topics=topics,
                application_areas=application_areas,
                membership=membership,
            )
        )

    return MemberSearchResponse(total=len(member_profiles), limit=actual_limit, members=member_profiles)
