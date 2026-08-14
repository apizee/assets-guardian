"""Tests for the AuditEngine orchestrating dynamic rules execution, matrix configuration, and baseline data loading."""

from unittest.mock import MagicMock, patch

import pytest

from assets_guardian.core.cache.cache import CacheManager
from assets_guardian.core.domain.engines.audit_engine import AuditEngine
from assets_guardian.core.domain.engines.collector_engine import CollectorResult
from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.domain.models.identity import Identity
from assets_guardian.core.domain.models.report import Report
from assets_guardian.core.domain.models.rules.comparison import IComparisonRule
from assets_guardian.core.domain.models.rules.rule import IRule


@pytest.fixture
def mock_cache():
    """Provide a mocked CacheManager for isolating file interactions."""
    return MagicMock(spec=CacheManager)


@pytest.fixture
def audit_engine(mock_cache):
    """Provide an instance of AuditEngine with a mocked cache."""
    return AuditEngine(cache=mock_cache)


@pytest.fixture
def mock_context():
    """Provide a mock Context with local rules config and standard options."""
    ctx = MagicMock(spec=Context)
    ctx.app_config.paths.rules.is_local = True
    ctx.app_config.paths.rules.clean_path = "rules.yml"
    ctx.app_config.paths.excel.clean_path = "baseline.xlsx"
    ctx.app_config.integrations = {}
    return ctx


def test_audit_engine_init(mocker):
    """Verify that AuditEngine initializes a default CacheManager when none is provided."""
    mocker.patch("assets_guardian.core.domain.engines.audit_engine.CacheManager")
    engine = AuditEngine()
    assert engine.cache is not None


def test_audit_engine_run_no_collectors(audit_engine, mock_context):
    """Verify that run returns an empty dictionary when no collectors are supplied."""
    results = audit_engine.run([], mock_context)
    assert results == {}


@patch("assets_guardian.core.domain.engines.audit_engine.load_yaml_config")
@patch("assets_guardian.core.domain.engines.audit_engine.RuleRegistry")
@patch("assets_guardian.core.domain.engines.audit_engine.read_workbook")
def test_audit_engine_run_success(
    mock_read_wb, mock_registry, mock_load_yaml, audit_engine, mock_context
):
    """Verify that run executes successfully and generates reports when active collectors and rules are present."""
    collector = MagicMock()
    collector.source_name = "gitlab"
    collector.instance_id = "prod"

    mock_load_yaml.return_value = {"gitlab": {"RULE-001": {"param": 1}}}
    rule_cls = MagicMock(return_value=MagicMock(spec=IRule))
    mock_registry.get_rule.return_value = rule_cls

    mock_context.app_config.integrations = {"gitlab": {"prod": {"config": "val"}}}

    # Mock collector engine result
    collect_result = CollectorResult(
        source_name="gitlab",
        instance_id="prod",
        success=True,
        identities=[],
        assets=[],
        accesses=[],
    )
    audit_engine.collector_engine.run_collect = MagicMock(return_value=collect_result)

    # Mock matrix loading
    mock_read_wb.return_value = {
        "gitlab matrix": {
            "header": {1: {"title": "Profile"}, 2: {"title": "Scope1"}},
            "content": [["Admin", "Maintainer"]],
        },
        "employees": {
            "header": {1: {"title": "Email"}, 2: {"title": "Profil"}},
            "content": [["user@test.com", "Admin"]],
        },
    }

    with patch("assets_guardian.core.domain.engines.audit_engine.Path.exists", return_value=True):
        results = audit_engine.run([collector], mock_context)

    assert ("gitlab", "prod") in results
    assert isinstance(results[("gitlab", "prod")], Report)


@patch("assets_guardian.core.domain.engines.audit_engine.load_yaml_config")
def test_audit_engine_run_no_rules(mock_load_yaml, audit_engine, mock_context):
    """Verify that run generates an empty report when no rules are configured in YAML for the source."""
    collector = MagicMock()
    collector.source_name = "gitlab"
    collector.instance_id = "prod"
    mock_load_yaml.return_value = {}

    results = audit_engine.run([collector], mock_context)
    assert results[("gitlab", "prod")].total_count == 0


@patch("assets_guardian.core.domain.engines.audit_engine.load_yaml_config")
def test_audit_engine_run_remote_rules(mock_load_yaml, audit_engine, mock_context):
    """Verify that run does not execute rules and returns empty report if rules configuration is remote."""
    collector = MagicMock()
    collector.source_name = "gitlab"
    collector.instance_id = "prod"
    mock_context.app_config.paths.rules.is_local = False

    results = audit_engine.run([collector], mock_context)
    assert results[("gitlab", "prod")].total_count == 0


@patch("assets_guardian.core.domain.engines.audit_engine.load_yaml_config")
def test_audit_engine_run_load_yaml_error(mock_load_yaml, audit_engine, mock_context):
    """Verify that run handles YAML loading exceptions gracefully and returns empty reports."""
    collector = MagicMock()
    collector.source_name = "gitlab"
    collector.instance_id = "prod"
    mock_load_yaml.side_effect = Exception("YAML error")

    results = audit_engine.run([collector], mock_context)
    assert results[("gitlab", "prod")].total_count == 0


def test_audit_engine_run_collect_fail(audit_engine, mock_context):
    """Verify that run returns an empty report when collector extraction fails."""
    collector = MagicMock()
    collector.source_name = "gitlab"
    collector.instance_id = "prod"

    # Mock collector engine result fail
    audit_engine.collector_engine.run_collect = MagicMock(
        return_value=CollectorResult(source_name="gitlab", instance_id="prod", success=False)
    )

    with patch.object(AuditEngine, "_AuditEngine__get_active_rules", return_value=[MagicMock()]):
        results = audit_engine.run([collector], mock_context)
        assert results[("gitlab", "prod")].total_count == 0


@patch("assets_guardian.core.domain.engines.audit_engine.read_workbook")
def test_audit_engine_load_matrix_no_file(mock_read_wb, audit_engine, mock_context):
    """Verify that __load_matrix_and_profiles returns empty structures when the workbook file does not exist."""
    with patch("assets_guardian.core.domain.engines.audit_engine.Path.exists", return_value=False):
        matrix, profiles = audit_engine._AuditEngine__load_matrix_and_profiles(
            mock_context, "gitlab"
        )
        assert matrix == {}
        assert profiles == {}


@patch("assets_guardian.core.domain.engines.audit_engine.read_workbook")
def test_audit_engine_load_matrix_error(mock_read_wb, audit_engine, mock_context):
    """Verify that __load_matrix_and_profiles handles workbook reading exceptions gracefully by returning empty maps."""
    with patch("assets_guardian.core.domain.engines.audit_engine.Path.exists", return_value=True):
        mock_read_wb.side_effect = Exception("Excel error")
        matrix, profiles = audit_engine._AuditEngine__load_matrix_and_profiles(
            mock_context, "gitlab"
        )
        assert matrix == {}
        assert profiles == {}


def test_audit_engine_extract_matrix_missing_sheet(audit_engine):
    """Verify that __extract_matrix returns an empty map when the expected matrix sheet is missing."""
    matrix = audit_engine._AuditEngine__extract_matrix({}, "gitlab")
    assert matrix == {}


def test_audit_engine_process_matrix_row_empty(audit_engine):
    """Verify that __process_matrix_row returns an empty map when the row or header definition is empty."""
    assert audit_engine._AuditEngine__process_matrix_row([], {}) == {}
    assert audit_engine._AuditEngine__process_matrix_row([None], {}) == {}


def test_audit_engine_extract_matrix_success(audit_engine):
    """Verify that __extract_matrix correctly processes header columns and maps profile scopes to roles."""
    data = {
        "some other sheet": {},
        "test matrix": {
            "header": {1: {"title": "Profile"}, 2: {"title": "Scope1"}},
            "content": [["Admin", "Role1"], [None, "Ignore"]],
        },
    }
    matrix = audit_engine._AuditEngine__extract_matrix(data, "test")
    assert ("Admin", "Scope1") in matrix
    assert matrix[("Admin", "Scope1")] == "Role1"


def test_audit_engine_extract_matrix_with_instance_id(audit_engine):
    """Verify that __extract_matrix handles sheet names containing instance_id."""
    data = {
        "some other sheet": {},
        "test (prod) matrix": {
            "header": {1: {"title": "Profile"}, 2: {"title": "Scope1"}},
            "content": [["Admin", "Role1"]],
        },
    }
    matrix = audit_engine._AuditEngine__extract_matrix(data, "test", "prod")

    assert ("Admin", "Scope1") in matrix
    assert matrix[("Admin", "Scope1")] == "Role1"


def test_audit_engine_extract_matrix_empty_role(audit_engine):
    """Verify that __extract_matrix ignores columns and values that resolve to empty strings or None."""
    data = {
        "test matrix": {
            "header": {1: {"title": "Profile"}, 2: {"title": "Scope1"}},
            "content": [["Admin", None], ["User", ""]],
        }
    }
    matrix = audit_engine._AuditEngine__extract_matrix(data, "test")
    assert matrix == {}


@patch("assets_guardian.core.domain.engines.audit_engine.load_yaml_config")
def test_audit_engine_get_active_rules_yaml_anchor(mock_load_yaml, audit_engine, mock_context):
    """Verify that __get_active_rules successfully ignores YAML anchors (e.g. '<<') and resolves valid rules."""
    mock_load_yaml.return_value = {"gitlab": {"<<": "anchor", "RULE-001": {"p": 1}}}
    with patch("assets_guardian.core.domain.engines.audit_engine.RuleRegistry") as mock_registry:
        mock_registry.get_rule.return_value = MagicMock(return_value=MagicMock())
        rules = audit_engine._AuditEngine__get_active_rules("gitlab", "prod", mock_context)
        assert len(rules) == 1


@patch("assets_guardian.core.domain.engines.audit_engine.load_yaml_config")
def test_audit_engine_get_active_rules_registry_error(mock_load_yaml, audit_engine, mock_context):
    """Verify that __get_active_rules handles rule registry lookups failure gracefully, returning only successfully parsed rules."""
    mock_load_yaml.return_value = {"gitlab": {"RULE-001": {"p": 1}}}
    with patch("assets_guardian.core.domain.engines.audit_engine.RuleRegistry") as mock_registry:
        mock_registry.get_rule.side_effect = Exception("Registry error")
        rules = audit_engine._AuditEngine__get_active_rules("gitlab", "prod", mock_context)
        assert len(rules) == 0


def test_audit_engine_launch_audit_exception(audit_engine, mock_context):
    """Verify that __launch_audit handles unexpected internal audit failures, logging errors and returning an empty report."""
    collector = MagicMock()
    collector.source_name = "gitlab"
    collector.instance_id = "prod"
    # Cause exception by making get_file_path raise
    audit_engine.cache.get_file_path.side_effect = Exception("Cache error")

    # Access private method for test
    report = audit_engine._AuditEngine__launch_audit(collector, mock_context)
    assert isinstance(report, Report)
    assert report.total_count == 0


def test_audit_engine_load_old_data_excel_missing(audit_engine, mock_context) -> None:
    """__load_old_data returns {} immediately when the baseline Excel file doesn't exist."""
    mock_rule = MagicMock(spec=IComparisonRule)
    mock_rule.rule_category.value = "COMPARISON"

    with patch("assets_guardian.core.domain.engines.audit_engine.Path.exists", return_value=False):
        old_data = audit_engine._AuditEngine__load_old_data(mock_context, [mock_rule])

    assert old_data == {}


def test_audit_engine_load_old_data_baseline_exception(audit_engine, mock_context) -> None:
    """__load_old_data skips a rule and logs when load_baseline raises."""
    mock_rule = MagicMock(spec=IComparisonRule)
    mock_rule.target_entity = "users"
    mock_rule.rule_category.value = "COMPARISON"
    mock_rule.load_baseline.side_effect = Exception("Baseline error")

    with patch("assets_guardian.core.domain.engines.audit_engine.Path.exists", return_value=True):
        old_data = audit_engine._AuditEngine__load_old_data(mock_context, [mock_rule])

    # Exception is caught; result has no entries for the failing rule
    assert old_data == {}


def test_audit_engine_load_old_data_empty_entries_skipped(audit_engine, mock_context) -> None:
    """__load_old_data skips rules whose load_baseline returns an empty iterable."""
    mock_rule = MagicMock(spec=IComparisonRule)
    mock_rule.target_entity = "users"
    mock_rule.load_baseline.return_value = []  # empty, falsy branch

    with patch("assets_guardian.core.domain.engines.audit_engine.Path.exists", return_value=True):
        old_data = audit_engine._AuditEngine__load_old_data(mock_context, [mock_rule])

    assert old_data == {}


def test_audit_engine_load_old_data_duplicate_target_extends_existing(
    audit_engine, mock_context
) -> None:
    """__load_old_data appends entries to an existing target key (no duplicate init)."""
    fake_entry = MagicMock(spec=Identity)

    rule_a = MagicMock(spec=IComparisonRule)
    rule_a.target_entity = "users"
    rule_a.load_baseline.return_value = [fake_entry]

    rule_b = MagicMock(spec=IComparisonRule)
    rule_b.target_entity = "users"  # same entity as rule_a
    rule_b.load_baseline.return_value = [fake_entry]

    with patch("assets_guardian.core.domain.engines.audit_engine.Path.exists", return_value=True):
        old_data = audit_engine._AuditEngine__load_old_data(mock_context, [rule_a, rule_b])

    # Both entries land under "users"; target init branch skipped on second rule
    assert len(old_data["users"]) == 2
