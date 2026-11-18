from typing import Any

from assets_guardian.core.clients.http_client import HttpClient
from assets_guardian.core.domain.ports.client import IClientProvider
from assets_guardian.core.domain.registry.client_registry import ClientProviderRegistry
from assets_guardian.plugins.gitlab.constants import SOURCE_NAME


@ClientProviderRegistry.register(SOURCE_NAME)
class GitlabClientProvider(IClientProvider):
    """Client provider for GitLab using HttpClient."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initializes the provider with the instance configuration.

        Args:
            config: Configuration dictionary containing the URL and credentials.
        """
        self.__config = config

    def instantiate_client(self) -> HttpClient:
        """Returns an HttpClient configured with GitLab credentials.

        Returns:
            A ready-to-use HttpClient instance.
        """
        credentials = self.__config.get("credentials", {})
        token = credentials.get("personnal_access_token") or self.__config.get("token", "")

        base_url = self.__config.get("url", "").rstrip("/")
        sslVerify = self.__config.get("ssl", True)

        headers = {"Authorization": f"Bearer {token}"}

        return HttpClient(base_url=base_url, headers=headers, sslVerify=sslVerify)

    def health_check(self) -> bool:
        """Verifies that the connection to GitLab works and the token is valid.

        Returns:
            True if the connection is operational, False otherwise.
        """
        try:
            client = self.instantiate_client()
            # The /user endpoint validates that the token is functional
            response = client.get("/user")
        except Exception:
            return False
        else:
            return response.status_code == 200
