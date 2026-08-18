"""MCP Tools for searching HiPEAC job postings."""

from django.db.models import Q
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from hipeac_mcp import mcp
from hipeac_mcp.db import ensure_connection_async
from hipeac_mcp.services.analytics import track_usage

from ..models import Job, RelApplicationArea, RelTopic
from ..models.jobs import job_ct_id
from ..schemas.jobs import Job as JobDetail
from ..schemas.jobs import JobInstitution, JobSearchResponse, JobSummary
from ..schemas.metadata import MetadataItem
from .metadata import fetch_metadata_items


HIPEAC_BASE_URL = "https://www.hipeac.net"
DESCRIPTION_PREVIEW_LENGTH = 300


def _truncate(text: str, length: int) -> str:
    """Truncate text on a word boundary.

    :param text: Text to truncate.
    :param length: Maximum character length.
    :returns: Truncated text with a trailing ellipsis if it was cut.
    """
    text = text.strip()
    if len(text) <= length:
        return text
    cut = text.rfind(" ", 0, length)
    return f"{text[: cut if cut != -1 else length]}…"


def _job_institution(job: Job) -> JobInstitution | None:
    """Build a JobInstitution from a job's prefetched institution FK.

    :param job: Job instance with ``institution`` selected.
    :returns: JobInstitution, or None if the job has no institution.
    """
    if job.institution_id is None:  # type: ignore[attr-defined]
        return None
    return JobInstitution(name=job.institution.name, country=job.institution.country)  # type: ignore[union-attr]


async def _resolve_job_topics_and_areas(
    job_ids: list[int],
) -> tuple[dict[int, list[MetadataItem]], dict[int, list[MetadataItem]]]:
    """Batch-resolve topics and application areas for a set of jobs.

    :param job_ids: Job primary keys.
    :returns: Tuple of (topics by job id, application areas by job id).
    """
    job_ct = job_ct_id()
    metadata_items = await fetch_metadata_items()

    topics_by_job: dict[int, list[MetadataItem]] = {jid: [] for jid in job_ids}
    async for rel in RelTopic.objects.filter(content_type_id=job_ct, object_id__in=job_ids):
        item = metadata_items.get("topic", {}).get(rel.topic_id)  # type: ignore[attr-defined]
        if item is not None:
            topics_by_job[rel.object_id].append(item)  # type: ignore[index]

    areas_by_job: dict[int, list[MetadataItem]] = {jid: [] for jid in job_ids}
    async for rel in RelApplicationArea.objects.filter(content_type_id=job_ct, object_id__in=job_ids):
        item = metadata_items.get("application_area", {}).get(rel.application_area_id)  # type: ignore[attr-defined]
        if item is not None:
            areas_by_job[rel.object_id].append(item)  # type: ignore[index]

    return topics_by_job, areas_by_job


def _base_filters(
    query: str | None,
    employment_type_id: int | None,
    career_level_ids: list[int] | None,
    countries: list[str] | None,
    include_expired: bool,
):
    """Build the filtered, related Job queryset shared by search_jobs.

    :param query: Free-text search on title/description/location/institution name.
    :param employment_type_id: Employment type metadata ID filter.
    :param career_level_ids: Career level metadata ID filters.
    :param countries: ISO country code filters.
    :param include_expired: Whether to include jobs past their deadline.
    :returns: Filtered Job queryset with institution/employment_type/career_levels related.
    """
    queryset = Job.objects.all() if include_expired else Job.objects.active()
    queryset = queryset.select_related("institution", "employment_type").prefetch_related("career_levels")

    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(location__icontains=query)
            | Q(institution__name__icontains=query)
        )

    if employment_type_id:
        queryset = queryset.filter(employment_type_id=employment_type_id)

    if career_level_ids:
        queryset = queryset.filter(career_levels__id__in=career_level_ids)

    if countries:
        queryset = queryset.filter(country__in=[c.upper() for c in countries])

    return queryset.distinct()


@mcp.tool(structured_output=True, annotations=ToolAnnotations(readOnlyHint=True))
@track_usage
async def search_jobs(
    query: str | None = None,
    topic_ids: list[int] | None = None,
    application_area_ids: list[int] | None = None,
    employment_type_id: int | None = None,
    career_level_ids: list[int] | None = None,
    countries: list[str] | None = None,
    include_expired: bool = False,
    limit: int = 20,
    ctx: Context = None,
) -> JobSearchResponse:
    """Search HiPEAC job postings by title, research area, and employment details.

    **Mandatory workflow**: call ``get_metadata`` first to get valid topic,
    application area, employment type, and career level IDs — use those IDs,
    not free text, for the corresponding filters.

    :param query: Text search on job title, description, location, and institution name.
    :param topic_ids: Filter by research topic IDs (get from get_metadata tool).
    :param application_area_ids: Filter by application area IDs (get from get_metadata tool).
    :param employment_type_id: Filter by employment type ID (get from get_metadata tool).
    :param career_level_ids: Filter by career level IDs (get from get_metadata tool).
    :param countries: Filter by ISO country codes (e.g., ['BE', 'ES', 'DE']).
    :param include_expired: Include jobs past their application deadline. Defaults to false.
    :param limit: Maximum number of results to return (max: 50).
    :returns: Structured search results with job summaries (truncated descriptions).
    """
    await ensure_connection_async()

    queryset = _base_filters(query, employment_type_id, career_level_ids, countries, include_expired)

    if topic_ids or application_area_ids:
        job_ct = job_ct_id()

        if topic_ids:
            topic_job_ids = [
                jid
                async for jid in RelTopic.objects.filter(content_type_id=job_ct, topic_id__in=topic_ids).values_list(
                    "object_id", flat=True
                )
            ]
            queryset = queryset.filter(id__in=topic_job_ids)

        if application_area_ids:
            area_job_ids = [
                jid
                async for jid in RelApplicationArea.objects.filter(
                    content_type_id=job_ct, application_area_id__in=application_area_ids
                ).values_list("object_id", flat=True)
            ]
            queryset = queryset.filter(id__in=area_job_ids)

    actual_limit = min(limit, 50)
    jobs = [j async for j in queryset[:actual_limit]]

    if not jobs:
        return JobSearchResponse(total=0, limit=actual_limit, jobs=[])

    topics_by_job, areas_by_job = await _resolve_job_topics_and_areas([job.id for job in jobs])  # type: ignore[attr-defined]

    summaries = [
        JobSummary(
            id=job.id,  # type: ignore[attr-defined]
            title=job.title,
            institution=_job_institution(job),
            employment_type=(
                MetadataItem(id=job.employment_type.id, value=job.employment_type.value)  # type: ignore[union-attr]
                if job.employment_type_id  # type: ignore[attr-defined]
                else None
            ),
            career_levels=[MetadataItem(id=cl.id, value=cl.value) for cl in job.career_levels.all()] or None,  # type: ignore[attr-defined]
            topics=topics_by_job.get(job.id) or None,  # type: ignore[attr-defined]
            application_areas=areas_by_job.get(job.id) or None,  # type: ignore[attr-defined]
            location=job.location,
            country=job.country or "",
            deadline=job.deadline.isoformat() if job.deadline else None,
            positions=job.positions,
            description_preview=_truncate(job.description, DESCRIPTION_PREVIEW_LENGTH),
            url=f"{HIPEAC_BASE_URL}{job.get_absolute_url()}",
        )
        for job in jobs
    ]

    return JobSearchResponse(total=len(summaries), limit=actual_limit, jobs=summaries)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
@track_usage
async def get_job(job_id: int, ctx: Context = None) -> JobDetail:
    """Retrieve full details of a single HiPEAC job posting, including the complete description.

    :param job_id: Job ID from a ``search_jobs`` result.
    :returns: Full job posting detail.
    :raises Job.DoesNotExist: If no job matches the given ID.
    """
    await ensure_connection_async()

    job = await Job.objects.select_related("institution", "employment_type").prefetch_related("career_levels").aget(
        id=job_id
    )
    topics_by_job, areas_by_job = await _resolve_job_topics_and_areas([job.id])  # type: ignore[attr-defined]

    return JobDetail(
        id=job.id,  # type: ignore[attr-defined]
        title=job.title,
        institution=_job_institution(job),
        employment_type=(
            MetadataItem(id=job.employment_type.id, value=job.employment_type.value)  # type: ignore[union-attr]
            if job.employment_type_id  # type: ignore[attr-defined]
            else None
        ),
        career_levels=[MetadataItem(id=cl.id, value=cl.value) for cl in job.career_levels.all()] or None,  # type: ignore[attr-defined]
        topics=topics_by_job.get(job.id) or None,  # type: ignore[attr-defined]
        application_areas=areas_by_job.get(job.id) or None,  # type: ignore[attr-defined]
        location=job.location,
        country=job.country or "",
        deadline=job.deadline.isoformat() if job.deadline else None,
        positions=job.positions,
        description=job.description,
        url=f"{HIPEAC_BASE_URL}{job.get_absolute_url()}",
    )
