import os
import re
from pathlib import Path
from unittest import mock

import pytest

from assets_guardian.core.config.app_config import AppConfig, AppEnv
from assets_guardian.core.config.author_config import AuthorConfig
from assets_guardian.core.config.cache_config import CacheConfig
from assets_guardian.core.config.loader import (
    get_config_value,
    load_yaml_config,
)
from assets_guardian.core.config.logging_config import LoggingConfig
from assets_guardian.core.config.paths_config import PathsConfig
from assets_guardian.core.config.validator import (
    validate_config,
)
from assets_guardian.core.domain.models.location import Location


@pytest.fixture(autouse=True)
def env_paths():
    """Provide default path values via environment variables to prevent potential get_config_value issues."""
    with mock.patch.dict(
        os.environ,
        {
            "PATH_EXCEL": "local:excel.xlsx",
            "PATH_PDF": "local:report.pdf",
            "PATH_RULES": "local:rules.yml",
            "PATH_EXCEL_CONFIG": "local:excel_config.json",
            "PATH_PDF_CONFIG": "local:pdf_config.json",
            "PATH_EMPLOYEES": "local:employees.json",
            "AUTHOR_FULLNAME": "Test Author",
            "AUTHOR_EMAIL": "author@example.com",
        },
    ):
        yield


def test_logging_config_valid() -> None:
    """Verify LoggingConfig initializes successfully with valid string levels and correct size calculations."""
    config = LoggingConfig(console_level="info", file_level="debug", max_size=2, max_files=3)
    assert config.console_level == 20
    assert config.file_level == 10
    assert config.max_size == 2 * 1048576
    assert config.max_files == 3
    assert config.file_basename == "assets-guardian"


def test_logging_config_invalid() -> None:
    """Verify LoggingConfig raises KeyError when provided with invalid string level representations."""
    with pytest.raises(KeyError, match="Invalid console logging level"):
        LoggingConfig(console_level="not-a-level", file_level="debug", max_size=2, max_files=3)
    with pytest.raises(KeyError, match="Invalid file logging level"):
        LoggingConfig(console_level="info", file_level="not-a-level", max_size=2, max_files=3)


def test_logging_config_with_integer_levels() -> None:
    """LoggingConfig accepts already-integer log levels and skips the string conversion branch."""
    config = LoggingConfig(console_level=30, file_level=20, max_size=1, max_files=2)
    # Integers pass through unchanged (WARNING=30, INFO=20)
    assert config.console_level == 30
    assert config.file_level == 20


def test_app_config_dry_run_enabled() -> None:
    """Verify dry-run mode activation conditions based on different environment values (DEV, TEST, PROD)."""
    base_params = {
        "version": "1.0",
        "author": AuthorConfig(fullname="Test Author", email="author@example.com"),
        "logging": LoggingConfig(console_level="INFO", file_level="INFO", max_size=1, max_files=1),
        "integrations": {},
        "paths": PathsConfig(
            excel=Location("local:test.xlsx"),
            pdf=Location("local:report.pdf"),
            rules=Location("local:rules.yml"),
            excel_config=Location("local:excel_config.json"),
            pdf_config=Location("local:pdf_config.json"),
            employees=Location("local:employees.json"),
            config_path=Location("local:config.yml"),
        ),
        "cache": CacheConfig(batch_size=64, cache_dir=".test"),
    }

    app_dev = AppConfig(env=AppEnv.DEV, **base_params)
    assert app_dev.dry_run_enabled is True

    app_test = AppConfig(env=AppEnv.TEST, **base_params)
    assert app_test.dry_run_enabled is True

    app_prod = AppConfig(env=AppEnv.PROD, **base_params)
    assert app_prod.dry_run_enabled is False


def test_load_yaml_config_success(tmp_path: Path) -> None:
    """Verify that load_yaml_config correctly parses a valid YAML file into a dictionary."""
    conf_file = tmp_path / "config.yml"
    conf_file.write_text('env: dev\nversion: "1.0"')

    data = load_yaml_config(str(conf_file))
    assert data == {"env": "dev", "version": "1.0"}


def test_load_yaml_config_with_env_interpolation(tmp_path: Path) -> None:
    """Verify that load_yaml_config correctly interpolates environment variables from os.environ and custom .env files."""
    # Test interpolation from os.environ
    conf_file = tmp_path / "config.yml"
    conf_file.write_text("token: ${MY_TEST_TOKEN}\nurl: http://example.com/$MY_TEST_URL")

    with mock.patch.dict(os.environ, {"MY_TEST_TOKEN": "secret123", "MY_TEST_URL": "api"}):
        data = load_yaml_config(str(conf_file))
        assert data == {"token": "secret123", "url": "http://example.com/api"}

    # Test interpolation from a local .env file
    # We must patch Path('.env') or temporarily write to the current directory's .env.
    # To keep the test hermetic, let's write to a mock .env file if we can patch it,
    # or write/restore a real .env in the cwd since pytest runs from the root of the project.
    dotenv_file = Path(".env")
    old_dotenv_content = None
    if dotenv_file.exists():
        old_dotenv_content = dotenv_file.read_text(encoding="utf-8")

    try:
        dotenv_file.write_text(
            "MY_DOTENV_TOKEN=dotenv_secret\n# Comment\nINVALID_LINE", encoding="utf-8"
        )
        conf_file_dotenv = tmp_path / "config_dotenv.yml"
        conf_file_dotenv.write_text("token: ${MY_DOTENV_TOKEN}")

        with mock.patch.dict(os.environ, {}):
            data = load_yaml_config(str(conf_file_dotenv))
            assert data == {"token": "dotenv_secret"}
    finally:
        if old_dotenv_content is not None:
            dotenv_file.write_text(old_dotenv_content, encoding="utf-8")
        elif dotenv_file.exists():
            dotenv_file.unlink()


def test_load_yaml_config_not_found(tmp_path: Path) -> None:
    """Verify that load_yaml_config raises a FileNotFoundError when the target configuration file is missing."""
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_yaml_config(str(tmp_path / "not-found.yml"))


def test_load_yaml_config_invalid_format(tmp_path: Path) -> None:
    """Verify that load_yaml_config raises a TypeError if the configuration file is not a valid YAML dictionary."""
    conf_file = tmp_path / "config.yml"
    # Not a dict
    conf_file.write_text("- item1\n- item2")
    with pytest.raises(TypeError, match="must contain a YAML dictionary"):
        load_yaml_config(str(conf_file))


def test_get_config_value_from_env() -> None:
    """Verify get_config_value correctly prioritizes retrieving properties from the environment variables."""
    with mock.patch.dict(os.environ, {"MY_KEY": "env_value"}):
        val = get_config_value("my_key", {"my_key": "dict_value"}, env_name="MY_KEY")
        assert val == "env_value"


def test_get_config_value_from_dict() -> None:
    """Verify get_config_value falls back to dictionary values when the corresponding environment variable is not defined."""
    # Use empty env mock to prevent local env interference
    with mock.patch.dict(os.environ, {}, clear=True):
        val = get_config_value("my_key", {"my_key": "dict_value"}, env_name="MY_KEY")
        assert val == "dict_value"


def test_get_config_value_default() -> None:
    """Verify get_config_value falls back to the provided default value if the key is missing from dictionary and env."""
    with mock.patch.dict(os.environ, {}, clear=True):
        val = get_config_value("my_key", {}, default="default_value")
        assert val == "default_value"


def test_get_config_value_missing() -> None:
    """Verify get_config_value raises a KeyError when a required configuration key is completely absent."""
    with (
        mock.patch.dict(os.environ, {}, clear=True),
        pytest.raises(KeyError, match="Missing required configuration key"),
    ):
        get_config_value("my_key", {})


def test_parse_config_valid() -> None:
    """Verify AppConfig.create_from_dict successfully parses all configurations under normal parameters."""
    raw = {
        "env": "prod",
        "version": "1.0",
        "author": {"fullname": "Test", "email": "test@example.com"},
        "logging": {"console_level": "info", "file_level": "debug", "max-size": 5, "max-files": 2},
        "extra_integration": {"token": "123"},
    }
    with mock.patch.dict(
        os.environ,
        {
            "PATH_EXCEL": "local:e",
            "PATH_PDF": "local:r",
            "PATH_RULES": "local:ru",
            "PATH_EXCEL_CONFIG": "local:er",
            "PATH_PDF_CONFIG": "local:pr",
            "PATH_EMPLOYEES": "local:em",
        },
        clear=True,
    ):
        app_config = AppConfig.create_from_dict(raw)
    assert app_config.env == AppEnv.PROD
    assert re.search(r"[0-9]+(\.[0-9]){2}", app_config.version)
    assert app_config.author == AuthorConfig(fullname="Test", email="test@example.com")
    assert app_config.logging.console_level == 20
    assert app_config.logging.file_level == 10
    assert app_config.logging.max_size == 5 * 1048576
    assert app_config.logging.max_files == 2
    assert "extra_integration" in app_config.integrations
    assert app_config.integrations["extra_integration"] == {"token": "123"}
    assert app_config.dry_run_enabled is False


def test_validate_config_success() -> None:
    """Verify validate_config successfully validates matching raw configurations against template schemas."""
    template = {
        "env": "dev",
        "version": "0.1.0",
        "logging": {"console_level": "info", "file_level": "info", "max-size": 10},
    }
    raw = {
        "env": "test",
        "version": "1.2",
        "logging": {"console_level": "debug", "file_level": "debug", "max-size": 5},
    }
    # Should not raise
    validate_config(raw, template)


def test_validate_config_missing_core_key() -> None:
    """Verify validate_config/get_config_value raises KeyError if a critical top-level configuration key is missing."""
    raw = {"env": "dev"}  # Missing 'version'
    with (
        mock.patch.dict(os.environ, {}, clear=True),
        pytest.raises(KeyError, match="Missing required configuration key"),
    ):
        get_config_value("version", raw)


def test_validate_config_satisfied_by_env() -> None:
    """Verify validation passes successfully when a missing config dict key is compensated for by environment variables."""
    raw = {"env": "dev"}
    # 'version' is in ENV
    with mock.patch.dict(os.environ, {"VERSION": "1.0"}):
        assert get_config_value("version", raw) == "1.0"


def test_validate_config_ignores_integrations() -> None:
    """Verify validation does not enforce integration-specific schema sections unless actively configured."""
    template = {
        "env": "dev",
        "gitlab": [{"url": "http://gitlab.com"}],  # Integration
    }
    raw = {"env": "prod"}  # Missing 'gitlab' but it's an integration, so it should be ignored
    validate_config(raw, template)


def test_validate_config_unknown_integration_raises() -> None:
    """Verify validate_config raises KeyError for an integration key with no matching plugin folder."""
    template = {
        "env": "dev",
        "plauf": [{"url": "http://plauf.com"}],  # Not a real plugin
    }
    raw = {"env": "prod"}
    with pytest.raises(KeyError, match="Unknown integration 'plauf'"):
        validate_config(raw, template)


def test_validate_config_nested_core() -> None:
    """Verify that get_config_value correctly evaluates paths for nested dictionary properties."""
    raw = {"logging": {}}  # Missing 'console_level' in logging
    with (
        mock.patch.dict(os.environ, {}, clear=True),
        pytest.raises(KeyError, match="Missing required configuration key"),
    ):
        get_config_value("logging:console_level", raw)


def test_validate_config_must_be_dict() -> None:
    """Verify validate_config raises a TypeError if a expected dictionary field is provided as a non-dictionary."""
    template = {"logging": {"console_level": "info"}}
    raw = {"logging": "not-a-dict"}
    with pytest.raises(TypeError, match="Configuration key 'logging' must be a dictionary"):
        validate_config(raw, template)


def test_get_config_value_env_name_derived_from_key() -> None:
    """Verify that get_config_value automatically searches for the uppercase key in the environment when env_name is omitted."""
    with mock.patch.dict(os.environ, {"ENV": "staging"}):
        val = get_config_value("env", {})
        assert val == "staging"


def test_get_config_value_env_name_derived_not_found_falls_through_to_dict() -> None:
    """Verify that get_config_value falls back to dictionary if the derived uppercase env name is not present."""
    with mock.patch.dict(os.environ, {}, clear=True):
        val = get_config_value("env", {"env": "prod"})
        assert val == "prod"


def test_logging_config_accepts_string_numeric_values() -> None:
    """Verify LoggingConfig handles typical integers/string inputs properly while enforcing correct typing."""
    config = LoggingConfig(console_level="INFO", file_level="INFO", max_size=5, max_files=3)
    assert config.max_size == 5 * 1048576
    assert config.max_files == 3


def test_logging_config_level_mixed_case() -> None:
    """Verify that log level string normalization accepts mixed/lowercase values seamlessly."""
    config = LoggingConfig(console_level="info", file_level="Warning", max_size=1, max_files=1)
    assert config.file_level == 30


def test_logging_config_custom_file_basename() -> None:
    """Verify LoggingConfig successfully applies custom base names for output logs."""
    config = LoggingConfig(
        console_level="INFO", file_level="INFO", max_size=1, max_files=1, file_basename="my-app"
    )
    assert config.file_basename == "my-app"


def test_logging_config_file_basename_from_env() -> None:
    """Verify LoggingConfig correctly parses and overrides the file base name using environment variables."""
    with mock.patch.dict(
        os.environ,
        {
            "LOGGING_FILE_BASENAME": "env-app",
            "PATH_EXCEL": "local:e",
            "PATH_PDF": "local:r",
            "PATH_RULES": "local:ru",
        },
    ):
        raw = {
            "env": "prod",
            "version": "1.0",
            "author": {},
            "logging": {
                "console_level": "info",
                "file_level": "info",
                "max-size": 5,
                "max-files": 2,
            },
        }
        config = AppConfig.create_from_dict(raw)
    assert config.logging.file_basename == "env-app"


def test_validate_env_vars_override_yaml_logging() -> None:
    """Verify that environment variables take complete precedence over YAML-defined configurations end-to-end."""
    raw = {
        "env": "prod",
        "version": "2.0",
        "author": {},
        "logging": {
            "console_level": "debug",
            "file_level": "debug",
            "max-size": 10,
            "max-files": 5,
        },
    }
    env_overrides = {
        "LOGGING_CONSOLE_LEVEL": "WARNING",
        "LOGGING_FILE_LEVEL": "ERROR",
        "LOGGING_MAX_SIZE": "20",
        "LOGGING_MAX_FILES": "8",
        "PATH_EXCEL": "local:e",
        "PATH_PDF": "local:r",
        "PATH_RULES": "local:ru",
        "PATH_EXCEL_CONFIG": "local:er",
        "PATH_PDF_CONFIG": "local:pr",
        "PATH_EMPLOYEES": "local:em",
        "AUTHOR_FULLNAME": "Test Author",
        "AUTHOR_EMAIL": "author@example.com",
    }
    with mock.patch.dict(os.environ, env_overrides, clear=True):
        config = AppConfig.create_from_dict(raw)

    assert config.logging.console_level == 30  # WARNING
    assert config.logging.file_level == 40  # ERROR
    assert config.logging.max_size == 20 * 1048576
    assert config.logging.max_files == 8


def test_validate_env_var_overrides_env_field() -> None:
    """Verify that the core 'env' configuration field can be overridden via the ENV variable."""
    raw = {
        "env": "prod",
        "version": "1.0",
        "author": {},
        "logging": {},
    }
    with mock.patch.dict(
        os.environ,
        {
            "ENV": "dev",
            "VERSION": "1.0",
            "LOGGING_LEVEL": "INFO",
            "LOGGING_MAX_SIZE": "10",
            "LOGGING_MAX_FILES": "5",
            "PATH_EXCEL": "local:excel",
            "PATH_REPORT": "local:report",
            "PATH_RULES": "local:rules",
            "AUTHOR_FULLNAME": "Test Author",
            "AUTHOR_EMAIL": "author@example.com",
        },
        clear=True,
    ):
        config = AppConfig.create_from_dict(raw)

    assert config.env == AppEnv.DEV
    assert config.dry_run_enabled is True  # "dev" activates dry_run


def test_validate_no_integrations() -> None:
    """Verify that a configuration containing no extra integration keys results in an empty integrations dictionary."""
    raw = {
        "env": "prod",
        "version": "1.0",
        "logging": {},
    }
    with mock.patch.dict(
        os.environ,
        {
            "ENV": "prod",
            "VERSION": "1.0",
            "LOGGING_LEVEL": "INFO",
            "LOGGING_MAX_SIZE": "10",
            "LOGGING_MAX_FILES": "5",
            "PATH_EXCEL": "local:excel",
            "PATH_REPORT": "local:report",
            "PATH_RULES": "local:rules",
            "AUTHOR_FULLNAME": "Test Author",
            "AUTHOR_EMAIL": "author@example.com",
        },
        clear=True,
    ):
        config = AppConfig.create_from_dict(raw)
    assert config.integrations == {}


def test_validate_author_absent_raises_missing_fullname() -> None:
    """Verify that AppConfig.create_from_dict raises KeyError when author settings are absent (author is mandatory)."""
    raw = {
        "env": "prod",
        "version": "1.0",
        "logging": {},
    }
    with (
        mock.patch.dict(
            os.environ,
            {
                "ENV": "prod",
                "VERSION": "1.0",
                "LOGGING_LEVEL": "INFO",
                "LOGGING_MAX_SIZE": "10",
                "LOGGING_MAX_FILES": "5",
                "PATH_EXCEL": "local:e",
                "PATH_REPORT": "local:r",
                "PATH_RULES": "local:ru",
            },
            clear=True,
        ),
        pytest.raises(KeyError, match="fullname"),
    ):
        AppConfig.create_from_dict(raw)


def test_load_yaml_config_empty_file(tmp_path) -> None:
    """Verify that attempting to load a completely empty YAML configuration file raises a ValueError."""
    conf_file = tmp_path / "empty.yml"
    conf_file.write_text("")
    with pytest.raises(ValueError, match="Configuration file is empty"):
        load_yaml_config(str(conf_file))


def test_validate_and_parse_config_invalid_int_in_env() -> None:
    """Verify that providing a non-integer environment override for an integer config raises a ValueError."""
    raw = {"env": "prod", "version": "1.0", "logging": {}}
    with (
        mock.patch.dict(os.environ, {"LOGGING_MAX_SIZE": "not-an-integer"}),
        pytest.raises(ValueError),
    ):
        AppConfig.create_from_dict(raw)


def test_app_config_unknown_env_raises_errors() -> None:
    """Verify that using an unrecognized or invalid environment value raises appropriate exceptions."""
    base_params = {
        "version": "1.0",
        "author": {},
        "logging": LoggingConfig(console_level="INFO", file_level="INFO", max_size=1, max_files=1),
        "integrations": {},
        "paths": PathsConfig(
            excel=Location("local:test.xlsx"),
            pdf=Location("local:report.pdf"),
            rules=Location("local:rules.yml"),
            excel_config=Location("local:excel_config.json"),
            pdf_config=Location("local:pdf_config.json"),
            employees=Location("local:employees.json"),
            config_path=Location("local:config.yml"),
        ),
        "cache": CacheConfig(batch_size=64, cache_dir=".test"),
    }
    # Direct instantiation with string triggers TypeError since AppEnv is expected
    with pytest.raises(TypeError, match="must be a AppEnv"):
        AppConfig(env="unknown_env", **base_params)

    # Creating from dict triggers ValueError since string is not in the AppEnv enum
    raw = {"env": "unknown_env", "version": "1.0", "logging": {}}
    with pytest.raises(ValueError, match="'unknown_env' is not a valid AppEnv"):
        AppConfig.create_from_dict(raw)


def test_get_config_value_nested_lookup() -> None:
    """Verify successful retrieval of nested configurations using the ':' key separator."""
    data = {"logging": {"console_level": "INFO", "details": {"format": "standard"}}}
    with mock.patch.dict(os.environ, {}, clear=True):
        # Double nested access
        assert get_config_value("logging:details:format", data) == "standard"
        # Simple nested access
        assert get_config_value("logging:console_level", data) == "INFO"


def test_get_config_value_env_derivation_nested() -> None:
    """Verify derived environment variable names are correctly compiled and checked for nested key paths."""
    # 'logging:max-size' must lookup 'LOGGING_MAX_SIZE'
    with mock.patch.dict(os.environ, {"LOGGING_MAX_SIZE": "50"}):
        assert get_config_value("logging:max-size", {}) == "50"

    # 'gitlab:credentials:token' must lookup 'GITLAB_CREDENTIALS_TOKEN'
    with mock.patch.dict(os.environ, {"GITLAB_CREDENTIALS_TOKEN": "secret"}):
        assert get_config_value("gitlab:credentials:token", {}) == "secret"


def test_get_config_value_nested_missing_yields_correct_error() -> None:
    """Verify that lookup of nested key paths raises KeyError if any segment is completely missing."""
    with (
        mock.patch.dict(os.environ, {}, clear=True),
        pytest.raises(KeyError, match="Missing required configuration key"),
    ):
        get_config_value("gitlab:token", {})


def test_get_config_value_none_coverage() -> None:
    """Verify get_config_value handles dict properties set to None properly, applying defaults if available."""
    data = {"key": None}
    with mock.patch.dict(os.environ, {}, clear=True):
        # Case with default
        assert get_config_value("key", data, default="fallback") == "fallback"
        # Case without default
        with pytest.raises(KeyError, match="Missing required configuration key: 'key'"):
            get_config_value("key", data)


def test_get_config_value_env_override_false() -> None:
    """Verify get_config_value ignores environment overrides when env_override is explicitly set to False."""
    data = {"key": "dict_value"}
    with mock.patch.dict(os.environ, {"KEY": "env_value"}):
        # Even if KEY is in env, it should take dict_value because env_override is False
        val = get_config_value("key", data, env_override=False)
        assert val == "dict_value"
