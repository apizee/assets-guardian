"""Tests for core/config/loader.py covering all public functions."""

import json
import os
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import pytest

from assets_guardian.core.config.loader import (
    browse_dict,
    get_config_value,
    get_env_key_name,
    get_project_version,
    load_employees_profiles,
    load_json,
    load_profiles,
    load_yaml_config,
)

# ---------------------------------------------------------------------------
# load_yaml_config
# ---------------------------------------------------------------------------


def test_load_yaml_config_without_dotenv(tmp_path: Path) -> None:
    """load_yaml_config works correctly when no .env file exists at the dotenv path."""
    conf_file = tmp_path / "config.yml"
    conf_file.write_text("env: dev\nname: app")

    # Point ROOT_PROJECT to a location that has no .env sibling
    fake_root = tmp_path / "src" / "assets_guardian"
    fake_root.mkdir(parents=True)

    with patch("assets_guardian.core.config.loader.ROOT_PROJECT", fake_root):
        data = load_yaml_config(str(conf_file))

    assert data == {"env": "dev", "name": "app"}


def test_load_yaml_config_with_dotenv_sets_env_vars(tmp_path: Path) -> None:
    """load_yaml_config reads a .env file and injects variables via os.environ.setdefault."""
    conf_file = tmp_path / "config.yml"
    conf_file.write_text("token: ${MY_DOTENV_VAR}")

    dotenv_dir = tmp_path / "src"
    dotenv_dir.mkdir()
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("MY_DOTENV_VAR=secret_from_dotenv\n# comment line\nINVALID")

    fake_root = dotenv_dir / "assets_guardian"
    fake_root.mkdir()

    with (
        patch("assets_guardian.core.config.loader.ROOT_PROJECT", fake_root),
        mock.patch.dict(os.environ, {}, clear=True),
    ):
        data = load_yaml_config(str(conf_file))

    assert data == {"token": "secret_from_dotenv"}


def test_load_yaml_config_dotenv_does_not_override_existing_env(tmp_path: Path) -> None:
    """os.environ.setdefault means an already-set env var is not overridden by .env."""
    conf_file = tmp_path / "config.yml"
    conf_file.write_text("token: ${MY_VAR}")

    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("MY_VAR=from_dotenv")

    fake_root = tmp_path / "src" / "assets_guardian"
    fake_root.mkdir(parents=True)

    with (
        patch("assets_guardian.core.config.loader.ROOT_PROJECT", fake_root),
        mock.patch.dict(os.environ, {"MY_VAR": "from_env"}, clear=False),
    ):
        data = load_yaml_config(str(conf_file))

    # env variable takes precedence over .env
    assert data == {"token": "from_env"}


def test_load_yaml_config_not_found(tmp_path: Path) -> None:
    """load_yaml_config raises FileNotFoundError for a missing file."""
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_yaml_config(str(tmp_path / "nonexistent.yml"))


def test_load_yaml_config_empty_file(tmp_path: Path) -> None:
    """load_yaml_config raises ValueError for an empty YAML file."""
    conf_file = tmp_path / "empty.yml"
    conf_file.write_text("")

    with pytest.raises(ValueError, match="empty"):
        load_yaml_config(str(conf_file))


def test_load_yaml_config_not_a_dict(tmp_path: Path) -> None:
    """load_yaml_config raises TypeError when the YAML root is not a dict."""
    conf_file = tmp_path / "list.yml"
    conf_file.write_text("- item1\n- item2")

    with pytest.raises(TypeError, match="must contain a YAML dictionary"):
        load_yaml_config(str(conf_file))


# ---------------------------------------------------------------------------
# load_json
# ---------------------------------------------------------------------------


def test_load_json_success(tmp_path: Path) -> None:
    """load_json returns parsed data from a valid JSON file."""
    json_file = tmp_path / "data.json"
    json_file.write_text('{"key": "value", "count": 42}')

    data = load_json(str(json_file))

    assert data == {"key": "value", "count": 42}


def test_load_json_list(tmp_path: Path) -> None:
    """load_json handles JSON arrays at the root level."""
    json_file = tmp_path / "list.json"
    json_file.write_text('[{"id": 1}, {"id": 2}]')

    data = load_json(str(json_file))

    assert data == [{"id": 1}, {"id": 2}]


def test_load_json_not_found(tmp_path: Path) -> None:
    """load_json raises FileNotFoundError for a missing file."""
    with pytest.raises(FileNotFoundError, match="JSON file not found"):
        load_json(str(tmp_path / "nonexistent.json"))


def test_load_json_invalid_json(tmp_path: Path) -> None:
    """load_json raises ValueError for a file with invalid JSON syntax."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json}")

    with pytest.raises(ValueError, match="Invalid JSON format"):
        load_json(str(bad_file))


def test_load_json_null_content(tmp_path: Path) -> None:
    """load_json raises ValueError for a file whose JSON value is null."""
    null_file = tmp_path / "null.json"
    null_file.write_text("null")

    with pytest.raises(ValueError, match="is empty"):
        load_json(str(null_file))


# ---------------------------------------------------------------------------
# browse_dict
# ---------------------------------------------------------------------------


def test_browse_dict_simple_key() -> None:
    """browse_dict retrieves a top-level key."""
    assert browse_dict({"a": 1}, "a") == 1


def test_browse_dict_nested_key() -> None:
    """browse_dict traverses nested keys separated by ':'."""
    data = {"a": {"b": {"c": "deep"}}}
    assert browse_dict(data, "a:b:c") == "deep"


def test_browse_dict_missing_key_returns_none() -> None:
    """browse_dict returns None when a segment is not found."""
    assert browse_dict({"a": 1}, "a:b") is None


def test_browse_dict_non_dict_intermediate_returns_none() -> None:
    """browse_dict returns None when an intermediate value is not a dict."""
    assert browse_dict({"a": "string"}, "a:b") is None


# ---------------------------------------------------------------------------
# get_env_key_name
# ---------------------------------------------------------------------------


def test_get_env_key_name_simple() -> None:
    """get_env_key_name uppercases and replaces ':' with '_'."""
    assert get_env_key_name("logging:level") == "LOGGING_LEVEL"


def test_get_env_key_name_with_dash() -> None:
    """get_env_key_name replaces '-' with '_' as well."""
    assert get_env_key_name("max-size") == "MAX_SIZE"


# ---------------------------------------------------------------------------
# get_config_value
# ---------------------------------------------------------------------------


def test_get_config_value_env_takes_priority() -> None:
    """get_config_value prefers the environment variable over the dict value."""
    with mock.patch.dict(os.environ, {"MY_KEY": "env_val"}):
        val = get_config_value("my_key", {"my_key": "dict_val"}, env_name="MY_KEY")
    assert val == "env_val"


def test_get_config_value_dict_fallback() -> None:
    """get_config_value reads from the dict when env is absent."""
    with mock.patch.dict(os.environ, {}, clear=True):
        val = get_config_value("my_key", {"my_key": "dict_val"}, env_name="MY_KEY")
    assert val == "dict_val"


def test_get_config_value_default_fallback() -> None:
    """get_config_value returns the default when neither env nor dict has the key."""
    with mock.patch.dict(os.environ, {}, clear=True):
        val = get_config_value("missing", {}, default="fallback")
    assert val == "fallback"


def test_get_config_value_raises_when_missing_and_no_default() -> None:
    """get_config_value raises KeyError when key is absent and no default is provided."""
    with (
        mock.patch.dict(os.environ, {}, clear=True),
        pytest.raises(KeyError, match="Missing required configuration key"),
    ):
        get_config_value("missing", {})


def test_get_config_value_env_override_disabled() -> None:
    """get_config_value ignores env vars when env_override=False."""
    with mock.patch.dict(os.environ, {"MY_KEY": "env_val"}):
        val = get_config_value(
            "my_key",
            {"my_key": "dict_val"},
            env_name="MY_KEY",
            env_override=False,
        )
    assert val == "dict_val"


# ---------------------------------------------------------------------------
# load_profiles
# ---------------------------------------------------------------------------


def test_load_profiles_no_path_returns_defaults() -> None:
    """load_profiles returns default profile list when no file path is given."""
    profiles = load_profiles(None)
    assert "R&D" in profiles
    assert len(profiles) == 5


def test_load_profiles_missing_file_returns_defaults(tmp_path: Path) -> None:
    """load_profiles returns defaults when the file does not exist."""
    profiles = load_profiles(str(tmp_path / "nonexistent.json"))
    assert "R&D" in profiles


def test_load_profiles_valid_file(tmp_path: Path) -> None:
    """load_profiles extracts unique profiles from the employees file."""
    employees_file = tmp_path / "employees.json"
    employees_file.write_text(
        json.dumps(
            [
                {"email": "a@a.com", "profiles": "R&D, Security"},
                {"email": "b@b.com", "profiles": "R&D"},
                {"email": "c@c.com", "profiles": "Finance"},
            ]
        )
    )

    profiles = load_profiles(str(employees_file))

    assert profiles == sorted({"R&D", "Security", "Finance"})


def test_load_profiles_employees_without_profiles_field(tmp_path: Path) -> None:
    """load_profiles skips employees that have no 'profiles' field."""
    employees_file = tmp_path / "employees.json"
    employees_file.write_text(json.dumps([{"email": "a@a.com"}, {"email": "b@b.com"}]))

    profiles = load_profiles(str(employees_file))

    assert profiles == []


def test_load_profiles_invalid_json_returns_defaults(tmp_path: Path) -> None:
    """load_profiles returns defaults when the file contains invalid JSON."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not valid json {")

    profiles = load_profiles(str(bad_file))

    assert "R&D" in profiles


# ---------------------------------------------------------------------------
# load_employees_profiles
# ---------------------------------------------------------------------------


def test_load_employees_profiles_no_path_returns_empty() -> None:
    """load_employees_profiles returns {} when no file path is given."""
    assert load_employees_profiles(None) == {}


def test_load_employees_profiles_missing_file_returns_empty(tmp_path: Path) -> None:
    """load_employees_profiles returns {} when the file does not exist."""
    result = load_employees_profiles(str(tmp_path / "nonexistent.json"))
    assert result == {}


def test_load_employees_profiles_valid_file(tmp_path: Path) -> None:
    """load_employees_profiles maps email → list of profiles from the JSON file."""
    employees_file = tmp_path / "employees.json"
    employees_file.write_text(
        json.dumps(
            [
                {"email": "alice@corp.com", "profiles": "R&D, Security"},
                {"email": "bob@corp.com", "profiles": "Finance"},
            ]
        )
    )

    result = load_employees_profiles(str(employees_file))

    assert result["alice@corp.com"] == ["R&D", "Security"]
    assert result["bob@corp.com"] == ["Finance"]


def test_load_employees_profiles_uses_username_fallback(tmp_path: Path) -> None:
    """load_employees_profiles uses 'username' when 'email' is absent."""
    employees_file = tmp_path / "employees.json"
    employees_file.write_text(json.dumps([{"username": "jdoe", "profiles": "Admin"}]))

    result = load_employees_profiles(str(employees_file))

    assert "jdoe" in result
    assert result["jdoe"] == ["Admin"]


def test_load_employees_profiles_multiple_emails_per_employee(tmp_path: Path) -> None:
    """load_employees_profiles maps every email in a list to the same profiles."""
    employees_file = tmp_path / "employees.json"
    employees_file.write_text(
        json.dumps(
            [
                {
                    "email": ["alice@corp.com", "alice.smith@corp.com"],
                    "profiles": "R&D, Security",
                }
            ]
        )
    )

    result = load_employees_profiles(str(employees_file))

    assert result["alice@corp.com"] == ["R&D", "Security"]
    assert result["alice.smith@corp.com"] == ["R&D", "Security"]


def test_load_employees_profiles_skips_entries_without_id_or_profiles(tmp_path: Path) -> None:
    """load_employees_profiles ignores employees missing both email/username and profiles."""
    employees_file = tmp_path / "employees.json"
    employees_file.write_text(
        json.dumps(
            [
                {"name": "Anonymous"},  # no email / username
                {"email": "a@a.com"},  # no profiles
                {"email": "b@b.com", "profiles": ""},  # empty profiles string
            ]
        )
    )

    result = load_employees_profiles(str(employees_file))

    assert result == {}


def test_load_employees_profiles_invalid_json_returns_empty(tmp_path: Path) -> None:
    """load_employees_profiles returns {} when the file is invalid JSON."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not valid {")

    result = load_employees_profiles(str(bad_file))

    assert result == {}


# ---------------------------------------------------------------------------
# get_project_version
# ---------------------------------------------------------------------------


def test_get_project_version_from_package() -> None:
    """get_project_version returns the package version when available."""
    with patch("assets_guardian.core.config.loader.version") as mock_version:
        mock_version.return_value = "1.2.3"
        version_str = get_project_version()
        assert version_str == "1.2.3"
        mock_version.assert_called_once_with("assets-guardian")


def test_get_project_version_from_pyproject(tmp_path: Path) -> None:
    """get_project_version falls back to pyproject.toml when package is not installed."""
    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text('[project]\nversion = "2.0.1"\n')

    fake_root = tmp_path / "src" / "assets_guardian"
    fake_root.mkdir(parents=True)

    with (
        patch("assets_guardian.core.config.loader.version", side_effect=PackageNotFoundError),
        patch("assets_guardian.core.config.loader.ROOT_PROJECT", fake_root),
    ):
        version_str = get_project_version()
        assert version_str == "2.0.1"


def test_get_project_version_missing_pyproject_returns_default(tmp_path: Path) -> None:
    """get_project_version returns '0.0.0' when pyproject.toml does not exist."""
    fake_root = tmp_path / "src" / "assets_guardian"
    fake_root.mkdir(parents=True)

    with (
        patch("assets_guardian.core.config.loader.version", side_effect=PackageNotFoundError),
        patch("assets_guardian.core.config.loader.ROOT_PROJECT", fake_root),
    ):
        version_str = get_project_version()
        assert version_str == "0.0.0"


def test_get_project_version_invalid_pyproject_returns_default(tmp_path: Path) -> None:
    """get_project_version returns '0.0.0' when pyproject.toml exists but has no version."""
    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text('[project]\nname = "assets-guardian"\n')

    fake_root = tmp_path / "src" / "assets_guardian"
    fake_root.mkdir(parents=True)

    with (
        patch("assets_guardian.core.config.loader.version", side_effect=PackageNotFoundError),
        patch("assets_guardian.core.config.loader.ROOT_PROJECT", fake_root),
    ):
        version_str = get_project_version()
        assert version_str == "0.0.0"
