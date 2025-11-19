"""SQLModel schemas for read-only async database operations.

This module provides SQLModel schemas that map to existing database tables.
These are used for ORM queries via SQLAlchemy/aiomysql in read-only mode.
No table creation occurs - we only read from existing tables.
"""

from enum import Enum

from pydantic import BaseModel


class MetadataType(str, Enum):
    """Metadata type enumeration."""

    APPLICATION_AREA = "application_area"
    TOPIC = "topic"
    INSTITUTION_TYPE = "institution_type"


class MetadataItem(BaseModel):
    """A single metadata item."""

    id: int
    value: str


class MetadataCategory(BaseModel):
    """A category of metadata items."""

    title: str
    description: str
    items: list[MetadataItem]


class MembershipType(str, Enum):
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
