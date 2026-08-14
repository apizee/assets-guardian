"""Tests for the logging system and color formatters."""

import logging
from pathlib import Path
from unittest import mock

import pytest

from assets_guardian.core.config.logging_config import LoggingConfig
from assets_guardian.core.domain.models.location import Location
from assets_guardian.core.logging.logger import (
    ColorFormatter,
    _ExcludeLoggersFilter,
    get_plugin_logger,
    init_logging,
)


@pytest.fixture
def mock_logging_config() -> LoggingConfig:
    """Provide a mock LoggingConfig for testing initialization parameters."""
    return LoggingConfig(
        console_level="INFO",
        file_level="DEBUG",
        max_size=1,  # 1MB
        max_files=5,
        file_basename="test-app",
    )


def test_get_plugin_logger() -> None:
    """Verify that get_plugin_logger initializes a logger with the correct plugin namespace name."""
    source = "test_source"
    logger = get_plugin_logger(source)
    assert isinstance(logger, logging.Logger)
    assert logger.name == f"assets_guardian.plugins.{source}"


def test_init_logging(mock_logging_config: LoggingConfig, tmp_path: Path) -> None:
    """Verify that init_logging handles cleanup and initialization of file and console log handlers."""
    with (
        mock.patch("assets_guardian.core.logging.logger.Path") as mock_path_cls,
        mock.patch("assets_guardian.core.logging.logger.RotatingFileHandler") as mock_handler_cls,
        mock.patch("logging.getLogger") as mock_get_logger,
    ):
        mock_log_dir = mock.MagicMock()
        mock_path_cls.return_value = mock_log_dir
        mock_log_file = mock.MagicMock()
        mock_log_dir.__truediv__.return_value = mock_log_file

        mock_root_logger = mock.MagicMock()
        mock_asyncio_logger = mock.MagicMock()

        mock_root_logger.handlers = mock.MagicMock()

        def get_logger_side_effect(name=None):
            if name is None:
                return mock_root_logger
            if name == "asyncio":
                return mock_asyncio_logger
            return mock.Mock()

        mock_get_logger.side_effect = get_logger_side_effect

        # hasHandlers is True
        mock_root_logger.hasHandlers.return_value = True
        init_logging(mock_logging_config)
        mock_root_logger.handlers.clear.assert_called_once()

        # hasHandlers is False
        mock_root_logger.handlers.clear.reset_mock()
        mock_handler_cls.reset_mock()
        mock_root_logger.setLevel.reset_mock()
        mock_asyncio_logger.setLevel.reset_mock()
        mock_root_logger.addHandler.reset_mock()

        mock_root_logger.hasHandlers.return_value = False
        init_logging(mock_logging_config)
        mock_root_logger.handlers.clear.assert_not_called()

        # Check common expectations
        mock_path_cls.assert_called_with("logs")
        mock_log_dir.mkdir.assert_called_with(parents=True, exist_ok=True)

        # RotatingFileHandler called with correct args
        mock_handler_cls.assert_called_with(
            mock_log_file,
            maxBytes=mock_logging_config.max_size,
            backupCount=mock_logging_config.max_files,
        )

        # Root logger level set to min(file_level, console_level)
        expected_root_level = min(mock_logging_config.file_level, mock_logging_config.console_level)
        mock_root_logger.setLevel.assert_called_with(expected_root_level)

        # Handlers added to root logger
        assert mock_root_logger.addHandler.call_count == 2

        # Asyncio noise reduced
        mock_asyncio_logger.setLevel.assert_called_with(logging.WARNING)


def test_init_logging_remote_path_falls_back_to_default(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that init_logging warns and falls back to the local default when path is remote."""
    remote_config = LoggingConfig(
        console_level="INFO",
        file_level="DEBUG",
        max_size=1,
        max_files=5,
        file_basename="test-app",
        path=Location("remote:test:some/remote/path"),
    )

    with (
        caplog.at_level(logging.WARNING, logger="assets_guardian.core.logging.logger"),
        mock.patch("assets_guardian.core.logging.logger.Path") as mock_path_cls,
        mock.patch("assets_guardian.core.logging.logger.RotatingFileHandler"),
        mock.patch("logging.getLogger") as mock_get_logger,
    ):
        mock_log_dir = mock.MagicMock()
        mock_path_cls.return_value = mock_log_dir
        mock_log_dir.__truediv__.return_value = mock.MagicMock()

        mock_root_logger = mock.MagicMock()
        mock_root_logger.hasHandlers.return_value = False

        def get_logger_side_effect(name=None):
            if name is None:
                return mock_root_logger
            return mock.Mock()

        mock_get_logger.side_effect = get_logger_side_effect

        init_logging(remote_config)

        mock_path_cls.assert_called_with("logs")
        assert "falling back to the local default" in caplog.text


def test_color_formatter():
    """Verify that ColorFormatter correctly inserts ANSI color codes into log records."""
    formatter = ColorFormatter("%(levelname)s - %(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=10,
        msg="test message",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)
    # Check that levelname was colored (contains ANSI codes)
    assert "\033[31m" in formatted  # Red for ERROR
    assert "ERROR" in formatted
    assert formatted.endswith("test message")

    # Check that levelname was restored
    assert record.levelname == "ERROR"


def test_color_formatter_no_color():
    """Verify that ColorFormatter skips color insertion when a level has no defined color configuration."""
    formatter = ColorFormatter("%(levelname)s - %(message)s")
    # Level with no color defined (if any, but let's use a dummy high level)
    record = logging.LogRecord(
        name="test",
        level=99,
        pathname="test.py",
        lineno=10,
        msg="test message",
        args=(),
        exc_info=None,
    )
    record.levelname = "DUMMY"

    formatted = formatter.format(record)
    assert "DUMMY" in formatted
    assert "\033" not in formatted


def test_exclude_loggers_filter() -> None:
    """Verify that _ExcludeLoggersFilter excludes only records from the configured prefixes."""
    log_filter = _ExcludeLoggersFilter(("httpx", "assets_guardian.plugins.microsoft365"))

    excluded_record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="HTTP Request: GET https://graph.microsoft.com/v1.0/users",
        args=(),
        exc_info=None,
    )
    included_record = logging.LogRecord(
        name="assets_guardian.plugins.dolibarr.collector",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Collected 1 Dolibarr identities.",
        args=(),
        exc_info=None,
    )

    assert log_filter.filter(excluded_record) is False
    assert log_filter.filter(included_record) is True
