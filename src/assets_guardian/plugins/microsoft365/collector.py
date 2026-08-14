import asyncio
import logging
from collections.abc import Iterable
from typing import Any

from assets_guardian.core.domain.models.access import Access
from assets_guardian.core.domain.models.asset import Asset
from assets_guardian.core.domain.models.identity import Identity
from assets_guardian.core.domain.ports.collector import Collector
from assets_guardian.core.domain.registry.collector_registry import CollectorRegistry
from assets_guardian.plugins.microsoft365.constants import DEFAULT_INSTANCE_ID, SOURCE_NAME
from assets_guardian.plugins.microsoft365.mapper import Microsoft365Mapper
from assets_guardian.plugins.microsoft365.repository import Microsoft365Repository

logger = logging.getLogger(__name__)


@CollectorRegistry.register(SOURCE_NAME)
class Microsoft365Collector(Collector):
    """Microsoft 365 collector using Microsoft Graph API."""

    def __init__(self, client: Any, instance_config: dict[str, Any]) -> None:
        self.__config = instance_config
        self.__mapper = Microsoft365Mapper(instance_id=self.instance_id)
        self.__repository = Microsoft365Repository(client)
        self.__cached_raw_users: list[dict[str, Any]] | None = None
        self.__loop = asyncio.new_event_loop()

    @property
    def source_name(self) -> str:
        return SOURCE_NAME

    @property
    def instance_id(self) -> str:
        return str(self.__config.get("instance_id", DEFAULT_INSTANCE_ID))

    def __run(self, coro: Any) -> Any:
        return self.__loop.run_until_complete(coro)

    def __get_raw_users(self) -> list[dict[str, Any]]:
        if self.__cached_raw_users is None:
            self.__cached_raw_users = self.__run(self.__repository.get_raw_users())
        return self.__cached_raw_users or []

    def collect_identities(self) -> Iterable[Identity]:
        count = 0
        for raw_user in self.__get_raw_users():
            role_accesses = [self.__mapper.to_access(role) for role in raw_user.get("roles", [])]
            count += 1
            yield self.__mapper.to_identity(raw_user, accesses=role_accesses)
        logger.info("Collected %d Microsoft 365 identities.", count)

    def collect_assets(self) -> Iterable[Asset]:
        count = 0
        raw_assets_apps = self.__run(self.__repository.get_raw_assets_applications())
        for raw_asset in raw_assets_apps:
            count += 1
            yield self.__mapper.to_asset(raw_asset, asset_type="application")

        raw_assets_licenses = self.__run(self.__repository.get_raw_assets_licenses())
        for raw_license in raw_assets_licenses:
            count += 1
            yield self.__mapper.to_asset(raw_license, asset_type="license")
        logger.info("Collected %d Microsoft 365 assets (applications and licenses).", count)

    def collect_accesses(self) -> Iterable[Access]:
        async def _fetch() -> tuple[
            list[dict[str, Any]],
            list[dict[str, Any]],
            dict[str, list[dict[str, Any]]],
        ]:
            users = self.__cached_raw_users
            if users is None:
                users = await self.__repository.get_raw_users()
            groups = await self.__repository.get_raw_groups()
            members_by_group: dict[str, list[dict[str, Any]]] = {}
            for group in groups:
                members_by_group[group["id"]] = await self.__repository.get_raw_group_members(
                    group["id"]
                )
            return users, groups, members_by_group

        raw_users, raw_groups, members_by_group = self.__run(_fetch())
        self.__cached_raw_users = raw_users

        role_asset = Asset(
            source=SOURCE_NAME,
            external_id="roles",
            asset_type="role",
            name="Roles",
        )

        license_asset = Asset(
            source=SOURCE_NAME,
            external_id="licenses",
            asset_type="license",
            name="Licenses",
        )
        count = 0
        for raw_user in raw_users:
            for role in raw_user.get("roles", []):
                count += 1
                yield self.__mapper.to_access(role, user_data=raw_user, asset=role_asset)
            for license_name in raw_user.get("licenses", []):
                count += 1
                yield self.__mapper.to_access(
                    license_name, user_data=raw_user, asset=license_asset, access_type="license"
                )
        for raw_group in raw_groups:
            group_asset = self.__mapper.to_asset(raw_group, asset_type="group")
            for member in members_by_group.get(raw_group["id"], []):
                count += 1
                yield self.__mapper.to_group_access(member, asset=group_asset)
        logger.info("Extracted %d Microsoft 365 accesses in total.", count)

    def collect_groups(self) -> Iterable[Any]:
        raw_groups = self.__run(self.__repository.get_raw_groups())
        for raw_group in raw_groups:
            yield self.__mapper.to_asset(raw_group, asset_type="group")

    def collect_permissions(self) -> Iterable[Any]:
        return []
