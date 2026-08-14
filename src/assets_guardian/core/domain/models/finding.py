from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from assets_guardian.core.domain.models.validator import validate_field


class SeverityType(StrEnum):
    CRITICAL = "CRITICAL"
    DANGER = "DANGER"
    WARNING = "WARNING"
    INFO = "INFO"


class RuleCategory(StrEnum):
    COMPARISON = "comparison"
    COMPLIANCE = "compliance"
    MATRIX = "matrix"


@dataclass(frozen=True, slots=True, kw_only=True)
class Finding:
    """
    Normalized representation of a discrepancy or anomaly detected by an
    audit rule.

    A finding is produced by the evaluation of an IRule (IComparisonRule,
    IComplianceRule, or IMatrixRule). It is then aggregated by the
    ComplianceEngine and rendered in the PDF report, where it can be filtered
    by severity and grouped by source.

    Attributes:
        rule_id: Unique identifier of the rule that produced this finding
            (e.g., "IAM-001", "CMP-001", "MTX-001").
        rule_category: Category of the rule that produced this finding
            (comparison, compliance, matrix).
        severity: Severity level of the finding (CRITICAL, DANGER, WARNING, INFO).
        title: Readable title of the finding (e.g., "Users without 2FA").
        description: Detailed description of the detected anomaly.
        entities_impacted: List of impacted entities (users, projects,
            groups, etc.) as human-readable labels.
        source: Source where the finding originated (gitlab, microsoft365,
            dolibarr, etc.).
        instance_id: Identifier of the audited instance (e.g., "gitlab.com").
        timestamp: Creation date and time of the finding.
        metadata: Custom arbitrary metadata dict (e.g., raw data
            useful for debugging or drilling down in reports).
    """

    # Rule
    rule_id: str
    rule_category: RuleCategory

    severity: SeverityType

    # Content
    title: str
    description: str | None = None

    # Contexte
    source: str
    instance_id: str
    entities_impacted: list[str]

    # Temps
    timestamp: datetime | None = None

    # Divers
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        validate_field(self, "rule_id", str)
        validate_field(self, "rule_category", RuleCategory)
        validate_field(self, "severity", SeverityType)
        validate_field(self, "title", str)
        validate_field(self, "description", str, optional=True)
        validate_field(self, "source", str)
        validate_field(self, "instance_id", str)
        validate_field(self, "entities_impacted", list)
        validate_field(self, "timestamp", datetime, optional=True)
        validate_field(self, "metadata", dict, optional=True)
