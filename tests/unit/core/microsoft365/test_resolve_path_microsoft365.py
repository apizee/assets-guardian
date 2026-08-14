"""Tests for ResolvePathMicrosoft365, the SharePoint path-to-Graph-IDs resolver."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from assets_guardian.core.clients.microsoft_client import MicrosoftGraph
from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.domain.models.location import Location
from assets_guardian.core.microsoft365.resolve_path_microsoft365 import ResolvePathMicrosoft365

MODULE = "assets_guardian.core.microsoft365.resolve_path_microsoft365"


def _named_item(name: str, folder: bool = True) -> MagicMock:
    """Builds a fake Graph drive item with a `.name` attribute (can't be a constructor
    kwarg on Mock/MagicMock, since `name` is reserved there for the mock's own repr)."""
    item = MagicMock(folder=folder)
    item.name = name
    return item


@pytest.fixture
def resolver() -> ResolvePathMicrosoft365:
    return ResolvePathMicrosoft365(graph=MagicMock(), target_path="Site A/Drive A/Folder1/Folder2")


@pytest.fixture
def ctx() -> Context:
    context = MagicMock(spec=Context)
    context.app_config.integrations = {}
    return context


# ---------------------------------------------------------------------------
# from_context
# ---------------------------------------------------------------------------


def test_from_context_returns_none_when_no_location(ctx: Context) -> None:
    result = ResolvePathMicrosoft365.from_context(ctx, path=None)

    assert result is None


def test_from_context_returns_none_when_no_colon_in_path(ctx: Context) -> None:
    location = MagicMock(spec=Location, clean_path="/no/colon/here")

    result = ResolvePathMicrosoft365.from_context(ctx, path=location)

    assert result is None


def test_from_context_returns_none_when_instance_not_configured(ctx: Context) -> None:
    location = MagicMock(spec=Location, clean_path="instance1:Site A/Drive A/Folder")
    ctx.app_config.integrations = {"microsoft365": {}}

    result = ResolvePathMicrosoft365.from_context(ctx, path=location)

    assert result is None


def test_from_context_returns_none_when_client_is_not_microsoft_graph(ctx: Context) -> None:
    location = MagicMock(spec=Location, clean_path="instance1:Site A/Drive A/Folder")
    ctx.app_config.integrations = {"microsoft365": {"instance1": {"tenant_id": "t"}}}

    with patch(f"{MODULE}.ClientProviderRegistry") as mock_registry:
        provider = mock_registry.instantiates_clientprovider.return_value
        provider.instantiate_client.return_value = MagicMock()

        result = ResolvePathMicrosoft365.from_context(ctx, path=location)

    assert result is None


def test_from_context_success_returns_resolver(ctx: Context) -> None:
    location = MagicMock(spec=Location, clean_path="instance1:Site A/Drive A/Folder")
    ctx.app_config.integrations = {"microsoft365": {"instance1": {"tenant_id": "t"}}}
    fake_graph = MagicMock(spec=MicrosoftGraph)

    with patch(f"{MODULE}.ClientProviderRegistry") as mock_registry:
        provider = mock_registry.instantiates_clientprovider.return_value
        provider.instantiate_client.return_value = fake_graph

        result = ResolvePathMicrosoft365.from_context(ctx, path=location)

    assert result is not None
    assert result.graph is fake_graph
    assert result.target_path == "Site A/Drive A/Folder"
    mock_registry.instantiates_clientprovider.assert_called_once_with(
        "microsoft365", {"tenant_id": "t"}
    )


# ---------------------------------------------------------------------------
# get_sites / get_drives_by_site / get_drives_by_user
# ---------------------------------------------------------------------------


def test_get_sites_maps_result_when_present(resolver: ResolvePathMicrosoft365) -> None:
    site = MagicMock(id="s1", display_name="Site A")
    resolver.graph._user_client.sites.with_url.return_value.get = AsyncMock(
        return_value=MagicMock(value=[site])
    )

    result = asyncio.run(resolver.get_sites())

    assert result == [{"id": "s1", "name": "Site A"}]


def test_get_sites_returns_falsy_result_as_is(resolver: ResolvePathMicrosoft365) -> None:
    resolver.graph._user_client.sites.with_url.return_value.get = AsyncMock(return_value=None)

    result = asyncio.run(resolver.get_sites())

    assert result is None


def test_get_drives_by_site_maps_result_when_present(resolver: ResolvePathMicrosoft365) -> None:
    drive = _named_item("Drive A")
    drive.id = "d1"
    resolver.graph._user_client.sites.by_site_id.return_value.drives.get = AsyncMock(
        return_value=MagicMock(value=[drive])
    )

    result = asyncio.run(resolver.get_drives_by_site("site-1"))

    assert result == [{"id": "d1", "name": "Drive A"}]
    resolver.graph._user_client.sites.by_site_id.assert_called_once_with("site-1")


def test_get_drives_by_site_returns_falsy_result_as_is(
    resolver: ResolvePathMicrosoft365,
) -> None:
    resolver.graph._user_client.sites.by_site_id.return_value.drives.get = AsyncMock(
        return_value=None
    )

    result = asyncio.run(resolver.get_drives_by_site("site-1"))

    assert result is None


def test_get_drives_by_user_maps_result_when_present(resolver: ResolvePathMicrosoft365) -> None:
    drive = _named_item("Drive A")
    drive.id = "d1"
    resolver.graph._user_client.users.by_user_id.return_value.drives.get = AsyncMock(
        return_value=MagicMock(value=[drive])
    )

    result = asyncio.run(resolver.get_drives_by_user("user-1"))

    assert result == [{"id": "d1", "name": "Drive A"}]


def test_get_drives_by_user_returns_falsy_result_as_is(
    resolver: ResolvePathMicrosoft365,
) -> None:
    resolver.graph._user_client.users.by_user_id.return_value.drives.get = AsyncMock(
        return_value=None
    )

    result = asyncio.run(resolver.get_drives_by_user("user-1"))

    assert result is None


# ---------------------------------------------------------------------------
# get_root_drive_items / get_children_drive_items / get_drive_item
# ---------------------------------------------------------------------------


def test_get_root_drive_items_returns_value_list_when_present(
    resolver: ResolvePathMicrosoft365,
) -> None:
    items = [MagicMock(), MagicMock()]
    resolver.graph._user_client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.children.get = AsyncMock(
        return_value=MagicMock(value=items)
    )

    result = asyncio.run(resolver.get_root_drive_items("drive-1"))

    assert result == items
    resolver.graph._user_client.drives.by_drive_id.assert_called_once_with("drive-1")
    resolver.graph._user_client.drives.by_drive_id.return_value.items.by_drive_item_id.assert_called_once_with(
        "root"
    )


def test_get_root_drive_items_returns_falsy_result_as_is(
    resolver: ResolvePathMicrosoft365,
) -> None:
    resolver.graph._user_client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.children.get = AsyncMock(
        return_value=None
    )

    result = asyncio.run(resolver.get_root_drive_items("drive-1"))

    assert result is None


def test_get_children_drive_items_returns_awaited_children(
    resolver: ResolvePathMicrosoft365,
) -> None:
    children = MagicMock()
    resolver.graph._user_client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.children.get = AsyncMock(
        return_value=children
    )

    result = asyncio.run(resolver.get_children_drive_items("drive-1", "item-1"))

    assert result is children
    resolver.graph._user_client.drives.by_drive_id.return_value.items.by_drive_item_id.assert_called_once_with(
        "item-1"
    )


def test_get_drive_item_returns_awaited_item(resolver: ResolvePathMicrosoft365) -> None:
    item = MagicMock()
    resolver.graph._user_client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.get = AsyncMock(
        return_value=item
    )

    result = asyncio.run(resolver.get_drive_item("drive-1", "item-1"))

    assert result is item


# ---------------------------------------------------------------------------
# _resolve_site_id / _resolve_drive_id
# ---------------------------------------------------------------------------


def test_resolve_site_id_found(resolver: ResolvePathMicrosoft365) -> None:
    resolver.get_sites = AsyncMock(return_value=[{"id": "site-1", "name": "Site A"}])  # type: ignore[method-assign]

    result = asyncio.run(resolver._resolve_site_id("Site A"))  # type: ignore[attr-defined]

    assert result == "site-1"


def test_resolve_site_id_not_found_raises(resolver: ResolvePathMicrosoft365) -> None:
    resolver.get_sites = AsyncMock(return_value=[{"id": "site-1", "name": "Site A"}])  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="No SharePoint site found"):
        asyncio.run(resolver._resolve_site_id("Unknown"))  # type: ignore[attr-defined]


def test_resolve_site_id_handles_no_sites(resolver: ResolvePathMicrosoft365) -> None:
    resolver.get_sites = AsyncMock(return_value=None)  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="No SharePoint site found"):
        asyncio.run(resolver._resolve_site_id("Site A"))  # type: ignore[attr-defined]


def test_resolve_drive_id_found(resolver: ResolvePathMicrosoft365) -> None:
    resolver.get_drives_by_site = AsyncMock(return_value=[{"id": "drive-1", "name": "Drive A"}])  # type: ignore[method-assign]

    result = asyncio.run(resolver._resolve_drive_id("site-1", "Drive A"))  # type: ignore[attr-defined]

    assert result == "drive-1"


def test_resolve_drive_id_not_found_raises(resolver: ResolvePathMicrosoft365) -> None:
    resolver.get_drives_by_site = AsyncMock(return_value=[{"id": "drive-1", "name": "Drive A"}])  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="No drive found"):
        asyncio.run(resolver._resolve_drive_id("site-1", "Unknown"))  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _resolve_item_id
# ---------------------------------------------------------------------------


def test_resolve_item_id_walks_multi_level_path(resolver: ResolvePathMicrosoft365) -> None:
    folder1 = _named_item("Folder1")
    folder1.id = "id-1"
    folder2 = _named_item("Folder2")
    folder2.id = "id-2"

    resolver.get_root_drive_items = AsyncMock(return_value=[folder1])  # type: ignore[method-assign]
    resolver.get_children_drive_items = AsyncMock(  # type: ignore[method-assign]
        side_effect=[MagicMock(value=[folder2]), MagicMock(value=[])]
    )

    result = asyncio.run(resolver._resolve_item_id("drive-1", ["Folder1", "Folder2"]))  # type: ignore[attr-defined]

    assert result == "id-2"


def test_resolve_item_id_stops_when_children_falsy(resolver: ResolvePathMicrosoft365) -> None:
    folder1 = _named_item("Folder1")
    folder1.id = "id-1"

    resolver.get_root_drive_items = AsyncMock(return_value=[folder1])  # type: ignore[method-assign]
    resolver.get_children_drive_items = AsyncMock(return_value=None)  # type: ignore[method-assign]

    result = asyncio.run(resolver._resolve_item_id("drive-1", ["Folder1"]))  # type: ignore[attr-defined]

    assert result == "id-1"


def test_resolve_item_id_folder_not_found_raises(resolver: ResolvePathMicrosoft365) -> None:
    resolver.get_root_drive_items = AsyncMock(return_value=[])  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="No folder found"):
        asyncio.run(resolver._resolve_item_id("drive-1", ["Missing"]))  # type: ignore[attr-defined]


def test_resolve_item_id_ignores_non_folder_items(resolver: ResolvePathMicrosoft365) -> None:
    file_item = _named_item("Folder1", folder=False)
    resolver.get_root_drive_items = AsyncMock(return_value=[file_item])  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="No folder found"):
        asyncio.run(resolver._resolve_item_id("drive-1", ["Folder1"]))  # type: ignore[attr-defined]


def test_resolve_item_id_empty_folder_parts_raises(resolver: ResolvePathMicrosoft365) -> None:
    resolver.get_root_drive_items = AsyncMock(return_value=[])  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="Empty folder path"):
        asyncio.run(resolver._resolve_item_id("drive-1", []))  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# resolve_target_path
# ---------------------------------------------------------------------------


def test_resolve_target_path_chains_resolution_steps(resolver: ResolvePathMicrosoft365) -> None:
    resolver._resolve_site_id = AsyncMock(return_value="site-1")  # type: ignore[method-assign]
    resolver._resolve_drive_id = AsyncMock(return_value="drive-1")  # type: ignore[method-assign]
    resolver._resolve_item_id = AsyncMock(return_value="item-1")  # type: ignore[method-assign]

    result = asyncio.run(resolver.resolve_target_path("Site A/Drive A/Folder1/Folder2"))

    assert result == ("site-1", "drive-1", "item-1")
    resolver._resolve_site_id.assert_called_once_with("Site A")  # type: ignore[attr-defined]
    resolver._resolve_drive_id.assert_called_once_with("site-1", "Drive A")  # type: ignore[attr-defined]
    resolver._resolve_item_id.assert_called_once_with("drive-1", ["Folder1", "Folder2"])  # type: ignore[attr-defined]
