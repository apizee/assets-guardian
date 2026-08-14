"""Tests for the CLI commands."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from assets_guardian.cli.audit import run_audit_command
from assets_guardian.cli.check import run_check_command
from assets_guardian.cli.script import run_script_command
from assets_guardian.cli.sync import run_sync_command
from assets_guardian.core.domain.models.context import Context


@pytest.fixture
def mock_ctx():
    """Provide a mock Context with populated paths configurations for CLI tests."""
    ctx = MagicMock(spec=Context)
    ctx.app_config.integrations = {}
    ctx.app_config.paths.pdf.clean_path = "report.pdf"
    ctx.app_config.paths.pdf_config.clean_path = "pdf_config.json"
    ctx.app_config.paths.excel.clean_path = "baseline.xlsx"
    ctx.app_config.paths.excel_config.clean_path = "excel_config.json"
    return ctx


@patch("assets_guardian.cli.audit.CheckEngine")
@patch("assets_guardian.cli.audit.instantiate_collectors")
@patch("assets_guardian.cli.audit.AuditEngine")
@patch("assets_guardian.cli.audit.PdfEngine")
def test_run_audit_command(
    mock_pdf_engine_cls, mock_audit_engine_cls, mock_instantiate, mock_check_cls, mock_ctx
):
    """Verify that the run_audit_command properly orchestrates verification, collection, audit execution, and PDF report generation."""
    mock_check = mock_check_cls.return_value
    mock_check.run.return_value = True

    mock_audit_engine = mock_audit_engine_cls.return_value
    mock_audit_engine.run.return_value = {}

    run_audit_command(mock_ctx)

    mock_check.run.assert_called_once_with(mock_ctx)
    mock_audit_engine.run.assert_called_once()
    mock_pdf_engine_cls.return_value.generate.assert_called_once()


@patch("assets_guardian.cli.check.CheckEngine")
def test_run_check_command(mock_check_cls, mock_ctx):
    """Verify that run_check_command instantiates the CheckEngine and runs config verification."""
    mock_check = mock_check_cls.return_value
    mock_check.run.return_value = True

    run_check_command(mock_ctx)
    mock_check.run.assert_called_once_with(mock_ctx)


@patch("assets_guardian.cli.sync.CheckEngine")
@patch("assets_guardian.cli.sync.instantiate_collectors")
@patch("assets_guardian.cli.sync.SyncEngine")
@patch("assets_guardian.cli.sync.ExcelEngine")
def test_run_sync_command(
    mock_excel_engine_cls, mock_sync_engine_cls, mock_instantiate, mock_check_cls, mock_ctx
):
    """Verify that the run_sync_command orchestrates verification, synchronization engine execution, and Excel report generation."""
    mock_check = mock_check_cls.return_value
    mock_check.run.return_value = True

    mock_sync_engine = mock_sync_engine_cls.return_value
    mock_sync_engine.run.return_value = {}

    run_sync_command(mock_ctx)

    mock_check.run.assert_called_once_with(mock_ctx)
    mock_sync_engine.run.assert_called_once()
    mock_excel_engine_cls.return_value.generate.assert_called_once()


@pytest.mark.parametrize("name", ["user_script", "user_script.py"])
def test_run_script_command(tmp_path, mock_ctx, name):
    """Verify that run_script_command loads the script file and calls its run entry point with the context."""
    script_file = tmp_path / "user_script.py"
    script_file.write_text("received = []\ndef run(ctx):\n    received.append(ctx)\n")

    with patch("assets_guardian.cli.script.DIR_SCRIPTS", tmp_path):
        run_script_command(mock_ctx, name)

    module = sys.modules.pop("assets_guardian_script_user_script")
    assert module.received == [mock_ctx]
