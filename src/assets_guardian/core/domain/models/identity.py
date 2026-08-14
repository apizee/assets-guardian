from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from assets_guardian.core.domain.models.access import Access
from assets_guardian.core.domain.models.validator import validate_field


class IdentityType(StrEnum):
    # Refine identity types based on requirements (e.g., human, machine, etc.)
    HUMAN = "human"
    NON_HUMAN = "non_human"
    GENERIC = "generic"


class IdentityState(StrEnum):
    # Refine identity states based on requirements (e.g., active, inactive, blocked, etc.)
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True, kw_only=True)
class Identity:
    """Normalized representation of an identity from an external source.

    Attributes:
        source: Source name (e.g., gitlab, microsoft365, dolibarr, etc.).
        external_id: Unique identifier of the identity within the source.
        identity_type: Type of identity (human, non-human, generic, etc.).
        email: Email address associated with the identity in the source.
        username: Username or handle of the identity in the source.
        name: Full or display name of the identity in the source.
        first_name: First name of the identity in the source.
        last_name: Last name of the identity in the source.
        company: Company or organization associated with the identity in the source.
        description: Description of the identity in the source (job title, role, etc.).
        state: State of the identity in the source (active, inactive, blocked, etc.).
        mfa_enabled: Flag indicating if MFA is enabled for the identity in the source.
        is_privileged: Flag indicating if the identity has privileged access in the source.
        is_external: Flag indicating if the identity is external to the organization.
        created_at: Creation date of the identity in the source.
        created_by: Identifier of the identity's creator in the source.
        last_activity_at: Last activity date of the identity in the source.
        last_sign_in_at: Last sign-in date of the identity in the source.
        last_sign_in_ip: IP address of the last sign-in.
        comments: Internal comments or notes for Assets Guardian.
        metadata: Custom arbitrary metadata dict.
    """

    # Global
    source: str
    external_id: str
    identity_type: IdentityType

    # Civils
    name: str
    email: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    description: str | None = None

    # Security
    state: IdentityState | None = None
    mfa_enabled: bool | None = None
    is_privileged: bool | None = None
    is_external: bool | None = None

    # Dates and activity
    created_at: datetime | None = None
    created_by: str | None = None
    last_activity_at: datetime | None = None
    last_sign_in_at: datetime | None = None
    last_sign_in_ip: IPv4Address | IPv6Address | None = None

    # Miscellaneous
    comments: str | None = None
    metadata: dict[str, Any] | None = None

    # Access
    access: list[Access] | None = None

    def __post_init__(self) -> None:
        validate_field(self, "source", str)
        validate_field(self, "external_id", str)
        validate_field(self, "identity_type", IdentityType)
        validate_field(self, "name", str)
        validate_field(self, "email", str, optional=True)
        validate_field(self, "username", str, optional=True)
        validate_field(self, "first_name", str, optional=True)
        validate_field(self, "last_name", str, optional=True)
        validate_field(self, "company", str, optional=True)
        validate_field(self, "description", str, optional=True, empty=True)
        validate_field(self, "state", IdentityState, optional=True)
        validate_field(self, "mfa_enabled", bool, optional=True)
        validate_field(self, "is_privileged", bool, optional=True)
        validate_field(self, "is_external", bool, optional=True)
        validate_field(self, "created_at", datetime, optional=True)
        validate_field(self, "created_by", str, optional=True)
        validate_field(self, "last_activity_at", datetime, optional=True)
        validate_field(self, "last_sign_in_at", datetime, optional=True)
        validate_field(self, "last_sign_in_ip", (IPv4Address, IPv6Address), optional=True)
        validate_field(self, "comments", str, optional=True, empty=True)
        validate_field(self, "metadata", dict, optional=True, empty=True)
        validate_field(self, "access", list, optional=True, empty=True)
