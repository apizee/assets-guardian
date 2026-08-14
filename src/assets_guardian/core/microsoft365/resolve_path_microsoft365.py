import logging
from typing import Any, cast

from assets_guardian.core.clients.microsoft_client import MicrosoftGraph
from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.domain.models.location import Location
from assets_guardian.core.domain.registry.client_registry import ClientProviderRegistry

logger = logging.getLogger(__name__)


class ResolvePathMicrosoft365:
    def __init__(self, graph: MicrosoftGraph, target_path: str):
        self.graph = graph
        self.target_path = target_path

    @classmethod
    def from_context(
        cls, ctx: Context, path: Location | None = None
    ) -> "ResolvePathMicrosoft365 | None":
        """Builds a ResolvePathMicrosoft365 from the given path.

        The path is expected as "<microsoft365 instance id>:<site>/<drive>/<folder>".
        Returns None (with a warning logged) if it isn't configured or the referenced
        microsoft365 instance can't be resolved to a MicrosoftGraph client.
        """
        if not path:
            return None

        clean_path = path.clean_path
        if ":" not in clean_path:
            logger.warning("Invalid path format (expected '<instance id>:<path>'): %r", clean_path)
            return None

        instance_id, target_path = clean_path.split(":", 1)
        params = ctx.app_config.integrations.get("microsoft365", {}).get(instance_id)
        if params is None:
            logger.warning("No microsoft365 instance configured for: %s", instance_id)
            return None

        client_provider = ClientProviderRegistry.instantiates_clientprovider("microsoft365", params)
        graph = client_provider.instantiate_client()
        if not isinstance(graph, MicrosoftGraph):
            logger.warning("%s: expected a MicrosoftGraph client, got %s", instance_id, type(graph))
            return None

        return cls(graph, target_path)

    async def get_sites(self) -> Any:
        """Get all sharepoint site (name and id)"""
        # Get all sharepoint sites from Microsoft Graph (equivalent to GET /sites)
        # In this case, we use a custom request to specify the search parameter because the
        # request is not supported by the SDK
        result: Any = await self.graph._user_client.sites.with_url(
            "https://graph.microsoft.com/v1.0/sites?search=*&$select=id,displayName"
        ).get()
        # Mapping site object to a dict
        if result:
            # Use simple list comprehension
            result = [{"id": site.id, "name": site.display_name} for site in result.value]
        return result

    async def get_drives_by_site(self, site_id: str) -> Any:
        """Get all drives from a site (name and id)"""
        # Get all drives from a sharepoint site (equivalent to GET /sites/{id}/drives)
        result: Any = await self.graph._user_client.sites.by_site_id(site_id).drives.get()
        # Mapping drive object to a dict
        if result:
            # Use simple list comprehension
            result = [{"id": drive.id, "name": drive.name} for drive in result.value]
        return result

    async def get_drives_by_user(self, user_id: str) -> Any:
        """Get all drives from a user"""
        # Get all drives from a user (equivalent to GET /users/{id}/drives)
        result: Any = await self.graph._user_client.users.by_user_id(user_id).drives.get()
        # Mapping drive object to a dict
        if result:
            # Use simple list comprehension
            result = [{"id": drive.id, "name": drive.name} for drive in result.value]
        return result

    async def get_root_drive_items(self, drive_id: str) -> Any:
        """Get all items from the root of a drive (name and id)"""
        # Get all items from a drive (equivalent to GET /drives/{id}/items/root/children)
        result: Any = await (
            self.graph._user_client.drives.by_drive_id(drive_id)
            .items.by_drive_item_id("root")
            .children.get()
        )
        if result:
            # Use simple list comprehension
            result = result.value
        return result

    async def get_children_drive_items(self, drive_id: str, item_id: str) -> Any:
        """Get all items from a drive"""
        # Get all items from a drive (equivalent to GET /drives/{id}/items/{id}/children)
        return await (
            self.graph._user_client.drives.by_drive_id(drive_id)
            .items.by_drive_item_id(item_id)
            .children.get()
        )

    async def get_drive_item(self, drive_id: str, item_id: str) -> Any:
        """Get an item"""
        # Get an item (equivalent to GET /drives/{drive-id}/items/{item-id})
        return await (
            self.graph._user_client.drives.by_drive_id(drive_id)
            .items.by_drive_item_id(item_id)
            .get()
        )

    async def _resolve_site_id(self, site_name: str) -> str:
        """Resolves a site id from its display name."""
        sites = await self.get_sites() or []
        site = next((s for s in sites if s["name"] == site_name), None)
        if site is None:
            raise ValueError(f"No SharePoint site found for name: {site_name!r}")
        return cast("str", site["id"])

    async def _resolve_drive_id(self, site_id: str, drive_name: str) -> str:
        """Resolves a drive id from its name within a site."""
        drives = await self.get_drives_by_site(site_id) or []
        drive = next((d for d in drives if d["name"] == drive_name), None)
        if drive is None:
            raise ValueError(f"No drive found for name: {drive_name!r}")
        return cast("str", drive["id"])

    async def _resolve_item_id(self, drive_id: str, folder_parts: list[str]) -> str:
        """Resolves a folder item id by walking the drive tree one segment at a time."""
        items = await self.get_root_drive_items(drive_id) or []
        item_id = None
        for folder_name in folder_parts:
            item = next((i for i in items if i.name == folder_name and i.folder), None)
            if item is None:
                raise ValueError(f"No folder found for name: {folder_name!r}")
            item_id = item.id
            children = await self.get_children_drive_items(drive_id, item_id)
            items = children.value if children else []
        if item_id is None:
            raise ValueError(f"Empty folder path: {folder_parts!r}")
        return cast("str", item_id)

    async def resolve_target_path(self, target_path: str) -> tuple[str, str, str]:
        """Resolves a "<site name>/<drive name>/<folder path>" string into Graph IDs.

        Args:
            target_path: SharePoint site path, e.g.
                "My Site/My Drive/Folder/Subfolder".

        Returns:
            tuple[str, str, str]: The resolved (site_id, drive_id, item_id).
        """
        site_name, drive_name, *folder_parts = target_path.split("/")
        site_id = await self._resolve_site_id(site_name)
        drive_id = await self._resolve_drive_id(site_id, drive_name)
        item_id = await self._resolve_item_id(drive_id, folder_parts)
        return site_id, drive_id, item_id
