from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from assets_guardian.core.domain.models.access import Access
from assets_guardian.core.domain.models.asset import Asset
from assets_guardian.core.domain.models.identity import Identity

if TYPE_CHECKING:
    from assets_guardian.core.domain.ports.mapper import IMapper
    from assets_guardian.core.domain.ports.repository import IRepository


class Collector:
    """Port: IAM data collector.

    Defines the contract for collecting identities, assets,
    and accesses from an external source.
    """

    def __init__(self, client: Any, instance_config: dict[str, Any]) -> None:
        """Initializes the collector with a client and its configuration.

        Subclasses must initialize self._repository and self._mapper
        in their own __init__ (or via properties).
        """
        self._client = client
        self._config = instance_config
        self._repository: IRepository
        self._mapper: IMapper

    @property
    def source_name(self) -> str:
        """Name of the source (e.g., 'gitlab', 'microsoft365', 'dolibarr')."""
        raise NotImplementedError

    @property
    def instance_id(self) -> str:
        """Unique identifier of the audited instance (e.g., 'gitlab.company.com')."""
        raise NotImplementedError

    def collect_identities(self) -> Iterable[Identity]:
        """Collects users and service accounts (default implementation)."""
        raw_users = self._repository.get_raw_users()
        for user in raw_users:
            yield self._mapper.to_identity(user)

    def collect_assets(self) -> Iterable[Asset]:
        """Collects assets (projects, sites, applications, etc.) (default implementation)."""
        raw_assets = self._repository.get_raw_assets()
        for asset in raw_assets:
            yield self._mapper.to_asset(asset)

    def collect_accesses(self) -> Iterable[Access]:
        """Collects identity-asset-role relations (default implementation).

        This implementation attempts to link assets to accesses if possible.
        """
        # We materialize assets into a list here because we will iterate over them multiple times
        # (searching for target_asset in the accesses loop)
        assets = list(self.collect_assets())
        raw_accesses = self._repository.get_raw_accesses()

        for raw in raw_accesses:
            asset_id = str(raw.get("pid") or raw.get("project_id") or raw.get("asset_id") or "")
            target_asset = next(
                (asset for asset in assets if str(asset.external_id) == asset_id),
                None,
            )
            yield self._mapper.to_access(raw, asset=target_asset)

    # TODO: Should groups become an explicit concept in the domain model?
    def collect_groups(self) -> Iterable[Any]:
        """Optional: collects groups from the source."""
        return []

    # TODO: Same question, but for permissions.
    def collect_permissions(self) -> Iterable[Any]:
        """Optional: collects granular permissions."""
        return []
