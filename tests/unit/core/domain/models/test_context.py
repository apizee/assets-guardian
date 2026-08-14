"""Tests for the Context class representing runtime settings and parameters."""

import pytest

from assets_guardian.core.config.app_config import AppConfig, AppEnv
from assets_guardian.core.config.author_config import AuthorConfig
from assets_guardian.core.config.cache_config import CacheConfig
from assets_guardian.core.config.logging_config import LoggingConfig
from assets_guardian.core.config.paths_config import PathsConfig
from assets_guardian.core.domain.models.context import AssetsGuardianMode, Context
from assets_guardian.core.domain.models.location import Location


@pytest.fixture
def valid_location() -> Location:
    """Provide a valid mock Location instance for testing."""
    return Location("local:path/to/file")


@pytest.fixture
def valid_app_config() -> AppConfig:
    """Provide a fully configured AppConfig instance with standard options."""
    return AppConfig(
        env=AppEnv.PROD,
        version="1.0.0",
        author=AuthorConfig(fullname="Test Author", email="author@example.com"),
        logging=LoggingConfig(
            console_level="INFO",
            file_level="INFO",
            max_size=10,
            max_files=5,
            file_basename="test",
        ),
        integrations={},
        paths=PathsConfig(
            excel=Location("local:tests/data/test.xlsx"),
            pdf=Location("local:tests/data/report.pdf"),
            rules=Location("local:tests/data/rules.yml"),
            excel_config=Location("local:excel_config.json"),
            pdf_config=Location("local:pdf_config.json"),
            employees=Location("local:employees.json"),
            config_path=Location("local:config.yml"),
        ),
        cache=CacheConfig(
            batch_size=64,
            cache_dir=".test_cache",
        ),
    )


@pytest.fixture
def valid_context_data(valid_app_config) -> dict:
    """Provide a dictionary of valid initialization parameters for Context model."""
    return {
        "app_config": valid_app_config,
        "dry_run": False,
        "verbose": True,
        "quiet": False,
        "no_interaction": True,
        "mode": AssetsGuardianMode.SYNC,
    }


def test_context_creation_success(valid_context_data, valid_app_config) -> None:
    """Verify that a Context instance is initialized successfully when valid inputs are provided."""
    context = Context(**valid_context_data)
    assert context.app_config == valid_app_config
    assert context.dry_run is False
    assert context.mode == AssetsGuardianMode.SYNC


@pytest.mark.parametrize(
    "field, invalid_value",
    [
        ("app_config", 123),
        ("dry_run", "no"),
        ("no_interaction", None),
        ("mode", "invalid"),
    ],
)
def test_context_type_validation(valid_context_data, field, invalid_value) -> None:
    """Verify that Context raises TypeError or ValueError when fields receive invalid types or values."""
    data = valid_context_data.copy()
    data[field] = invalid_value
    with pytest.raises((TypeError, ValueError)):
        Context(**data)


@pytest.mark.parametrize(
    "field",
    ["app_config"],
)
def test_context_mandatory_fields_empty_raises(valid_context_data, field) -> None:
    """Verify that Context raises TypeError when mandatory fields are omitted or set to None."""
    data = valid_context_data.copy()
    data[field] = None  # None because it's an object now, not a string
    with pytest.raises(TypeError, match="must be a AppConfig"):
        Context(**data)


def test_context_immutability(valid_context_data) -> None:
    """Verify that Context fields are frozen and cannot be modified after instantiation."""
    context = Context(**valid_context_data)
    with pytest.raises(AttributeError):
        context.dry_run = True  # type: ignore


def test_context_slots(valid_context_data) -> None:
    """Verify that Context prevents dynamic attribute addition via __slots__ constraints."""
    context = Context(**valid_context_data)
    with pytest.raises((AttributeError, TypeError)):
        context.new_attr = "val"  # type: ignore
