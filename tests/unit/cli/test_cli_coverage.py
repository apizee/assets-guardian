"""Coverage test assertions for CLI execution flows when check engine fails."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from assets_guardian.cli.audit import _local_path_for, _push_report, run_audit_command
from assets_guardian.cli.script import run_script_command
from assets_guardian.cli.sync import run_sync_command
from assets_guardian.core.domain.models.context import Context


@pytest.fixture
def mock_ctx():
    """Provide a mock Context with preset GitLab integrations and cache path configurations."""
    ctx = MagicMock(spec=Context)
    ctx.app_config.integrations = {"gitlab": {"prod": {}}}
    ctx.app_config.paths.pdf.clean_path = "report.pdf"
    ctx.app_config.paths.pdf_config.clean_path = "pdf_config.json"
    ctx.app_config.paths.rules.clean_path = "rules.yml"
    ctx.app_config.cache.batch_size = 64
    ctx.app_config.cache.cache_dir = ".test_cache"
    return ctx


def test_run_audit_command_check_failure(mock_ctx):
    """Verify that run_audit_command raises a RuntimeError if the config check fails."""
    with patch("assets_guardian.cli.audit.CheckEngine") as mock_check_cls:
        mock_check = mock_check_cls.return_value
        mock_check.run.return_value = False

        with pytest.raises(RuntimeError, match="Configuration error"):
            run_audit_command(mock_ctx)


def test_local_path_for_remote_location_uses_cache_dir(mock_ctx):
    """Verify _local_path_for builds a cache_dir-based path when the Location is not local."""
    location = MagicMock(clean_path="baseline.xlsx", is_local=False)

    result = _local_path_for(mock_ctx, location)

    assert result == str(Path(mock_ctx.app_config.cache.cache_dir) / "baseline.xlsx")


def test_push_report_skips_log_when_location_not_remote(mock_ctx, caplog):
    """Verify _push_report does not log the SharePoint message for a non-remote Location."""
    location = MagicMock(is_remote=False)

    with (
        patch("assets_guardian.cli.audit.push_to_location", return_value=True),
        caplog.at_level("INFO", logger="assets_guardian.cli.audit"),
    ):
        _push_report(mock_ctx, location, "/out/report.pdf", "PDF report")

    assert "pushed to SharePoint" not in caplog.text


def test_push_report_logs_error_on_failure(mock_ctx, caplog):
    """Verify _push_report logs an error when push_to_location fails."""
    location = MagicMock(is_remote=True)

    with (
        patch("assets_guardian.cli.audit.push_to_location", return_value=False),
        caplog.at_level("ERROR", logger="assets_guardian.cli.audit"),
    ):
        _push_report(mock_ctx, location, "/out/report.pdf", "PDF report")

    assert "Failed to push the PDF report to SharePoint." in caplog.text


def test_run_audit_command_pushes_excel_and_sends_email_when_configured(mock_ctx, tmp_path):
    """Verify run_audit_command pushes the Excel repository when it exists on disk, and
    sends the audit notification email when a sender and notification_emails are configured."""
    pdf_file = tmp_path / "report.pdf"
    excel_file = tmp_path / "baseline.xlsx"
    excel_file.write_bytes(b"data")

    mock_ctx.app_config.paths.pdf.clean_path = str(pdf_file)
    mock_ctx.app_config.paths.pdf.is_local = True
    mock_ctx.app_config.paths.excel.clean_path = str(excel_file)
    mock_ctx.app_config.paths.excel.is_local = True
    mock_ctx.app_config.notification_emails = ["a@b.com"]

    with (
        patch("assets_guardian.cli.audit.CheckEngine") as mock_check_cls,
        patch("assets_guardian.cli.audit.instantiate_collectors", return_value={}),
        patch("assets_guardian.cli.audit.AuditEngine") as mock_audit_engine_cls,
        patch("assets_guardian.cli.audit.PdfEngine"),
        patch("assets_guardian.cli.audit.push_to_location", return_value=True),
        patch("assets_guardian.cli.audit.SendEmailMicrosoft365") as mock_send_email_cls,
    ):
        mock_check_cls.return_value.run.return_value = True
        mock_audit_engine_cls.return_value.run.return_value = {}
        mock_sender = mock_send_email_cls.from_context.return_value

        run_audit_command(mock_ctx)

    mock_sender.send_email.assert_called_once()
    kwargs = mock_sender.send_email.call_args.kwargs
    assert kwargs["recipients"] == {"to": ["a@b.com"], "cc": []}


def test_run_sync_command_check_failure(mock_ctx):
    """Verify that run_sync_command raises a RuntimeError if the config check fails."""
    with patch("assets_guardian.cli.sync.CheckEngine") as mock_check_cls:
        mock_check = mock_check_cls.return_value
        mock_check.run.return_value = False

        with pytest.raises(RuntimeError, match="Configuration error"):
            run_sync_command(mock_ctx)


def test_run_sync_command_remote_excel_uses_cache_dir_and_logs_push(mock_ctx, caplog):
    """Verify output_path is built from cache_dir when excel is remote, and the
    'pushed to SharePoint' info log fires when the push succeeds for a remote Location."""
    mock_ctx.app_config.paths.excel = MagicMock(
        clean_path="baseline.xlsx", is_local=False, is_remote=True
    )

    with (
        patch("assets_guardian.cli.sync.CheckEngine") as mock_check_cls,
        patch("assets_guardian.cli.sync.instantiate_collectors", return_value={}),
        patch("assets_guardian.cli.sync.SyncEngine") as mock_sync_engine_cls,
        patch("assets_guardian.cli.sync.ExcelEngine") as mock_excel_engine_cls,
        patch("assets_guardian.cli.sync.push_to_location", return_value=True) as mock_push,
        caplog.at_level("INFO", logger="assets_guardian.cli.sync"),
    ):
        mock_check_cls.return_value.run.return_value = True
        mock_sync_engine_cls.return_value.run.return_value = {}

        run_sync_command(mock_ctx)

    expected_path = str(Path(mock_ctx.app_config.cache.cache_dir) / "baseline.xlsx")
    _, kwargs = mock_excel_engine_cls.return_value.generate.call_args
    assert kwargs["output_path"] == expected_path
    mock_push.assert_called_once_with(mock_ctx, mock_ctx.app_config.paths.excel, expected_path)
    assert "Excel repository pushed to SharePoint." in caplog.text


def test_run_sync_command_local_push_success_skips_sharepoint_log(mock_ctx, caplog):
    """Verify the SharePoint info log is skipped when push succeeds but the Location is local."""
    mock_ctx.app_config.paths.excel = MagicMock(
        clean_path="baseline.xlsx", is_local=True, is_remote=False
    )

    with (
        patch("assets_guardian.cli.sync.CheckEngine") as mock_check_cls,
        patch("assets_guardian.cli.sync.instantiate_collectors", return_value={}),
        patch("assets_guardian.cli.sync.SyncEngine") as mock_sync_engine_cls,
        patch("assets_guardian.cli.sync.ExcelEngine"),
        patch("assets_guardian.cli.sync.push_to_location", return_value=True),
        caplog.at_level("INFO", logger="assets_guardian.cli.sync"),
    ):
        mock_check_cls.return_value.run.return_value = True
        mock_sync_engine_cls.return_value.run.return_value = {}

        run_sync_command(mock_ctx)

    assert "pushed to SharePoint" not in caplog.text


def test_run_sync_command_push_failure_logs_error(mock_ctx, caplog):
    """Verify an error is logged when push_to_location fails."""
    mock_ctx.app_config.paths.excel = MagicMock(
        clean_path="baseline.xlsx", is_local=True, is_remote=False
    )

    with (
        patch("assets_guardian.cli.sync.CheckEngine") as mock_check_cls,
        patch("assets_guardian.cli.sync.instantiate_collectors", return_value={}),
        patch("assets_guardian.cli.sync.SyncEngine") as mock_sync_engine_cls,
        patch("assets_guardian.cli.sync.ExcelEngine"),
        patch("assets_guardian.cli.sync.push_to_location", return_value=False),
        caplog.at_level("ERROR", logger="assets_guardian.cli.sync"),
    ):
        mock_check_cls.return_value.run.return_value = True
        mock_sync_engine_cls.return_value.run.return_value = {}

        run_sync_command(mock_ctx)

    assert "Failed to push the Excel repository to SharePoint" in caplog.text


def test_run_script_command_missing_script(tmp_path, mock_ctx):
    """Verify that run_script_command raises a FileNotFoundError when the script file does not exist."""
    with (
        patch("assets_guardian.cli.script.DIR_SCRIPTS", tmp_path),
        pytest.raises(FileNotFoundError, match="not found"),
    ):
        run_script_command(mock_ctx, "ghost")


@pytest.mark.parametrize("name", ["../evil", "sub/dir_script", ""])
def test_run_script_command_invalid_name(mock_ctx, name):
    """Verify that run_script_command rejects empty names and names containing path separators."""
    with pytest.raises(ValueError, match="Invalid script name"):
        run_script_command(mock_ctx, name)


def test_run_script_command_without_run_entry_point(tmp_path, mock_ctx):
    """Verify that run_script_command raises a TypeError when the script has no callable run function."""
    script_file = tmp_path / "no_entry.py"
    script_file.write_text("run = 42\n")

    with (
        patch("assets_guardian.cli.script.DIR_SCRIPTS", tmp_path),
        pytest.raises(TypeError, match="must expose a callable"),
    ):
        run_script_command(mock_ctx, "no_entry")


def test_run_script_command_propagates_script_error(tmp_path, mock_ctx):
    """Verify that exceptions raised inside a user script propagate to the caller."""
    script_file = tmp_path / "boom.py"
    script_file.write_text("def run(ctx):\n    raise RuntimeError('boom')\n")

    with (
        patch("assets_guardian.cli.script.DIR_SCRIPTS", tmp_path),
        pytest.raises(RuntimeError, match="boom"),
    ):
        run_script_command(mock_ctx, "boom")


def test_run_script_command_unloadable_module(tmp_path, mock_ctx):
    """Verify that run_script_command raises an ImportError when the module spec cannot be built."""
    script_file = tmp_path / "weird.py"
    script_file.write_text("def run(ctx):\n    pass\n")

    with (
        patch("assets_guardian.cli.script.DIR_SCRIPTS", tmp_path),
        patch(
            "assets_guardian.cli.script.importlib.util.spec_from_file_location", return_value=None
        ),
        pytest.raises(ImportError, match="Unable to load"),
    ):
        run_script_command(mock_ctx, "weird")
