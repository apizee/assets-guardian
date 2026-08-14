from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from assets_guardian.core.config.loader import get_config_value, get_project_version
from assets_guardian.core.domain.models.validator import validate_field

from .author_config import AuthorConfig
from .cache_config import CacheConfig
from .logging_config import LoggingConfig
from .paths_config import PathsConfig


class AppEnv(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


DRY_RUN_ENVIRONMENTS = {AppEnv.TEST, AppEnv.DEV}

# Configuration Constants
CORE_KEYS = {"env", "version", "author", "notification_email", "logging", "paths", "cache"}

# Default Values
DEFAULT_LOGGING_CONSOLE_LEVEL = "INFO"
DEFAULT_LOGGING_FILE_LEVEL = "DEBUG"
DEFAULT_LOGGING_MAX_SIZE = "10"
DEFAULT_LOGGING_MAX_FILES = "5"
DEFAULT_LOGGING_FILE_BASENAME = "assets-guardian"

DEFAULT_PATH_EXCEL = "local:outputs/assets_guardian.xlsx"
DEFAULT_PATH_PDF = "local:outputs/audit_report.pdf"
DEFAULT_PATH_RULES = "local:config/rules_config.yml"
DEFAULT_PATH_EXCEL_CONFIG = "local:config/excel_config.json"
DEFAULT_PATH_PDF_CONFIG = "local:config/pdf_config.json"
DEFAULT_PATH_EMPLOYEES = "local:config/employees.json"

DEFAULT_CACHE_BATCH_SIZE = "64"
DEFAULT_CACHE_DIR = ".assets-guardian_cache"


@dataclass
class AppConfig:
    """Representation of the application configuration.

    Attributes:
        env (AppEnv): Application environment.
        version (str): Application version.
        author (AuthorConfig): Application author identity (fullname and email required).
        notification_emails (list[str]): Recipient emails for audit notifications, if configured.
        logging (LoggingConfig): Logging configuration.
        integrations (dict[str, Any]): Integrations configuration.
        paths (PathsConfig): File paths configuration.
        dry_run_enabled (bool): Indicates if dry-run mode is enabled.
    """

    env: AppEnv
    version: str
    author: AuthorConfig
    logging: LoggingConfig
    integrations: dict[str, Any]
    paths: PathsConfig
    cache: CacheConfig
    notification_emails: list[str] = field(default_factory=list)
    dry_run_enabled: bool = False

    def __post_init__(self) -> None:
        self.dry_run_enabled = self.env in DRY_RUN_ENVIRONMENTS
        validate_field(self, "env", AppEnv)
        validate_field(self, "version", str)
        validate_field(self, "author", AuthorConfig)
        validate_field(self, "logging", LoggingConfig)
        validate_field(self, "integrations", dict, empty=True)
        validate_field(self, "paths", PathsConfig)
        validate_field(self, "cache", CacheConfig)
        validate_field(self, "notification_emails", list, empty=True)
        validate_field(self, "dry_run_enabled", bool)

    @classmethod
    def create_from_dict(
        cls, raw_config: dict[str, Any], config_path: str = "config/config.yml"
    ) -> "AppConfig":
        """
        Converts a raw dictionary into a strongly typed AppConfig object.
        Assumes the configuration has been validated.

        Args:
            raw_config: Dictionary containing raw configuration data.
            config_path: Path to the configuration file.

        Returns:
            An initialized AppConfig instance.
        """

        integrations: dict[str, Any] = {}

        for key, value in raw_config.items():
            if key not in CORE_KEYS:
                integrations[key] = value

        return cls(
            env=AppEnv(get_config_value("env", raw_config, env_name="ENV").lower()),
            version=get_project_version(),
            author=AuthorConfig.from_dict(raw_config.get("author", {})),
            notification_emails=raw_config.get("notification_email") or [],
            logging=LoggingConfig.from_dict(raw_config.get("logging", {})),
            paths=PathsConfig.from_dict(raw_config.get("paths", {}), config_path=config_path),
            cache=CacheConfig.from_dict(raw_config.get("cache", {})),
            integrations=integrations,
        )
