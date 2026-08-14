import logging
from typing import Any

from azure.identity import ClientSecretCredential, DeviceCodeCredential
from msgraph.generated.users.item.user_item_request_builder import UserItemRequestBuilder
from msgraph.graph_service_client import GraphServiceClient

from assets_guardian.core.config.loader import load_yaml_config

logger = logging.getLogger(__name__)


class MicrosoftGraph:
    """Microsoft Graph SDK core class"""

    _graph_scopes: list[str]
    _credentials: DeviceCodeCredential | ClientSecretCredential
    _user_client: GraphServiceClient

    def __init__(
        self, tenant_id: str, client_id: str, client_secret: str, graph_scopes: list[str]
    ) -> None:
        # Check if each attribute has a value
        if not tenant_id:
            raise ValueError("Tenant ID is required")
        if not client_id:
            raise ValueError("Client ID is required")
        if not graph_scopes:
            raise ValueError("Graph scopes are required")
        self._client_id = client_id
        self._graph_scopes = graph_scopes
        # Check if client_secret is empty, if so, use the device code flow
        if client_secret:
            self._credentials = ClientSecretCredential(tenant_id, client_id, client_secret)
        else:
            self._credentials = DeviceCodeCredential(client_id, tenant_id=tenant_id)
        self._user_client = GraphServiceClient(self._credentials, self._graph_scopes)

    async def get_token(self) -> str:
        """Get access token"""
        access_token = self._credentials.get_token(" ".join(self._graph_scopes))
        return access_token.token

    async def __get_current_user_info(self) -> dict[str, Any] | None:
        """Get the current connected user information (delegated permissions)."""
        query_params = UserItemRequestBuilder.UserItemRequestBuilderGetQueryParameters(
            select=["id", "displayName", "mail", "userPrincipalName"]
        )
        request_config = UserItemRequestBuilder.UserItemRequestBuilderGetRequestConfiguration(
            query_parameters=query_params
        )
        user = await self._user_client.me.get(request_configuration=request_config)
        if not user:
            return None
        return {
            "id": user.id,
            "name": user.display_name,
            "email": user.mail or user.user_principal_name,
            "company": user.company_name,
        }

    async def __get_current_organization_info(self) -> dict[str, Any] | None:
        """Get the current organization information (application permissions)."""
        org = await self._user_client.organization.get()
        if not org or not org.value:
            return None
        tenant = org.value[0]
        return {
            "id": tenant.id,
            "name": tenant.display_name,
            "email": None,
            "company": tenant.display_name,
        }

    async def __get_granted_permissions(self) -> list[str]:
        """Lists the Microsoft Graph permissions (app roles) granted to this app."""
        service_principal_id = await self.__get_own_service_principal_id()
        if service_principal_id is None:
            return []

        assignments = await self._user_client.service_principals.by_service_principal_id(
            service_principal_id
        ).app_role_assignments.get()
        if not assignments or not assignments.value:
            return []

        # Each assignment only references a role by GUID. Resolve it to a human-readable
        # permission name (e.g. "Sites.ReadWrite.All"), caching lookups per resource since
        # most assignments point to the same resource (Microsoft Graph itself).
        resource_roles_cache: dict[str, Any] = {}
        permission_names = []
        for assignment in assignments.value:
            permission_name = await self.__resolve_app_role_name(assignment, resource_roles_cache)
            permission_names.append(permission_name)
        return permission_names

    async def __get_own_service_principal_id(self) -> str | None:
        """Finds this app's own service principal ID in Microsoft Graph."""
        filter_url = (
            "https://graph.microsoft.com/v1.0/servicePrincipals"
            f"?$filter=appId eq '{self._client_id}'"
        )
        service_principals = await self._user_client.service_principals.with_url(filter_url).get()
        if not service_principals or not service_principals.value:
            return None
        return str(service_principals.value[0].id)

    async def __resolve_app_role_name(
        self, assignment: Any, resource_roles_cache: dict[str, Any]
    ) -> str:
        """Resolves an app role assignment's GUID into its human-readable permission name."""
        resource_id = str(assignment.resource_id)
        if resource_id not in resource_roles_cache:
            resource_roles_cache[resource_id] = await self.__fetch_resource_app_roles(resource_id)

        matching_role = next(
            (
                role
                for role in resource_roles_cache[resource_id]
                if str(role.id) == str(assignment.app_role_id)
            ),
            None,
        )
        return matching_role.value if matching_role else str(assignment.app_role_id)

    async def __fetch_resource_app_roles(self, resource_id: str) -> list[Any]:
        """Fetches the app roles (permission definitions) exposed by a resource."""
        resource_service_principal = await (
            self._user_client.service_principals.by_service_principal_id(resource_id).get()
        )
        if not resource_service_principal or not resource_service_principal.app_roles:
            return []
        return resource_service_principal.app_roles

    async def check_requirements(self) -> bool:
        """Verifies that the credentials can retrieve the current user or organization."""
        if isinstance(self._credentials, DeviceCodeCredential):
            info = await self.__get_current_user_info()
        else:
            info = await self.__get_current_organization_info()
        if info is None:
            return False

        granted_permissions = await self.__get_granted_permissions()
        logger.info("Granted permissions: %s", granted_permissions)

        raw_config = load_yaml_config("config/config.yml")
        required_permissions = self.__required_permissions(raw_config)
        missing_permissions = set(required_permissions) - set(granted_permissions)

        if missing_permissions:
            logger.warning("Missing permissions: %s", sorted(missing_permissions))
            return False

        return True

    def __required_permissions(self, raw_config: dict[str, Any]) -> list[str]:
        """Determines the Microsoft Graph permissions required by the current configuration."""
        required_permissions = [
            "UserAuthenticationMethod.Read.All",
            "Group.Read.All",
            "RoleManagement.Read.All",
            "User.Read.All",
            "GroupMember.Read.All",
            "Organization.Read.All",
            "AuditLog.Read.All",
            "Application.Read.All",
        ]

        if raw_config.get("notification_email", []):
            required_permissions.append("Mail.Send")

        if self.__has_remote_path(raw_config):
            required_permissions.append("Sites.ReadWrite.All")

        return required_permissions

    def __has_remote_path(self, raw_config: dict[str, Any]) -> bool:
        """Checks if any configured path uses the 'remote' prefix."""
        paths = raw_config.get("paths", {})
        for path_value in paths.values():
            if isinstance(path_value, str) and path_value.startswith("remote"):
                return True
        return False
