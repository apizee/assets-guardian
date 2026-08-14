import logging
from typing import TYPE_CHECKING, Any

from kiota_abstractions.base_request_configuration import RequestConfiguration
from msgraph.generated.groups.groups_request_builder import GroupsRequestBuilder
from msgraph.generated.role_management.directory.role_assignments.role_assignments_request_builder import (  # noqa: E501
    RoleAssignmentsRequestBuilder,
)
from msgraph.generated.role_management.directory.role_definitions.role_definitions_request_builder import (  # noqa: E501
    RoleDefinitionsRequestBuilder,
)
from msgraph.generated.users.users_request_builder import UsersRequestBuilder
from msgraph.graph_service_client import GraphServiceClient

from assets_guardian.core.clients.microsoft_client import MicrosoftGraph
from assets_guardian.plugins.microsoft365.license_utils import get_license_name

if TYPE_CHECKING:
    from msgraph.generated.models.user_collection_response import UserCollectionResponse


logger = logging.getLogger(__name__)


class Microsoft365Repository:
    """Port: Raw data repository access.

    Defines the contract for retrieving raw data
    from an external source (API, database, etc.).
    """

    _user_client: GraphServiceClient

    def __init__(self, client: MicrosoftGraph) -> None:
        self._user_client = client._user_client

    def user_has_mfa(self, auth_methods: Any) -> bool:
        mfa_methods = {
            "#microsoft.graph.microsoftAuthenticatorAuthenticationMethod",
            "#microsoft.graph.fido2AuthenticationMethod",
            "#microsoft.graph.windowsHelloForBusinessAuthenticationMethod",
            "#microsoft.graph.phoneAuthenticationMethod",
        }
        for method in auth_methods.value:
            odata_type = method.odata_type
            if (
                odata_type == "#microsoft.graph.phoneAuthenticationMethod"
                and method.sms_sign_in_state == "enabled"
            ):
                return True
            if odata_type in mfa_methods:
                return True
        return False

    async def get_raw_users(self) -> list[dict[str, Any]]:
        """Get all users (name, id, email and company)"""
        # Add custom headers for the request to get all users count
        request_configuration: Any = RequestConfiguration()
        request_configuration.headers.add("ConsistencyLevel", "eventual")
        total_users = await self._user_client.users.count.get(
            request_configuration=request_configuration
        )

        # Only request specific properties using $select
        query_params: Any = UsersRequestBuilder.UsersRequestBuilderGetQueryParameters(
            select=[
                "id",
                "accountEnabled",
                "displayName",
                "mail",
                "userPrincipalName",
                "companyName",
                "jobTitle",
                "userType",
                "createdDateTime",
                "lastPasswordChangeDateTime",
                "signInActivity",
            ],
            top=total_users,
        )
        # Add custom headers for the request
        request_configuration = UsersRequestBuilder.UsersRequestBuilderGetRequestConfiguration(
            query_parameters=query_params,
        )
        # Send request to Microsoft Graph (equivalent to GET /users)
        result: UserCollectionResponse | None = await self._user_client.users.get(
            request_configuration=request_configuration
        )
        # Mapping user object to a dict
        if not result:
            return []
        roles_definitions = await self.get_raw_roles_definitions()

        users = []
        can_fetch_mfa = True
        for user in result.value or []:
            if not user.id:
                continue
            user_roles: list[str] = []
            if roles_definitions:
                user_roles = await self.get_raw_roles_assignments(user.id, roles_definitions)

            user_licenses = await self.get_raw_licenses(user.id)

            mfa_enabled = None
            if can_fetch_mfa:
                try:
                    mfa_enabled = self.user_has_mfa(
                        await self._user_client.users.by_user_id(
                            user.id
                        ).authentication.methods.get()
                    )
                except Exception:
                    can_fetch_mfa = False
                    logger.warning(
                        "Unable to fetch MFA (insufficient permissions). Skipping for all users."
                    )
            users.append(
                {
                    "id": user.id,
                    "accountEnabled": user.account_enabled,
                    "displayName": user.display_name,
                    "email": user.mail or user.user_principal_name,
                    "companyName": user.company_name,
                    "jobTitle": user.job_title,
                    "userType": user.user_type,
                    "createdDateTime": user.created_date_time,
                    "lastPasswordChangeDateTime": user.last_password_change_date_time,
                    "signInActivity": user.sign_in_activity.last_sign_in_date_time
                    if user.sign_in_activity
                    else None,
                    "mfaEnabled": mfa_enabled,
                    "roles": user_roles,
                    "licenses": user_licenses,
                }
            )
        logger.info("Retrieved %d users from Microsoft 365.", len(users))
        return users

    async def get_raw_roles_definitions(self) -> dict[str, str]:
        """Get a mapping of role definition id to role name."""
        roles_definitions: dict[str, str] = {}
        try:
            query_params = (
                RoleDefinitionsRequestBuilder.RoleDefinitionsRequestBuilderGetQueryParameters(
                    select=["id", "displayName"],
                )
            )
            request_configuration = RequestConfiguration(query_parameters=query_params)
            roles_result = await self._user_client.role_management.directory.role_definitions.get(
                request_configuration=request_configuration
            )
            for role_definition in roles_result.value or [] if roles_result else []:
                if role_definition.id and role_definition.display_name:
                    roles_definitions[str(role_definition.id)] = str(role_definition.display_name)
        except Exception:
            logger.warning("Unable to fetch role definitions (insufficient permissions).")
        return roles_definitions

    async def get_raw_roles_assignments(
        self, user_id: str, roles_definitions: dict[str, str]
    ) -> list[str]:
        # https://graph.microsoft.com/v1.0/roleManagement/directory/roleAssignments?$filter=principalId eq '{id}'&$select=roleDefinitionId  # noqa: E501
        try:
            query_params = (
                RoleAssignmentsRequestBuilder.RoleAssignmentsRequestBuilderGetQueryParameters(
                    filter="principalId eq '" + user_id + "'",
                    select=["roleDefinitionId"],
                )
            )
            request_configuration = RequestConfiguration(query_parameters=query_params)
            assignments_result = (
                await self._user_client.role_management.directory.role_assignments.get(
                    request_configuration=request_configuration
                )
            )
            assignments = (assignments_result.value or []) if assignments_result else []
            return [
                roles_definitions[a.role_definition_id]
                for a in assignments
                if a.role_definition_id in roles_definitions
            ]
        except Exception:
            logger.warning("Unable to fetch role assignments for user %s.", user_id)
            return []

    async def get_raw_groups(self) -> list[dict[str, Any]]:
        """Get all groups (name and id)"""
        query_params = GroupsRequestBuilder.GroupsRequestBuilderGetQueryParameters(
            select=[
                "id",
                "displayName",
                "description",
                "visibility",
                "groupTypes",
                "createdDateTime",
            ],
        )
        request_configuration = GroupsRequestBuilder.GroupsRequestBuilderGetRequestConfiguration(
            query_parameters=query_params,
        )
        try:
            result = await self._user_client.groups.get(request_configuration=request_configuration)
        except Exception as e:
            logger.warning("Unable to fetch groups: %s", e)
            return []
        if result:
            groups = [
                {
                    "id": group.id,
                    "name": group.display_name,
                    "description": group.description,
                    "visibility": group.visibility,
                    "groupTypes": group.group_types,
                    "createdDateTime": group.created_date_time,
                }
                for group in (result.value or [])
            ]
            logger.info("Retrieved %d groups from Microsoft 365.", len(groups))
            return groups
        return []

    async def get_raw_roles(self) -> list[dict[str, Any]]:
        """Get all Azure AD role definitions"""
        query_params = (
            RoleDefinitionsRequestBuilder.RoleDefinitionsRequestBuilderGetQueryParameters(
                select=["id", "displayName", "description", "isBuiltIn", "isEnabled"],
            )
        )
        request_configuration = RequestConfiguration(
            query_parameters=query_params,
        )
        result = await self._user_client.role_management.directory.role_definitions.get(
            request_configuration=request_configuration
        )
        if result:
            roles = [
                {
                    "id": role.id,
                    "name": role.display_name,
                    "description": role.description,
                    "isBuiltIn": role.is_built_in,
                    "isEnabled": role.is_enabled,
                }
                for role in (result.value or [])
            ]
            logger.info("Retrieved %d role definitions from Microsoft 365.", len(roles))
            return roles
        return []

    async def get_raw_group_members(self, group_id: str) -> list[dict[str, Any]]:
        """Get members of a specific group."""
        try:
            result = await self._user_client.groups.by_group_id(group_id).members.get()
        except Exception as e:
            logger.warning("Unable to fetch members for group %s: %s", group_id, e)
            return []
        if result:
            return [
                {
                    "id": member.id,
                    "displayName": getattr(member, "display_name", None),
                    "mail": getattr(member, "mail", None),
                    "userPrincipalName": getattr(member, "user_principal_name", None),
                }
                for member in (result.value or [])
            ]
        return []

    async def get_raw_assets_applications(self) -> list[dict[str, Any]]:
        """Get all Azure AD app registrations"""
        try:
            result = await self._user_client.applications.with_url(
                "https://graph.microsoft.com/v1.0/applications"
                "?$select=id,appId,displayName,description,createdDateTime"
                ",passwordCredentials,keyCredentials"
            ).get()
        except Exception as e:
            logger.warning("Unable to fetch app registrations: %s", e)
            return []
        if not result:
            return []
        sp_enabled = await self.get_raw_application_enabled_status()

        apps = [
            {
                "id": app.id,
                "appId": app.app_id,
                "name": app.display_name,
                "description": app.description,
                "createdDateTime": app.created_date_time,
                "accountEnabled": sp_enabled.get(app.app_id) if app.app_id else None,
            }
            for app in (result.value or [])
        ]
        logger.info("Retrieved %d app registrations from Microsoft 365.", len(apps))
        return apps

    async def get_raw_assets_licenses(self) -> list[dict[str, Any]]:
        """Get all Azure AD subscribed licenses (SKUs)"""
        try:
            result = await self._user_client.subscribed_skus.get()
        except Exception as e:
            logger.warning("Unable to fetch subscribed licenses: %s", e)
            return []
        if not result:
            return []

        licenses = [
            {
                "id": str(sku.sku_id) if sku.sku_id else None,
                "name": get_license_name(sku.sku_part_number)
                if sku.sku_part_number
                else sku.sku_part_number,
                "capabilityStatus": sku.capability_status,
                "accountEnabled": sku.capability_status == "Enabled",
                "consumedUnits": sku.consumed_units,
                "enabledUnits": sku.prepaid_units.enabled if sku.prepaid_units else None,
            }
            for sku in (result.value or [])
        ]
        logger.info("Retrieved %d licenses from Microsoft 365.", len(licenses))
        return licenses

    async def get_raw_licenses(self, user_id: str) -> list[str]:
        """Get licenses assigned to a specific user."""
        licenses = []
        try:
            result = await self._user_client.users.by_user_id(user_id).license_details.get()
        except Exception as e:
            logger.warning("Unable to fetch licenses for user %s: %s", user_id, e)
            return []
        if not result:
            return []
        for license_details in result.value or []:
            if license_details.sku_part_number:
                licenses.append(get_license_name(license_details.sku_part_number))
        logger.debug("Retrieved %d licenses for user %s.", len(licenses), user_id)
        return licenses

    async def get_raw_application_enabled_status(self) -> dict[str, bool]:
        sp_enabled: dict[str, bool] = {}
        try:
            sp_result = await self._user_client.service_principals.with_url(
                "https://graph.microsoft.com/v1.0/servicePrincipals"
                "?$select=appId,accountEnabled&$top=999"
            ).get()
            for sp in (sp_result.value or []) if sp_result else []:
                if sp.app_id is not None:
                    sp_enabled[sp.app_id] = bool(sp.account_enabled)
        except Exception as e:
            logger.warning("Unable to fetch service principals: %s", e)
        return sp_enabled

    async def get_raw_accesses(self) -> list[dict[str, Any]]:
        # ARCH-LIMIT: accesses require N+1 calls per user/app and are built in the collector.
        return []
