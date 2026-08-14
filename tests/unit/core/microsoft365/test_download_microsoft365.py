"""Tests for download_microsoft365: resolve_location_path and DownloadMicrosoft365."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.domain.models.location import Location
from assets_guardian.core.microsoft365.download_microsoft365 import (
    DownloadMicrosoft365,
    resolve_location_path,
)

MODULE = "assets_guardian.core.microsoft365.download_microsoft365"


@pytest.fixture
def ctx(tmp_path):
    context = MagicMock(spec=Context)
    context.app_config.cache.cache_dir = str(tmp_path)
    return context


@pytest.fixture
def downloader():
    return DownloadMicrosoft365(MagicMock(), MagicMock(), "Site A/Drive A/Folder/file.yml")


# ---------------------------------------------------------------------------
# resolve_location_path
# ---------------------------------------------------------------------------


def test_resolve_location_path_local_returns_clean_path(ctx):
    location = MagicMock(
        spec=Location, is_local=True, is_remote=False, clean_path="/local/file.yml"
    )

    result = resolve_location_path(ctx, location, "cache.yml")

    assert result == "/local/file.yml"


def test_resolve_location_path_neither_local_nor_remote_returns_none(ctx):
    location = MagicMock(spec=Location, is_local=False, is_remote=False)

    result = resolve_location_path(ctx, location, "cache.yml")

    assert result is None


def test_resolve_location_path_remote_cache_hit_skips_download(ctx, tmp_path):
    location = MagicMock(spec=Location, is_local=False, is_remote=True)
    cached_file = tmp_path / "cache.yml"
    cached_file.write_text("cached content")

    with patch(f"{MODULE}.ResolvePathMicrosoft365.from_context") as mock_from_context:
        result = resolve_location_path(ctx, location, "cache.yml")

    assert result == str(cached_file)
    mock_from_context.assert_not_called()


def test_resolve_location_path_remote_resolver_none_returns_none(ctx):
    location = MagicMock(spec=Location, is_local=False, is_remote=True)

    with patch(f"{MODULE}.ResolvePathMicrosoft365.from_context", return_value=None):
        result = resolve_location_path(ctx, location, "cache.yml")

    assert result is None


def test_resolve_location_path_remote_pull_success_returns_cached_path(ctx, tmp_path):
    location = MagicMock(spec=Location, is_local=False, is_remote=True)
    resolver = MagicMock(target_path="Site/Drive/Folder/file.yml", graph=MagicMock())

    with (
        patch(f"{MODULE}.ResolvePathMicrosoft365.from_context", return_value=resolver),
        patch(f"{MODULE}.DownloadMicrosoft365") as mock_downloader_cls,
    ):
        mock_downloader_cls.return_value.pull_report.return_value = True

        result = resolve_location_path(ctx, location, "cache.yml")

    expected_path = str(tmp_path / "cache.yml")
    assert result == expected_path
    mock_downloader_cls.return_value.pull_report.assert_called_once_with(expected_path)


def test_resolve_location_path_remote_pull_failure_returns_none(ctx):
    location = MagicMock(spec=Location, is_local=False, is_remote=True)
    resolver = MagicMock(target_path="Site/Drive/Folder/file.yml", graph=MagicMock())

    with (
        patch(f"{MODULE}.ResolvePathMicrosoft365.from_context", return_value=resolver),
        patch(f"{MODULE}.DownloadMicrosoft365") as mock_downloader_cls,
    ):
        mock_downloader_cls.return_value.pull_report.return_value = False

        result = resolve_location_path(ctx, location, "cache.yml")

    assert result is None


# ---------------------------------------------------------------------------
# DownloadMicrosoft365.__init__
# ---------------------------------------------------------------------------


def test_init_sets_attributes():
    graph = MagicMock()
    resolver = MagicMock()

    downloader = DownloadMicrosoft365(graph, resolver, "target/path.yml")

    assert downloader.graph is graph
    assert downloader.resolver is resolver
    assert downloader.target_path == "target/path.yml"


# ---------------------------------------------------------------------------
# get_drive_item_content
# ---------------------------------------------------------------------------


def test_get_drive_item_content_returns_awaited_content(downloader):
    content = b"file bytes"
    downloader.graph._user_client.drives.by_drive_id.return_value.items.by_drive_item_id.return_value.content.get = AsyncMock(
        return_value=content
    )

    result = asyncio.run(downloader.get_drive_item_content("drive-1", "item-1"))

    assert result == content
    downloader.graph._user_client.drives.by_drive_id.assert_called_once_with("drive-1")


# ---------------------------------------------------------------------------
# pull_item
# ---------------------------------------------------------------------------


def test_pull_item_downloads_content_when_found(downloader, tmp_path):
    item = MagicMock(id="item-1")
    item.name = "file.yml"
    downloader.resolver.get_children_drive_items = AsyncMock(return_value=MagicMock(value=[item]))
    downloader.get_drive_item_content = AsyncMock(return_value=b"content")
    local_path = tmp_path / "downloaded.yml"

    result = asyncio.run(downloader.pull_item("drive-1", "folder-1", "file.yml", str(local_path)))

    assert result is True
    assert local_path.read_bytes() == b"content"
    downloader.get_drive_item_content.assert_called_once_with("drive-1", "item-1")


def test_pull_item_returns_false_when_file_not_found(downloader, tmp_path):
    other_item = MagicMock()
    other_item.name = "other.yml"
    downloader.resolver.get_children_drive_items = AsyncMock(
        return_value=MagicMock(value=[other_item])
    )

    result = asyncio.run(
        downloader.pull_item("drive-1", "folder-1", "file.yml", str(tmp_path / "x.yml"))
    )

    assert result is False


def test_pull_item_returns_false_when_children_falsy(downloader, tmp_path):
    downloader.resolver.get_children_drive_items = AsyncMock(return_value=None)

    result = asyncio.run(
        downloader.pull_item("drive-1", "folder-1", "file.yml", str(tmp_path / "x.yml"))
    )

    assert result is False


# ---------------------------------------------------------------------------
# pull_report
# ---------------------------------------------------------------------------


def test_pull_report_downloads_using_resolved_path(downloader, tmp_path):
    downloader.resolver.resolve_target_path = AsyncMock(
        return_value=("site-1", "drive-1", "folder-1")
    )
    downloader.pull_item = AsyncMock(return_value=True)
    local_path = str(tmp_path / "cached.yml")

    result = downloader.pull_report(local_path)

    assert result is True
    downloader.resolver.resolve_target_path.assert_called_once_with("Site A/Drive A/Folder")
    downloader.pull_item.assert_called_once_with("drive-1", "folder-1", "file.yml", local_path)


def test_pull_report_returns_false_when_pull_item_fails(downloader, tmp_path):
    downloader.resolver.resolve_target_path = AsyncMock(
        return_value=("site-1", "drive-1", "folder-1")
    )
    downloader.pull_item = AsyncMock(return_value=False)

    result = downloader.pull_report(str(tmp_path / "cached.yml"))

    assert result is False
