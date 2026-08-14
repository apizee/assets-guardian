from dataclasses import dataclass
from enum import StrEnum

from assets_guardian.core.config.app_config import AppConfig
from assets_guardian.core.domain.models.validator import validate_field


class AssetsGuardianMode(StrEnum):
    SYNC = "sync"
    AUDIT = "audit"
    CHECK = "check"
    SCRIPT = "script"
    UNRECOGNIZED = "unrecognized"


@dataclass(frozen=True, slots=True, kw_only=True)
class Context:
    """Global application execution context.

    Attributes:
        app_config: Loaded and parsed application configuration.
        dry_run: If True, simulate operations without modifying resources.
        verbose: Enable detailed logging output.
        quiet: Suppress standard output logs (minimal logs).
        no_interaction: Disable interactive user prompts.
        mode: Name of the executed command mode (sync, audit, check, etc.).
    """

    # Configuration
    app_config: AppConfig

    # Execution
    dry_run: bool
    verbose: bool
    quiet: bool
    no_interaction: bool
    mode: AssetsGuardianMode

    def __post_init__(self) -> None:
        validate_field(self, "app_config", AppConfig)
        validate_field(self, "dry_run", bool)
        validate_field(self, "verbose", bool)
        validate_field(self, "quiet", bool)
        validate_field(self, "no_interaction", bool)
        validate_field(self, "mode", AssetsGuardianMode)
