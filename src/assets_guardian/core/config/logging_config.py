import logging
from dataclasses import dataclass, field
from typing import Any

from assets_guardian.core.config.loader import get_config_value
from assets_guardian.core.domain.models.location import Location
from assets_guardian.core.domain.models.validator import validate_field

DEFAULT_LOGGING_CONSOLE_LEVEL = "INFO"
DEFAULT_LOGGING_FILE_LEVEL = "DEBUG"
DEFAULT_LOGGING_MAX_SIZE = "10"
DEFAULT_LOGGING_MAX_FILES = "5"
DEFAULT_LOGGING_FILE_BASENAME = "assets-guardian"
DEFAULT_LOGGING_PATH = "local:logs"


@dataclass
class LoggingConfig:
    """Configuration of application logging.

    Attributes:
        console_level: Logging level for the console.
        file_level: Logging level for the log file.
        max_size: Maximum size of log files in MB.
        max_files: Maximum number of log files to keep.
        file_basename: Base name of the log files.
        path: Directory where log files are written. Must be local; remote logging
            destinations are not supported.
    """

    max_size: int
    max_files: int
    console_level: int
    file_level: int
    file_basename: str = "assets-guardian"
    path: Location = field(default_factory=lambda: Location(DEFAULT_LOGGING_PATH))

    def __post_init__(self) -> None:
        """Validates and processes the logging configuration.

        Raises:
            KeyError: If a logging level is invalid.
        """

        # Retrieve the logging levels map from the logging module
        level_mapping = logging.getLevelNamesMapping()

        # Convert console logging level to integer if it is a string
        if isinstance(self.console_level, str):
            console_level_upper = self.console_level.upper()
            if console_level_upper not in level_mapping:
                raise KeyError(f"Invalid console logging level: {self.console_level}")
            self.console_level = level_mapping[console_level_upper]

        # Convert file logging level to integer if it is a string
        if isinstance(self.file_level, str):
            file_level_upper = self.file_level.upper()
            if file_level_upper not in level_mapping:
                raise KeyError(f"Invalid file logging level: {self.file_level}")
            self.file_level = level_mapping[file_level_upper]

        # Final type validations
        validate_field(self, "console_level", int)
        validate_field(self, "file_level", int)
        validate_field(self, "max_size", int)
        validate_field(self, "max_files", int)
        validate_field(self, "file_basename", str)
        validate_field(self, "path", Location)

        self.max_size *= 1048576

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LoggingConfig":
        return cls(
            console_level=get_config_value(
                "console_level",
                data,
                default=DEFAULT_LOGGING_CONSOLE_LEVEL,
                env_name="LOGGING_CONSOLE_LEVEL",
            ),
            file_level=get_config_value(
                "file_level",
                data,
                default=DEFAULT_LOGGING_FILE_LEVEL,
                env_name="LOGGING_FILE_LEVEL",
            ),
            max_size=int(
                get_config_value(
                    "max-size",
                    data,
                    default=DEFAULT_LOGGING_MAX_SIZE,
                    env_name="LOGGING_MAX_SIZE",
                )
            ),
            max_files=int(
                get_config_value(
                    "max-files",
                    data,
                    default=DEFAULT_LOGGING_MAX_FILES,
                    env_name="LOGGING_MAX_FILES",
                )
            ),
            file_basename=get_config_value(
                "file-basename",
                data,
                default=DEFAULT_LOGGING_FILE_BASENAME,
                env_name="LOGGING_FILE_BASENAME",
            ),
            path=Location(
                get_config_value(
                    "path",
                    data,
                    default=DEFAULT_LOGGING_PATH,
                    env_name="LOGGING_PATH",
                )
            ),
        )
