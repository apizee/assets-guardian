"""Smoke tests to validate that the Assets Guardian CLI is loaded and triggered correctly."""

import logging

import pytest
from click.testing import CliRunner

from assets_guardian.cli.main import cli
from assets_guardian.core.config.app_config import AppConfig, AppEnv
from assets_guardian.core.config.author_config import AuthorConfig
from assets_guardian.core.config.cache_config import CacheConfig
from assets_guardian.core.config.logging_config import LoggingConfig
from assets_guardian.core.config.paths_config import PathsConfig
from assets_guardian.core.domain.models.context import AssetsGuardianMode
from assets_guardian.core.domain.models.location import Location


class TestCLI:
    """Tests suite for verifying the CLI entrypoint commands and arguments parsing."""

    @pytest.fixture(autouse=True)
    def mock_config_and_logs(self, mocker):
        """Prepare mocks for YAML configurations, logging, and core engine triggers to isolate CLI interactions."""
        # Mock load_yaml_config
        mocker.patch("assets_guardian.cli.main.load_yaml_config", return_value={})

        # Mock AppConfig.create_from_dict

        mock_app_config = AppConfig(
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
            integrations={"gitlab": {"prod": {}}},
            paths=PathsConfig(
                excel=Location("local:test.xlsx"),
                pdf=Location("local:report.pdf"),
                rules=Location("local:rules.yml"),
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
        self.mock_app_config = mock_app_config
        mocker.patch.object(AppConfig, "create_from_dict", return_value=mock_app_config)

        # Mock init_logging
        self.mock_init_logging = mocker.patch("assets_guardian.cli.main.init_logging")

        # Mock discover_all
        mocker.patch("assets_guardian.cli.main.discover_all")

        # Mock run_sync_command, run_audit_command, run_check_command and
        # run_script_command to avoid side effects
        mocker.patch("assets_guardian.cli.main.run_sync_command")
        mocker.patch("assets_guardian.cli.main.run_audit_command")
        mocker.patch("assets_guardian.cli.main.run_check_command")
        mocker.patch("assets_guardian.cli.main.run_script_command")

    def test_help_returns_zero(self) -> None:
        """Verify that running 'assets-guardian --help' successfully prints the help menu and exits with 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Assets Guardian, IAM governance tool." in result.output

    def test_sync_defaults(self, mocker) -> None:
        """Verify that the 'sync' command executes the sync command handler successfully with default options."""
        mock_run = mocker.patch("assets_guardian.cli.main.run_sync_command")
        runner = CliRunner()
        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_sync_dry_run(self, mocker) -> None:
        """Verify that passing the '--dry-run' flag sets dry_run to True in the configuration passed to the sync command."""
        mock_run = mocker.patch("assets_guardian.cli.main.run_sync_command")
        runner = CliRunner()
        result = runner.invoke(cli, ["--dry-run", "sync"])
        assert result.exit_code == 0
        # Verify that dry_run is True in the first argument of the invocation call
        args, _ = mock_run.call_args
        assert args[0].dry_run is True

    def test_audit_defaults(self, mocker) -> None:
        """Verify that the 'audit' command executes the audit command handler successfully with default options."""
        mock_run = mocker.patch("assets_guardian.cli.main.run_audit_command")
        runner = CliRunner()
        result = runner.invoke(cli, ["audit"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_audit_custom_report(self, mocker) -> None:
        """Verify that passing the '--dry-run' flag sets dry_run to True in the configuration passed to the audit command."""
        mock_run = mocker.patch("assets_guardian.cli.main.run_audit_command")
        runner = CliRunner()
        result = runner.invoke(cli, ["--dry-run", "audit"])
        assert result.exit_code == 0
        mock_run.assert_called_once()
        args, _ = mock_run.call_args
        assert args[0].dry_run is True

    def test_check_command(self, mocker) -> None:
        """Verify that the 'check' command runs the configuration checking routine successfully."""
        mock_run = mocker.patch("assets_guardian.cli.main.run_check_command")
        runner = CliRunner()
        result = runner.invoke(cli, ["check"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_script_command(self, mocker) -> None:
        """Verify that the 'script' command executes the script command handler with the script name."""
        mock_run = mocker.patch("assets_guardian.cli.main.run_script_command")
        runner = CliRunner()
        result = runner.invoke(cli, ["script", "my_script"])
        assert result.exit_code == 0
        mock_run.assert_called_once()
        args, _ = mock_run.call_args
        assert args[0].mode is AssetsGuardianMode.SCRIPT
        assert args[1] == "my_script"

    def test_script_requires_name(self) -> None:
        """Verify that the 'script' command fails with a usage error when no script name is given."""
        runner = CliRunner()
        result = runner.invoke(cli, ["script"])
        assert result.exit_code != 0

    def test_verbose_flag(self) -> None:
        """Verify that the CLI accepts the '--verbose' global flag successfully."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--verbose", "check"])
        assert result.exit_code == 0
        assert self.mock_app_config.logging.console_level == logging.DEBUG
        self.mock_init_logging.assert_called_once_with(logging_config=self.mock_app_config.logging)

    def test_quiet_flag(self) -> None:
        """Verify that the CLI accepts the '-q' (quiet) global flag successfully."""
        runner = CliRunner()
        result = runner.invoke(cli, ["-q", "check"])
        assert result.exit_code == 0
        assert self.mock_app_config.logging.console_level == logging.CRITICAL
        self.mock_init_logging.assert_called_once_with(logging_config=self.mock_app_config.logging)

    def test_custom_config(self) -> None:
        """Verify that the CLI accepts a custom configuration file path via the '--config' option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", "other.yml", "check"])
        assert result.exit_code == 0
