import asyncio
import logging
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

import requests

from assets_guardian.core.clients.microsoft_client import MicrosoftGraph
from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.domain.models.location import Location
from assets_guardian.core.microsoft365.resolve_path_microsoft365 import ResolvePathMicrosoft365

logger = logging.getLogger(__name__)


def push_to_location(ctx: Context, location: Location, local_file_path: str) -> bool:
    """Pushes a local file to SharePoint if the Location is remote; no-op if local.

    Args:
        ctx: The application context.
        location: The configured file location (local or remote).
        local_file_path: Path to the local file to push.

    Returns:
        bool: True if the file is already at its destination (local) or was
            successfully pushed (remote), False if resolution/upload failed.
    """
    if location.is_local:
        return True

    if location.is_remote:
        resolver = ResolvePathMicrosoft365.from_context(ctx, location)
        if resolver is None:
            return False
        folder_path, _, _ = resolver.target_path.rpartition("/")
        uploader = UploadMicrosoft365(resolver.graph, resolver, folder_path)
        return uploader.upload_report(local_file_path)
    return False


class UploadMicrosoft365:
    def __init__(self, graph: MicrosoftGraph, resolver: ResolvePathMicrosoft365, target_path: str):
        self.graph = graph
        self.resolver = resolver
        self.target_path = target_path
        self.__loop = asyncio.new_event_loop()

    def __run(self, coro: Coroutine[Any, Any, bool]) -> bool:
        return self.__loop.run_until_complete(coro)

    def upload_report(self, output_path: str) -> bool:
        """Resolves the SharePoint destination and pushes the report there."""

        async def _upload() -> bool:
            site_id, drive_id, item_id = await self.resolver.resolve_target_path(self.target_path)
            return await self.push_item(
                site_id=site_id,
                drive_id=drive_id,
                item_id=item_id,
                remote_file_path=Path(output_path).name,
                local_file_path=output_path,
            )

        return self.__run(_upload())

    async def push_item(
        self,
        site_id: str,
        drive_id: str,
        item_id: str,
        remote_file_path: str,
        local_file_path: str = "test",
    ) -> bool:  # pylint: disable=too-many-arguments
        """Push a file on a Sharepoint drive"""
        token = await self.graph.get_token()  # user_id: str = None
        url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/items/{item_id}:/{remote_file_path}:/content"
        headers = {"Authorization": f"Bearer {token}"}
        local_file = Path(local_file_path)
        file_size = local_file.stat().st_size
        logger.info("File size for %s: %d bytes", local_file_path, file_size)
        # Check the file size, because the limit is 4MB to use the PUT method
        if file_size >= 4 * 1024 * 1024:
            logger.info("File size is too big for: %s (4MB max)", local_file_path)
            return False
        # Read the file content
        with local_file.open("rb") as file:
            file_content = file.read()
        # Send the file
        try:
            response = requests.put(url, headers=headers, data=file_content, timeout=1000)
            response.raise_for_status()  # 200 or 201
        except requests.exceptions.HTTPError as err:
            logger.warning("HTTP Error occurred: %s", err)
        except requests.exceptions.RequestException as err:
            logger.warning("An error occurred: %s", err)
        else:
            return True
        return False
