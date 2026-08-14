import asyncio
import logging
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from assets_guardian.core.clients.microsoft_client import MicrosoftGraph
from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.domain.models.location import Location
from assets_guardian.core.microsoft365.resolve_path_microsoft365 import ResolvePathMicrosoft365
from assets_guardian.utils.dates import add_date_to_filename

logger = logging.getLogger(__name__)


def resolve_location_path(ctx: Context, location: Location, cache_filename: str) -> str | None:
    """Resolves a Location to a local file path, downloading it from SharePoint if remote.

    Any 'DATE' placeholder in the file name is replaced with today's date, if present
    (no-op otherwise).

    Args:
        ctx: The application context.
        location: The configured file location (local or remote).
        cache_filename: File name to use when caching a downloaded remote file.

    Returns:
        str | None: The local file path to read, or None if resolution/download failed.
    """
    if location.is_local:
        return add_date_to_filename(location.clean_path)

    if location.is_remote:
        cache_dir = Path(ctx.app_config.cache.cache_dir)
        cached_path = str(cache_dir / cache_filename)
        if Path(cached_path).exists():
            logger.info("File already in cache, using cached copy: %s", cached_path)
            return add_date_to_filename(cached_path)

        resolver = ResolvePathMicrosoft365.from_context(ctx, location)
        if resolver is None:
            return None
        dated_target_path = add_date_to_filename(resolver.target_path)
        downloader = DownloadMicrosoft365(resolver.graph, resolver, dated_target_path)
        cache_dir.mkdir(parents=True, exist_ok=True)
        if not downloader.pull_report(cached_path):
            return None
        return cached_path

    return None


class DownloadMicrosoft365:
    def __init__(self, graph: MicrosoftGraph, resolver: ResolvePathMicrosoft365, target_path: str):
        self.graph = graph
        self.resolver = resolver
        self.target_path = target_path
        self.__loop = asyncio.new_event_loop()

    def __run(self, coro: Coroutine[Any, Any, bool]) -> bool:
        return self.__loop.run_until_complete(coro)

    async def get_drive_item_content(self, drive_id: str, item_id: str) -> Any:
        """Get the content of an item"""
        # Get the content of an item (equivalent to GET /drives/{drive-id}/items/{item-id}/content)
        return await (
            self.graph._user_client.drives.by_drive_id(drive_id)
            .items.by_drive_item_id(item_id)
            .content.get()
        )

    def pull_report(self, local_file_path: str) -> bool:
        """Resolves the SharePoint source file (from target_path) and downloads it locally.

        target_path is expected as "<site>/<drive>/<folder>/<file name>", with the
        file name as its last segment.
        """

        async def _pull() -> bool:
            folder_path, _, remote_file_name = self.target_path.rpartition("/")
            _, drive_id, folder_id = await self.resolver.resolve_target_path(folder_path)
            return await self.pull_item(drive_id, folder_id, remote_file_name, local_file_path)

        return self.__run(_pull())

    async def pull_item(
        self,
        drive_id: str,
        folder_id: str,
        remote_file_name: str,
        local_file_path: str,
    ) -> bool:
        """Download a file from a Sharepoint drive folder to a local path"""
        children = await self.resolver.get_children_drive_items(drive_id, folder_id)
        items = children.value if children else []
        item = next((i for i in items if i.name == remote_file_name), None)
        if item is None:
            logger.warning("No file found for name: %s", remote_file_name)
            return False

        content = await self.get_drive_item_content(drive_id, item.id)
        Path(local_file_path).write_bytes(content)
        logger.info("Downloaded %s to %s", remote_file_name, local_file_path)
        return True
