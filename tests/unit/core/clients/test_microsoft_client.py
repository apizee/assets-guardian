"""Tests for MicrosoftGraph, the Microsoft Graph SDK wrapper."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.identity import ClientSecretCredential, DeviceCodeCredential

from assets_guardian.core.clients.microsoft_client import MicrosoftGraph

MODULE = "assets_guardian.core.clients.microsoft_client"


@pytest.fixture
def graph():
    """A MicrosoftGraph instance built without running __init__, so no real Azure/Graph
    SDK object is ever created. Business logic is tested in full isolation this way.
    Defaults to a ClientSecretCredential (organization-info) code path.
    """
    instance = MicrosoftGraph.__new__(MicrosoftGraph)
    instance._client_id = "client-id"
    instance._graph_scopes = ["scope"]
    instance._credentials = MagicMock(spec=ClientSecretCredential)
    instance._user_client = MagicMock()
    return instance


@pytest.fixture
def device_code_graph(graph):
    """Same as `graph`, but using a DeviceCodeCredential (current-user-info) code path."""
    graph._credentials = MagicMock(spec=DeviceCodeCredential)
    return graph


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_missing_tenant_id():
    with pytest.raises(ValueError, match="Tenant ID is required"):
        MicrosoftGraph(
            tenant_id="",
            client_id="c",
            client_secret="s",  # noqa: S106
            graph_scopes=["scope"],
        )


def test_init_missing_client_id():
    with pytest.raises(ValueError, match="Client ID is required"):
        MicrosoftGraph(
            tenant_id="t",
            client_id="",
            client_secret="s",  # noqa: S106
            graph_scopes=["scope"],
        )


def test_init_missing_graph_scopes():
    with pytest.raises(ValueError, match="Graph scopes are required"):
        MicrosoftGraph(
            tenant_id="t",
            client_id="c",
            client_secret="s",  # noqa: S106
            graph_scopes=[],
        )


def test_init_uses_client_secret_credential_when_secret_provided():
    with (
        patch(f"{MODULE}.GraphServiceClient") as mock_graph_client,
        patch(f"{MODULE}.ClientSecretCredential") as mock_cred,
    ):
        graph_instance = MicrosoftGraph(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",  # noqa: S106
            graph_scopes=["scope"],
        )

    mock_cred.assert_called_once_with("tenant", "client", "secret")
    mock_graph_client.assert_called_once_with(mock_cred.return_value, ["scope"])
    assert graph_instance._credentials is mock_cred.return_value


def test_init_uses_device_code_credential_when_no_secret():
    with (
        patch(f"{MODULE}.GraphServiceClient"),
        patch(f"{MODULE}.DeviceCodeCredential") as mock_cred,
    ):
        graph_instance = MicrosoftGraph(
            tenant_id="tenant",
            client_id="client",
            client_secret="",
            graph_scopes=["scope"],
        )

    mock_cred.assert_called_once_with("client", tenant_id="tenant")
    assert graph_instance._credentials is mock_cred.return_value


# ---------------------------------------------------------------------------
# get_token
# ---------------------------------------------------------------------------


def test_get_token_returns_token_string(graph):
    graph._credentials.get_token.return_value = MagicMock(token="abc123")  # noqa: S106

    result = asyncio.run(graph.get_token())

    assert result == "abc123"
    graph._credentials.get_token.assert_called_once_with("scope")


# ---------------------------------------------------------------------------
# check_requirements -- current user / organization info resolution
# ---------------------------------------------------------------------------


def test_check_requirements_device_code_no_user_returns_false(device_code_graph):
    device_code_graph._user_client.me.get = AsyncMock(return_value=None)

    result = asyncio.run(device_code_graph.check_requirements())

    assert result is False


def test_check_requirements_client_secret_no_org_returns_false(graph):
    graph._user_client.organization.get = AsyncMock(return_value=None)

    result = asyncio.run(graph.check_requirements())

    assert result is False


def test_check_requirements_client_secret_empty_org_value_returns_false(graph):
    graph._user_client.organization.get = AsyncMock(return_value=MagicMock(value=[]))

    result = asyncio.run(graph.check_requirements())

    assert result is False


def _mock_empty_permissions(target_graph):
    """Wires the granted-permissions chain to resolve to an empty list."""
    sp_result = MagicMock(value=[])
    target_graph._user_client.service_principals.with_url.return_value.get = AsyncMock(
        return_value=sp_result
    )


def test_check_requirements_device_code_user_found_missing_permissions(device_code_graph):
    user = MagicMock(
        id="1", display_name="Bob", mail="bob@example.com", user_principal_name="bob@example.com"
    )
    user.company_name = "Acme"
    device_code_graph._user_client.me.get = AsyncMock(return_value=user)
    _mock_empty_permissions(device_code_graph)

    with patch(f"{MODULE}.load_yaml_config", return_value={"paths": {}}):
        result = asyncio.run(device_code_graph.check_requirements())

    assert result is False


def test_check_requirements_client_secret_org_found_success(graph):
    tenant = MagicMock(id="tid", display_name="Tenant")
    graph._user_client.organization.get = AsyncMock(return_value=MagicMock(value=[tenant]))
    _mock_empty_permissions(graph)

    required = graph._MicrosoftGraph__required_permissions({"paths": {}})
    with (
        patch(f"{MODULE}.load_yaml_config", return_value={"paths": {}}),
        patch.object(
            graph, "_MicrosoftGraph__get_granted_permissions", AsyncMock(return_value=required)
        ),
    ):
        result = asyncio.run(graph.check_requirements())

    assert result is True


# ---------------------------------------------------------------------------
# __get_granted_permissions / __resolve_app_role_name (private, exercised directly)
# ---------------------------------------------------------------------------


def test_get_granted_permissions_no_service_principal_returns_empty(graph):
    graph._user_client.service_principals.with_url.return_value.get = AsyncMock(
        return_value=MagicMock(value=[])
    )

    result = asyncio.run(graph._MicrosoftGraph__get_granted_permissions())

    assert result == []


def test_get_granted_permissions_no_assignments_returns_empty(graph):
    sp = MagicMock(value=[MagicMock(id="sp-1")])
    graph._user_client.service_principals.with_url.return_value.get = AsyncMock(return_value=sp)
    graph._user_client.service_principals.by_service_principal_id.return_value.app_role_assignments.get = AsyncMock(
        return_value=None
    )

    result = asyncio.run(graph._MicrosoftGraph__get_granted_permissions())

    assert result == []


def test_get_granted_permissions_resolves_role_names(graph):
    sp = MagicMock(value=[MagicMock(id="sp-1")])
    graph._user_client.service_principals.with_url.return_value.get = AsyncMock(return_value=sp)

    assignment = MagicMock(resource_id="res-1", app_role_id="role-guid")
    assignments = MagicMock(value=[assignment])
    graph._user_client.service_principals.by_service_principal_id.return_value.app_role_assignments.get = AsyncMock(
        return_value=assignments
    )

    resource_sp = MagicMock(app_roles=[MagicMock(id="role-guid", value="User.Read.All")])
    graph._user_client.service_principals.by_service_principal_id.return_value.get = AsyncMock(
        return_value=resource_sp
    )

    result = asyncio.run(graph._MicrosoftGraph__get_granted_permissions())

    assert result == ["User.Read.All"]


def test_resolve_app_role_name_no_matching_role_returns_guid(graph):
    assignment = MagicMock(resource_id="res-1", app_role_id="unknown-guid")
    resource_sp = MagicMock(app_roles=[MagicMock(id="other-guid", value="Some.Permission")])
    graph._user_client.service_principals.by_service_principal_id.return_value.get = AsyncMock(
        return_value=resource_sp
    )

    result = asyncio.run(graph._MicrosoftGraph__resolve_app_role_name(assignment, {}))

    assert result == "unknown-guid"


def test_resolve_app_role_name_uses_cache_when_resource_already_resolved(graph):
    assignment = MagicMock(resource_id="res-1", app_role_id="role-guid")
    cache = {"res-1": [MagicMock(id="role-guid", value="Cached.Permission")]}

    result = asyncio.run(graph._MicrosoftGraph__resolve_app_role_name(assignment, cache))

    assert result == "Cached.Permission"
    graph._user_client.service_principals.by_service_principal_id.assert_not_called()


def test_resolve_app_role_name_missing_resource_sp_caches_empty_roles(graph):
    assignment = MagicMock(resource_id="res-1", app_role_id="role-guid")
    graph._user_client.service_principals.by_service_principal_id.return_value.get = AsyncMock(
        return_value=None
    )
    cache: dict = {}

    result = asyncio.run(graph._MicrosoftGraph__resolve_app_role_name(assignment, cache))

    assert result == "role-guid"
    assert cache["res-1"] == []


# ---------------------------------------------------------------------------
# __required_permissions / __has_remote_path
# ---------------------------------------------------------------------------


def test_required_permissions_without_email_or_remote_path(graph):
    perms = graph._MicrosoftGraph__required_permissions({"paths": {}})

    assert "Mail.Send" not in perms
    assert "Sites.ReadWrite.All" not in perms
    assert "User.Read.All" in perms


def test_required_permissions_with_notification_email(graph):
    perms = graph._MicrosoftGraph__required_permissions({"notification_email": ["a@b.com"]})

    assert "Mail.Send" in perms


def test_required_permissions_with_remote_path(graph):
    raw_config = {"paths": {"rules_config": "remote:site/drive/file.yml"}}

    perms = graph._MicrosoftGraph__required_permissions(raw_config)

    assert "Sites.ReadWrite.All" in perms


def test_has_remote_path_true_when_prefixed_remote(graph):
    assert (
        graph._MicrosoftGraph__has_remote_path(
            {"paths": {"config": "remote:instance:site/drive/file.yml"}}
        )
        is True
    )


def test_has_remote_path_false_when_only_local(graph):
    assert (
        graph._MicrosoftGraph__has_remote_path({"paths": {"config": "local:./config.yml"}}) is False
    )


def test_has_remote_path_ignores_non_string_values(graph):
    assert graph._MicrosoftGraph__has_remote_path({"paths": {"config": 123}}) is False
