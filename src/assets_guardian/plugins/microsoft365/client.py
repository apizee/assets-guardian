import asyncio
import logging
from typing import Any

from assets_guardian.core.clients.microsoft_client import MicrosoftGraph
from assets_guardian.core.domain.ports.client import IClientProvider
from assets_guardian.core.domain.registry.client_registry import ClientProviderRegistry

from .constants import SOURCE_NAME

DEFAULT_SCOPES = ["https://graph.microsoft.com/.default"]

logger = logging.getLogger(__name__)


@ClientProviderRegistry.register(SOURCE_NAME)
class Microsoft365ClientProvider(IClientProvider):
    """Client provider for Microsoft 365 via Microsoft Graph."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.__config = config

    def instantiate_client(self) -> MicrosoftGraph:
        credentials = self.__config.get("credentials", {})
        return MicrosoftGraph(
            tenant_id=credentials.get("tenant_id"),
            client_id=credentials.get("application_id"),
            client_secret=credentials.get("client_secret"),
            graph_scopes=self.__config.get("scopes", DEFAULT_SCOPES),
        )

    def health_check(self) -> bool:
        try:
            client = self.instantiate_client()
            return asyncio.run(client.check_requirements())
        except Exception:
            return False
