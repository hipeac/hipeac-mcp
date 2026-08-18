"""Pydantic schemas for HiPEAC metadata."""

from enum import StrEnum

from pydantic import BaseModel


class MetadataType(StrEnum):
    """Metadata type enumeration."""

    APPLICATION_AREA = "application_area"
    TOPIC = "topic"
    INSTITUTION_TYPE = "institution_type"
    EMPLOYMENT_TYPE = "employment_type"
    CAREER_LEVEL = "career_level"


class MetadataItem(BaseModel):
    """A single metadata item."""

    id: int
    value: str


class MembershipType(StrEnum):
    """Membership type enumeration."""

    MEMBER = "member"
    ASSOCIATED_MEMBER = "associated_member"
    AFFILIATED_MEMBER = "affiliated_member"
    AFFILIATED_PHD = "affiliated_phd"


class MembershipTypeItem(BaseModel):
    """A membership type option."""

    key: MembershipType
    label: str


class MetadataResponse(BaseModel):
    """Complete metadata response."""

    application_areas: list[MetadataItem] | None = None
    institution_types: list[MetadataItem] | None = None
    membership_types: list[MembershipTypeItem] | None = None
    topics: list[MetadataItem] | None = None
    employment_types: list[MetadataItem] | None = None
    career_levels: list[MetadataItem] | None = None
