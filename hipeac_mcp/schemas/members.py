"""Pydantic schemas for member search responses."""

from pydantic import BaseModel, HttpUrl

from .metadata import MembershipType, MetadataItem


class Institution(BaseModel):
    """Institution information."""

    name: str
    country: str
    type: MetadataItem | None = None


class Member(BaseModel):
    """Individual member profile."""

    username: str
    first_name: str
    last_name: str
    profile_url: HttpUrl
    membership: MembershipType | None = None
    institutions: list[Institution] | None = None
    application_areas: list[MetadataItem] | None = None
    topics: list[MetadataItem] | None = None


class MemberSearchResponse(BaseModel):
    """Search results for member queries."""

    total: int
    limit: int
    members: list[Member]
