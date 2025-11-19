"""MCP Tools for searching and analyzing HiPEAC members.

These tools provide intelligent search and discovery of network members
based on research interests, location, and institutional affiliation.
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from hipeac_mcp import mcp

from ..models import Metadata, RelApplicationArea, RelInstitution, RelTopic, User


@mcp.tool()
def search_members(
    query: str | None = None,
    topics: list[str] | None = None,
    application_areas: list[str] | None = None,
    countries: list[str] | None = None,
    institution_types: list[str] | None = None,
    membership_types: list[str] | None = None,
    limit: int = 20,
) -> str:
    """Search HiPEAC network members by research interests, location, and institution.

    Returns detailed member profiles including current affiliation, research topics,
    and contact information. Use the metadata resources to discover available topics
    and application areas before searching.

    :param query: Text search in member names, emails, or institutions.
    :param topics: Filter by research topic IDs or names.
    :param application_areas: Filter by application area IDs or names.
    :param countries: Filter by country codes (e.g., ['BE', 'ES', 'DE']).
    :param institution_types: Filter by institution type (e.g., ['academia', 'industry']).
    :param membership_types: Filter by membership type ('member', 'associated_member', etc.).
    :param limit: Maximum number of results to return (max: 100).
    :returns: Formatted search results.
    """
    user_ct = ContentType.objects.get(app_label="hipeac", model="user")
    queryset = User.objects.filter(memberships__end_date__isnull=True).distinct()

    if query:
        queryset = queryset.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(username__icontains=query)
        )

    if topics:
        topic_ids = []
        for topic in topics:
            if topic.isdigit():
                ids = RelTopic.objects.filter(content_type=user_ct, topic_id=int(topic)).values_list(
                    "object_id", flat=True
                )
            else:
                ids = RelTopic.objects.filter(content_type=user_ct, topic__value__icontains=topic).values_list(
                    "object_id", flat=True
                )
            topic_ids.extend(ids)
        if topic_ids:
            queryset = queryset.filter(id__in=topic_ids)

    if application_areas:
        area_ids = []
        for area in application_areas:
            if area.isdigit():
                ids = RelApplicationArea.objects.filter(
                    content_type=user_ct, application_area_id=int(area)
                ).values_list("object_id", flat=True)
            else:
                ids = RelApplicationArea.objects.filter(
                    content_type=user_ct, application_area__value__icontains=area
                ).values_list("object_id", flat=True)
            area_ids.extend(ids)
        if area_ids:
            queryset = queryset.filter(id__in=area_ids)

    if countries:
        country_ids = RelInstitution.objects.filter(
            content_type=user_ct, institution__country__in=[c.upper() for c in countries]
        ).values_list("object_id", flat=True)
        queryset = queryset.filter(id__in=country_ids)

    if institution_types:
        type_ids = []
        for itype in institution_types:
            if itype.isdigit():
                ids = RelInstitution.objects.filter(content_type=user_ct, institution__type_id=int(itype)).values_list(
                    "object_id", flat=True
                )
            else:
                ids = RelInstitution.objects.filter(
                    content_type=user_ct, institution__type__value__icontains=itype
                ).values_list("object_id", flat=True)
            type_ids.extend(ids)
        if type_ids:
            queryset = queryset.filter(id__in=type_ids)

    if membership_types:
        queryset = queryset.filter(memberships__type__in=membership_types)

    actual_limit = min(limit, 100)
    members = queryset.select_related().prefetch_related("memberships")[:actual_limit]

    if not members:
        return "No members found matching the search criteria."

    results = [f"Found {len(members)} member(s) (showing up to {actual_limit}):\n"]

    for user in members:
        member_info = [
            f"**{user.first_name} {user.last_name}** (@{user.username})",
            f"  Profile: https://www.hipeac.net/~{user.username}/",
        ]

        rel_institutions = RelInstitution.objects.filter(content_type=user_ct, object_id=user.id).select_related(
            "institution"
        )
        if rel_institutions:
            inst_list = [f"{rel.institution.name} ({rel.institution.country})" for rel in rel_institutions]
            member_info.append(f"  Institutions: {', '.join(inst_list)}")

        rel_topics = RelTopic.objects.filter(content_type=user_ct, object_id=user.id).select_related("topic")
        if rel_topics:
            topic_list = [rel.topic.value for rel in rel_topics]
            member_info.append(f"  Research topics: {', '.join(topic_list)}")

        rel_areas = RelApplicationArea.objects.filter(content_type=user_ct, object_id=user.id).select_related(
            "application_area"
        )
        if rel_areas:
            area_list = [rel.application_area.value for rel in rel_areas]
            member_info.append(f"  Application areas: {', '.join(area_list)}")

        memberships = user.memberships.filter(end_date__isnull=True)
        if memberships:
            membership_list = [m.type for m in memberships]
            member_info.append(f"  Membership: {', '.join(membership_list)}")

        results.append("\n".join(member_info))
        results.append("")  # Empty line between members

    return "\n".join(results)


@mcp.tool()
def find_experts(
    expertise: list[str],
    country: str | None = None,
    min_members: int = 1,
) -> str:
    """Find expert researchers in specific topics or application areas.

    This tool identifies members with demonstrated expertise based on their declared
    research interests. Useful for finding collaborators or potential project partners.

    :param expertise: Required research topics or application areas to find experts in (IDs or names).
    :param country: Optional country code to filter by location.
    :param min_members: Minimum experts to return per topic/area (max: 10).
    :returns: Formatted expert profiles grouped by expertise area.
    """
    user_ct = ContentType.objects.get(app_label="hipeac", model="user")
    results = []
    actual_min = min(min_members, 10)

    for exp in expertise:
        metadata_q = Q(id=int(exp)) if exp.isdigit() else Q(value__icontains=exp)
        metadata_items = Metadata.objects.filter(metadata_q).filter(
            Q(type=Metadata.TOPIC) | Q(type=Metadata.APPLICATION_AREA)
        )

        if not metadata_items:
            continue

        for metadata in metadata_items:
            if metadata.type == Metadata.TOPIC:
                user_ids = list(
                    RelTopic.objects.filter(content_type=user_ct, topic=metadata).values_list("object_id", flat=True)
                )
            elif metadata.type == Metadata.APPLICATION_AREA:
                user_ids = list(
                    RelApplicationArea.objects.filter(content_type=user_ct, application_area=metadata).values_list(
                        "object_id", flat=True
                    )
                )
            else:
                continue

            if not user_ids:
                continue

            user_filter = Q(id__in=user_ids) & Q(memberships__end_date__isnull=True)

            if country:
                country_ids = RelInstitution.objects.filter(
                    content_type=user_ct, institution__country=country.upper()
                ).values_list("object_id", flat=True)
                user_filter &= Q(id__in=country_ids)

            experts = User.objects.filter(user_filter).distinct().select_related()[:actual_min]

            if not experts:
                continue

            results.append(f"## Experts in: {metadata.value}\n")

            for idx, user in enumerate(experts, 1):
                rel_institutions = RelInstitution.objects.filter(
                    content_type=user_ct, object_id=user.id
                ).select_related("institution")
                inst_names = (
                    [rel.institution.name for rel in rel_institutions] if rel_institutions else ["No institution"]
                )

                results.append(
                    f"{idx}. **{user.first_name} {user.last_name}** - {', '.join(inst_names)}\n"
                    f"   Profile: https://www.hipeac.net/~{user.username}/"
                )

            results.append("")  # Empty line between areas

    if not results:
        return "No experts found in the specified areas."

    return "\n".join(results)
