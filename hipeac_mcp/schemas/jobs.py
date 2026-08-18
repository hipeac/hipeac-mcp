"""Pydantic schemas for job tools."""

from pydantic import BaseModel

from .metadata import MetadataItem


class JobInstitution(BaseModel):
    """Institution posting a job."""

    name: str
    country: str


class JobSummary(BaseModel):
    """A single job posting as returned by search_jobs, with a truncated description."""

    id: int
    title: str
    institution: JobInstitution | None = None
    employment_type: MetadataItem | None = None
    career_levels: list[MetadataItem] | None = None
    topics: list[MetadataItem] | None = None
    application_areas: list[MetadataItem] | None = None
    location: str = ""
    country: str = ""
    deadline: str | None = None
    positions: int | None = None
    description_preview: str = ""
    url: str


class JobSearchResponse(BaseModel):
    """Search results for job queries."""

    total: int
    limit: int
    jobs: list[JobSummary]


class Job(BaseModel):
    """Full job posting as returned by get_job, with the complete description."""

    id: int
    title: str
    institution: JobInstitution | None = None
    employment_type: MetadataItem | None = None
    career_levels: list[MetadataItem] | None = None
    topics: list[MetadataItem] | None = None
    application_areas: list[MetadataItem] | None = None
    location: str = ""
    country: str = ""
    deadline: str | None = None
    positions: int | None = None
    description: str = ""
    url: str
