"""Tests for the CacheManager and related lazy iterables."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from ipaddress import IPv4Address
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from assets_guardian.core.cache.cache import CacheManager, LazyCacheIterable
from assets_guardian.core.config.app_config import AppEnv
from assets_guardian.core.config.cache_config import CacheConfig
from assets_guardian.core.domain.models.access import Access
from assets_guardian.core.domain.models.asset import Asset
from assets_guardian.core.domain.models.identity import Identity, IdentityState, IdentityType


@dataclass
class MockItem:
    """Mock item dataclass for cache serialization and deserialization testing."""

    name: str
    value: int
    created_at: datetime = field(default_factory=datetime.now)
    ip: IPv4Address = field(default_factory=lambda: IPv4Address("127.0.0.1"))


class MockEnum(Enum):
    """Mock enum for verifying cache serialization support of enums."""

    VAL1 = "val1"


@dataclass
class MockWithEnum:
    """Mock class wrapping an enum to verify complex nested serialization."""

    status: MockEnum


def test_cache_save_load(tmp_path):
    """Verify that saving and loading basic mock items using CacheManager works correctly."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)
    items = [MockItem("test1", 1), MockItem("test2", 2)]
    file_path = cache.get_file_path("test", "source", "inst", "data")

    cache.save(items, file_path)
    assert file_path.exists()

    loaded = list(cache.load(file_path, MockItem))
    assert len(loaded) == 2
    assert loaded[0].name == "test1"
    assert isinstance(loaded[0].created_at, datetime)
    assert isinstance(loaded[0].ip, IPv4Address)
    assert loaded[1].value == 2


def test_cache_serialization_edge_cases(tmp_path):
    """Verify serialization of specific types such as Enums and standard containers (lists/dicts)."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = MagicMock()  # Keep it simple or use real manager
    cache = CacheManager(config=config)

    # Enum serialization
    item_enum = MockWithEnum(status=MockEnum.VAL1)
    serialized = cache._CacheManager__serialize(item_enum)
    assert serialized["status"] == "val1"

    # List/Dict serialization
    data = {"list": [1, 2], "dict": {"a": 1}}
    serialized_data = cache._CacheManager__serialize(data)
    assert serialized_data == data


def test_cache_deserialization_complex(tmp_path):
    """Verify complex deserialization for domain models like Identity, Asset, and Access."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)

    # Identity
    identity_data = {
        "source": "gitlab",
        "external_id": "user1",
        "name": "User One",
        "identity_type": "human",
        "state": "active",
        "created_at": "2023-01-01T00:00:00",
    }
    identity = cache._CacheManager__deserialize(identity_data, Identity)
    assert identity.external_id == "user1"
    assert identity.identity_type == IdentityType.HUMAN
    assert identity.state == IdentityState.ACTIVE
    assert isinstance(identity.created_at, datetime)

    # Asset
    asset_data = {
        "source": "gitlab",
        "external_id": "res1",
        "asset_type": "repo",
        "name": "Resource 1",
    }
    asset = cache._CacheManager__deserialize(asset_data, Asset)
    assert asset.external_id == "res1"

    # Access
    access_data = {
        "source": "gitlab",
        "access_type": "permission",
        "name": "Maintainer",
        "asset": asset_data,
    }
    access = cache._CacheManager__deserialize(access_data, Access)
    assert access.name == "Maintainer"
    assert isinstance(access.asset, Asset)


def test_cache_load_iterable(tmp_path):
    """Verify load_iterable returns a LazyCacheIterable which loads items sequentially."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)
    items = [MockItem(name="test1", value=1)]
    file_path = cache.get_file_path("test", "source", "inst", "data")
    cache.save(items, file_path)

    lazy = cache.load_iterable(file_path, MockItem)
    assert isinstance(lazy, LazyCacheIterable)

    count = 0
    for item in lazy:
        assert item.name == "test1"
        count += 1
    assert count == 1


def test_cache_save_exception(tmp_path, mocker):
    """Verify that serialization failures during save do not leave behind corrupted files."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)
    file_path = tmp_path / "fail.jsonl"

    # Mock json.dumps to fail
    mocker.patch("json.dumps", side_effect=TypeError("Fail"))

    cache.save([{"a": 1}], file_path)
    assert not file_path.exists()
    assert not file_path.with_suffix(".tmp").exists()


def test_cache_deserialization_edge_cases(tmp_path):
    """Verify deserialization handles blank lines, optional fields, extra keys, and invalid formats."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)

    # Empty line in JSONL
    file_path = tmp_path / "empty_lines.jsonl"
    file_path.write_text('\n{"name": "test", "value": 1}\n\n')
    loaded = list(cache.load(file_path, MockItem))
    assert len(loaded) == 1

    # Dataclass with None value
    @dataclass
    class OptionalItem:
        name: str
        opt: str | None = None

    item = OptionalItem(name="test", opt=None)
    serialized = cache._CacheManager__serialize(item)
    assert "opt" not in serialized

    # Extra field in JSON
    data = {"name": "test", "value": 1, "extra": "field"}
    item = cache._CacheManager__deserialize(data, MockItem)
    assert item.name == "test"
    # 'extra' should be ignored

    # None value in JSON
    data = {"name": "test", "value": 1, "created_at": None}
    item = cache._CacheManager__deserialize(data, MockItem)
    assert item.created_at is None

    # Access field with non-dict/list value
    @dataclass
    class AccessHolder:
        access: Access

    # Passing a string instead of a dict
    holder = cache._CacheManager__deserialize({"access": "invalid"}, AccessHolder)
    assert holder.access == "invalid"


def test_cache_save_exception_no_temp(tmp_path, mocker):
    """Verify that file open errors during write operations are safely handled."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)
    file_path = tmp_path / "fail_no_temp.jsonl"

    # Mock open to fail
    mocker.patch("pathlib.Path.open", side_effect=OSError("Cannot open"))
    cache.save([{"a": 1}], file_path)

    assert not file_path.exists()


def test_cache_deserialization_complex_nested(tmp_path):
    """Verify correct instantiation of complex nested structures containing Identity and lists of Access."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)

    @dataclass
    class Root:
        identity: Identity
        accesses: list[Access]
        single_access: Access

    data = {
        "identity": {
            "source": "s",
            "external_id": "i",
            "name": "n",
            "identity_type": "human",
            "state": "active",
        },
        "accesses": [{"source": "s", "access_type": "p", "name": "a1"}],
        "single_access": {"source": "s", "access_type": "p", "name": "a2"},
    }

    root = cache._CacheManager__deserialize(data, Root)
    assert isinstance(root.identity, Identity)
    assert isinstance(root.accesses[0], Access)
    assert isinstance(root.single_access, Access)


def test_cache_load_error_handling(tmp_path, mocker, caplog):
    """Verify corrupt JSON lines are skipped during load with a warning logged."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)
    file_path = tmp_path / "corrupt.jsonl"
    file_path.write_text('invalid json\n{"valid": 1}\n')

    # Should skip invalid lines
    loaded = list(cache.load(file_path, dict))

    assert len(loaded) == 1
    assert "Error reading line" in caplog.text


def test_cache_cleanup_exception(tmp_path, mocker, caplog):
    """Verify that cleanup handles OS permissions errors when attempting to delete cache files."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)
    f = cache.get_file_path("sync", "s", "i", "d")
    f.touch()

    # Mock Path.unlink to fail
    mocker.patch.object(Path, "unlink", side_effect=OSError("Permission denied"))

    with caplog.at_level("WARNING"):
        cache.cleanup("sync", AppEnv.PROD)

    assert "Unable to delete temporary file" in caplog.text


def test_cache_deserialize_field_value_exception(tmp_path, caplog):
    """Verify deserialization handles exceptions (like IP/date parsing) on individual fields gracefully."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)
    with caplog.at_level("WARNING"):
        res = cache._CacheManager__deserialize_field_value("test_ip", "not-an-ip", "IPv4Address")

    assert res == "not-an-ip"
    assert "Deserialization error for field test_ip" in caplog.text


def test_cache_load_non_existent(tmp_path):
    """Verify that loading a non-existent file returns an empty list without raising an error."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)
    file_path = tmp_path / "none.jsonl"
    loaded = list(cache.load(file_path, dict))
    assert loaded == []


def test_cache_cleanup(tmp_path):
    """Verify that cleanup empties the entire cache directory in production, regardless of
    the file's associated command or extension."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)
    file1 = cache.get_file_path("sync", "s1", "i1", "d1")
    file2 = cache.get_file_path("audit", "s2", "i2", "d2")
    other_file = tmp_path / "employees.json"

    file1.touch()
    file2.touch()
    other_file.touch()

    cache.cleanup("sync", AppEnv.PROD)
    assert not file1.exists()
    assert not file2.exists()
    assert not other_file.exists()


def test_cache_cleanup_skips_subdirectories(tmp_path):
    """Verify that cleanup ignores subdirectories found in the cache directory."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)
    subdir = tmp_path / "some_subdir"
    subdir.mkdir()

    cache.cleanup("sync", AppEnv.PROD)

    assert subdir.exists()


def test_has_checkpoint(tmp_path):
    """Verify has_checkpoint returns True if a cache file exists and False otherwise."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)
    file_path = cache.get_file_path("sync", "s1", "i1", "identities")

    assert not cache.has_checkpoint(file_path)

    file_path.touch()
    assert cache.has_checkpoint(file_path)


def test_cache_service_initialization(tmp_path):
    """Verify that CacheManager creates the cache directory if it does not exist at startup."""
    new_dir = tmp_path / "new_cache"
    assert not new_dir.exists()
    config = CacheConfig(batch_size=64, cache_dir=str(new_dir))
    CacheManager(config=config)
    assert new_dir.exists()


def test_cache_lazy_iterable_iter():
    """Verify LazyCacheIterable triggers sequential file loads only when iterated over."""
    service = MagicMock(spec=CacheManager)
    path = Path("test.jsonl")
    lazy = LazyCacheIterable(service, path, dict)

    iter(lazy)
    service.load.assert_called_once_with(path, dict)


def test_cache_manager_init_no_config():
    """Verify that initializing CacheManager with a None config triggers an AttributeError."""
    with pytest.raises(AttributeError):
        CacheManager(config=None)


def test_cache_cleanup_non_prod(tmp_path):
    """Verify that in non-production environments, cache cleanup operations are skipped."""
    config = CacheConfig(batch_size=64, cache_dir=str(tmp_path))
    cache = CacheManager(config=config)
    file1 = cache.get_file_path("sync", "s1", "i1", "d1")
    file2 = cache.get_file_path("audit", "s2", "i2", "d2")

    file1.touch()
    file2.touch()

    # For non-production environment, cleanup should NOT unlink the files
    cache.cleanup("sync", AppEnv.DEV)
    assert file1.exists()
    assert file2.exists()
