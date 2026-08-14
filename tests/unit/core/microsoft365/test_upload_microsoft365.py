"""Tests for upload_microsoft365: push_to_location and UploadMicrosoft365."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.domain.models.location import Location
from assets_guardian.core.microsoft365.upload_microsoft365 import (
    UploadMicrosoft365,
    push_to_location,
)

MODULE = "assets_guardian.core.microsoft365.upload_microsoft365"


@pytest.fixture
def uploader():
    return UploadMicrosoft365(MagicMock(), MagicMock(), "Site A/Drive A/Folder")


# ---------------------------------------------------------------------------
# push_to_location
# ---------------------------------------------------------------------------


def test_push_to_location_local_returns_true():
    location = MagicMock(spec=Location, is_local=True, is_remote=False)

    result = push_to_location(MagicMock(spec=Context), location, "/local/file.pdf")

    assert result is True


def test_push_to_location_neither_local_nor_remote_returns_false():
    location = MagicMock(spec=Location, is_local=False, is_remote=False)

    result = push_to_location(MagicMock(spec=Context), location, "/local/file.pdf")

    assert result is False


def test_push_to_location_remote_resolver_none_returns_false():
    location = MagicMock(spec=Location, is_local=False, is_remote=True)

    with patch(f"{MODULE}.ResolvePathMicrosoft365.from_context", return_value=None):
        result = push_to_location(MagicMock(spec=Context), location, "/local/file.pdf")

    assert result is False


def test_push_to_location_remote_success_delegates_to_uploader():
    location = MagicMock(spec=Location, is_local=False, is_remote=True)
    resolver = MagicMock(target_path="Site/Drive/Folder", graph=MagicMock())

    with (
        patch(f"{MODULE}.ResolvePathMicrosoft365.from_context", return_value=resolver),
        patch(f"{MODULE}.UploadMicrosoft365") as mock_uploader_cls,
    ):
        mock_uploader_cls.return_value.upload_report.return_value = True

        result = push_to_location(MagicMock(spec=Context), location, "/local/file.pdf")

    assert result is True
    mock_uploader_cls.return_value.upload_report.assert_called_once_with("/local/file.pdf")


def test_push_to_location_remote_failure_returns_false():
    location = MagicMock(spec=Location, is_local=False, is_remote=True)
    resolver = MagicMock(target_path="Site/Drive/Folder", graph=MagicMock())

    with (
        patch(f"{MODULE}.ResolvePathMicrosoft365.from_context", return_value=resolver),
        patch(f"{MODULE}.UploadMicrosoft365") as mock_uploader_cls,
    ):
        mock_uploader_cls.return_value.upload_report.return_value = False

        result = push_to_location(MagicMock(spec=Context), location, "/local/file.pdf")

    assert result is False


# ---------------------------------------------------------------------------
# UploadMicrosoft365.__init__
# ---------------------------------------------------------------------------


def test_init_sets_attributes():
    graph = MagicMock()
    resolver = MagicMock()

    instance = UploadMicrosoft365(graph, resolver, "target/path")

    assert instance.graph is graph
    assert instance.resolver is resolver
    assert instance.target_path == "target/path"


# ---------------------------------------------------------------------------
# upload_report
# ---------------------------------------------------------------------------


def test_upload_report_delegates_to_push_item(uploader):
    uploader.resolver.resolve_target_path = AsyncMock(return_value=("site-1", "drive-1", "item-1"))
    uploader.push_item = AsyncMock(return_value=True)

    result = uploader.upload_report("/local/report.pdf")

    assert result is True
    uploader.resolver.resolve_target_path.assert_called_once_with("Site A/Drive A/Folder")
    uploader.push_item.assert_called_once_with(
        site_id="site-1",
        drive_id="drive-1",
        item_id="item-1",
        remote_file_path="report.pdf",
        local_file_path="/local/report.pdf",
    )


def test_upload_report_returns_false_when_push_item_fails(uploader):
    uploader.resolver.resolve_target_path = AsyncMock(return_value=("site-1", "drive-1", "item-1"))
    uploader.push_item = AsyncMock(return_value=False)

    result = uploader.upload_report("/local/report.pdf")

    assert result is False


# ---------------------------------------------------------------------------
# push_item
# ---------------------------------------------------------------------------


def test_push_item_success(tmp_path):
    local_file = tmp_path / "report.pdf"
    local_file.write_bytes(b"content")

    graph = MagicMock()
    graph.get_token = AsyncMock(return_value="fake-token")
    instance = UploadMicrosoft365(graph, MagicMock(), "Site/Drive/Folder")

    with patch(f"{MODULE}.requests.put") as mock_put:
        mock_put.return_value = MagicMock(raise_for_status=MagicMock())

        result = asyncio.run(
            instance.push_item(
                site_id="site1",
                drive_id="drive1",
                item_id="item1",
                remote_file_path="report.pdf",
                local_file_path=str(local_file),
            )
        )

    assert result is True
    mock_put.assert_called_once()
    call_args = mock_put.call_args
    assert call_args.args[0] == (
        "https://graph.microsoft.com/v1.0/sites/site1/drives/drive1/items/item1:/report.pdf:/content"
    )
    assert call_args.kwargs["headers"] == {"Authorization": "Bearer fake-token"}
    assert call_args.kwargs["data"] == b"content"


def test_push_item_returns_false_when_file_too_large():
    graph = MagicMock()
    graph.get_token = AsyncMock(return_value="fake-token")
    instance = UploadMicrosoft365(graph, MagicMock(), "Site/Drive/Folder")

    with patch(f"{MODULE}.Path") as mock_path_cls:
        mock_path_cls.return_value.stat.return_value = MagicMock(st_size=5 * 1024 * 1024)

        result = asyncio.run(
            instance.push_item(
                site_id="site1",
                drive_id="drive1",
                item_id="item1",
                remote_file_path="big.pdf",
                local_file_path="irrelevant.pdf",
            )
        )

    assert result is False


def test_push_item_returns_false_on_http_error(tmp_path):
    local_file = tmp_path / "report.pdf"
    local_file.write_bytes(b"content")

    graph = MagicMock()
    graph.get_token = AsyncMock(return_value="fake-token")
    instance = UploadMicrosoft365(graph, MagicMock(), "Site/Drive/Folder")

    with patch(f"{MODULE}.requests.put") as mock_put:
        mock_put.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")

        result = asyncio.run(
            instance.push_item(
                site_id="site1",
                drive_id="drive1",
                item_id="item1",
                remote_file_path="report.pdf",
                local_file_path=str(local_file),
            )
        )

    assert result is False


def test_push_item_returns_false_on_request_exception(tmp_path):
    local_file = tmp_path / "report.pdf"
    local_file.write_bytes(b"content")

    graph = MagicMock()
    graph.get_token = AsyncMock(return_value="fake-token")
    instance = UploadMicrosoft365(graph, MagicMock(), "Site/Drive/Folder")

    with patch(
        f"{MODULE}.requests.put",
        side_effect=requests.exceptions.RequestException("network down"),
    ):
        result = asyncio.run(
            instance.push_item(
                site_id="site1",
                drive_id="drive1",
                item_id="item1",
                remote_file_path="report.pdf",
                local_file_path=str(local_file),
            )
        )

    assert result is False
