import logging
from typing import Any

from assets_guardian.core.domain.models.access import Access
from assets_guardian.core.domain.models.asset import Asset
from assets_guardian.core.domain.models.identity import Identity, IdentityState, IdentityType
from assets_guardian.core.domain.ports.mapper import IMapper
from assets_guardian.plugins.microsoft365.constants import SOURCE_NAME
from assets_guardian.utils.dates import format_datetime

logger = logging.getLogger(__name__)


class Microsoft365Mapper(IMapper):
    """Port: Data normalizer (mapper).

    Defines the contract for converting raw data from APIs
    to the domain's normalized data models.
    """

    def __init__(self, instance_id: str) -> None:
        self._instance_id = instance_id

    @property
    def source_name(self) -> str:
        return SOURCE_NAME

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def to_identity(self, raw_data: Any, accesses: list[Access] | None = None) -> Identity:
        if not isinstance(raw_data, dict):
            raw_data = {}

        account_enabled = raw_data.get("accountEnabled", False)

        roles = raw_data.get("roles", [])

        return Identity(
            source=self.source_name,
            external_id=str(raw_data.get("id", "unknown")),
            identity_type=IdentityType.HUMAN,
            name=raw_data.get("displayName") or "Unnamed",
            email=raw_data.get("email"),
            company=raw_data.get("companyName"),
            description=raw_data.get("jobTitle"),
            state=IdentityState.ACTIVE if account_enabled else IdentityState.INACTIVE,
            mfa_enabled=raw_data.get("mfaEnabled"),
            is_privileged=bool(roles),
            is_external=raw_data.get("userType") == "Guest",
            created_at=raw_data.get("createdDateTime"),
            last_sign_in_at=raw_data.get("signInActivity"),
            access=accesses,
            metadata={
                "userType": raw_data.get("userType"),
                "lastPasswordChangeDateTime": format_datetime(
                    raw_data.get("lastPasswordChangeDateTime")
                ),
                "roles": roles,
                "web_url": "https://entra.microsoft.com/",
                "licenses": raw_data.get("licenses", []),
            },
        )

    def to_asset(self, raw_data: Any, asset_type: str = "application") -> Asset:
        if not isinstance(raw_data, dict):
            raw_data = {}

        if asset_type == "group":
            group_types = raw_data.get("groupTypes") or []
            metadata: dict[str, Any] = {
                "visibility": raw_data.get("visibility"),
                "groupType": ", ".join(group_types) if group_types else "Security",
            }
        elif asset_type == "license":
            metadata = {
                "capabilityStatus": raw_data.get("capabilityStatus"),
                "consumedUnits": raw_data.get("consumedUnits"),
                "enabledUnits": raw_data.get("enabledUnits"),
            }
        else:
            metadata = {
                "appId": raw_data.get("appId"),
            }

        account_enabled = raw_data.get("accountEnabled", True)
        state = "active" if account_enabled else "inactive"

        return Asset(
            source=self.source_name,
            external_id=str(raw_data.get("id", "unknown")),
            asset_type=asset_type,
            name=raw_data.get("name") or "Unnamed",
            description=raw_data.get("description"),
            created_at=raw_data.get("createdDateTime"),
            state=state,
            metadata=metadata,
        )

    def to_group_access(self, raw_member: Any, asset: Asset) -> Access:
        if not isinstance(raw_member, dict):
            raw_member = {}

        return Access(
            source=self.source_name,
            access_type="group_membership",
            name="Member",
            asset=asset,
            state="active",
            metadata={
                "asset_external_id": asset.external_id,
                "asset_name": asset.name,
                "asset_description": asset.description or "",
                "asset_visibility": asset.metadata.get("visibility") if asset.metadata else None,
                "asset_group_type": asset.metadata.get("groupType") if asset.metadata else None,
                "asset_created_at": format_datetime(asset.created_at),
                "user_external_id": str(raw_member.get("id", "")),
                "user_name": raw_member.get("displayName") or "Unnamed",
                "user_email": raw_member.get("mail") or raw_member.get("userPrincipalName"),
            },
        )

    def to_access(
        self,
        raw_data: Any,
        asset: Asset | None = None,
        user_data: dict[str, Any] | None = None,
        access_type: str = "role",
    ) -> Access:
        name = raw_data if isinstance(raw_data, str) else raw_data.get("name", "Unknown")

        metadata: dict[str, Any] | None = None
        if user_data:
            metadata = {
                "user_id": user_data.get("id"),
                "user_name": user_data.get("displayName"),
                "user_email": user_data.get("email"),
            }

        return Access(
            source=self.source_name,
            access_type=access_type,
            name=name,
            asset=asset,
            state="active",
            metadata=metadata,
        )
