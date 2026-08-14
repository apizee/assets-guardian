import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from assets_guardian.core.domain.models.access import Access
from assets_guardian.core.domain.models.finding import Finding, SeverityType
from assets_guardian.core.domain.models.identity import Identity
from assets_guardian.core.domain.models.rules.compliance import IComplianceRule
from assets_guardian.core.domain.registry.rule_registry import RuleRegistry

logger = logging.getLogger(__name__)


@RuleRegistry.register("COMPLIANCE-001")
class Microsoft365UserPrivilegeComplianceRule(IComplianceRule):
    """Lists Microsoft365 users holding an administrator role."""

    rule_id: str = "COMPLIANCE-001"

    def __init__(self, **kwargs: Any) -> None:
        self.instance_id = kwargs.get("instance_id", "default")
        self._name = kwargs.get("name", "Microsoft365 administrator roles")
        self._description = kwargs.get(
            "description",
            "Lists users who hold an administrator role on Microsoft365.",
        )
        severity_value = kwargs.get("severity")
        if not severity_value:
            logger.warning(
                "Rule %s: no 'severity' configured in rules_config.yml, defaulting to %s.",
                self.rule_id,
                SeverityType.INFO,
            )
            severity_value = SeverityType.INFO
        self._severity = severity_value

    @property
    def target_entity(self) -> str:
        return "accesses"

    @property
    def severity(self) -> SeverityType:
        return SeverityType(self._severity)

    @property
    def name(self) -> str:
        return str(self._name)

    @property
    def description(self) -> str:
        return str(self._description)

    def evaluate(  # type: ignore
        self,
        entries: Iterable[Access],
        config: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> Iterable[Finding]:
        """Reports each user who holds a role on Microsoft365.

        Yields:
            Finding: One finding per user/role pair detected.
        """
        seen: dict[str, Finding] = {}
        for access in entries:
            if access.access_type != "role":
                continue

            meta = access.metadata or {}
            user_id = str(meta.get("user_id") or meta.get("user_email") or "unknown")
            if user_id in seen:
                continue

            user_name = meta.get("user_name", "Unknown")
            user_email = meta.get("user_email")
            label = f"{user_name} ({user_email})" if user_email else user_name

            seen[user_id] = Finding(
                rule_id=self.rule_id,
                rule_category=self.rule_category,
                severity=self.severity,
                title=f"Administrator role assigned: {user_name}",
                description=(f"{label} has an administrator role on Microsoft365."),
                source="microsoft365",
                instance_id=self.instance_id,
                entities_impacted=[user_email or user_name],
                metadata={
                    "user_id": user_id,
                    "user_email": user_email,
                    "user_name": user_name,
                    "role": access.name,
                },
            )
        yield from seen.values()


@RuleRegistry.register("COMPLIANCE-002")
class Microsoft365UnknownMailComplianceRule(IComplianceRule):
    """Detects Microsoft365 mailboxes that do not match any employee in employees.json."""

    rule_id: str = "COMPLIANCE-002"

    def __init__(self, **kwargs: Any) -> None:
        self.instance_id = kwargs.get("instance_id", "default")
        self._name = kwargs.get("name", "Microsoft365 unknown employee email")
        self._description = kwargs.get(
            "description",
            "Detects Microsoft365 mailboxes that do not match any employee in employees.json.",
        )
        severity_value = kwargs.get("severity")
        if not severity_value:
            logger.warning(
                "Rule %s: no 'severity' configured in rules_config.yml, defaulting to %s.",
                self.rule_id,
                SeverityType.WARNING,
            )
            severity_value = SeverityType.WARNING
        self._severity = severity_value
        self._employees_file_path = kwargs.get("employees_file_path", "config/employees.json")

    @property
    def target_entity(self) -> str:
        return "users"

    @property
    def severity(self) -> SeverityType:
        return SeverityType(self._severity)

    @property
    def name(self) -> str:
        return str(self._name)

    @property
    def description(self) -> str:
        return str(self._description)

    def __load_know_emails(self) -> list[str]:
        """Extracts the unique list of emails from the configured employees file."""

        if not self._employees_file_path:
            return []

        path = Path(self._employees_file_path)
        if not path.exists():
            return []

        try:
            with path.open(encoding="utf-8") as file:
                employees = json.load(file)
            emails = set()  # set automatically handles duplicates
            for emp in employees:
                emp_emails = emp.get("email", "")
                if emp_emails:
                    emails.add(emp_emails.strip())
            return sorted(emails)
        except Exception:
            return []

    def evaluate(  # type: ignore
        self,
        entries: Iterable[Identity],
        config: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> Iterable[Finding]:
        """Reports each user who holds a role on Microsoft365.

        Yields:
            Finding: One finding per user/role pair detected.
        """
        known_emails = self.__load_know_emails()
        seen: dict[str, Finding] = {}
        for identity in entries:
            if not identity.email:
                continue

            if identity.is_external:
                continue

            if identity.email in known_emails:
                continue

            if identity.external_id in seen:
                continue

            meta = identity.metadata or {}
            user_type = meta.get("userType")

            seen[identity.external_id] = Finding(
                rule_id=self.rule_id,
                rule_category=self.rule_category,
                severity=self.severity,
                title=f"Unknown employee mailbox: {identity.name}",
                description=(
                    f"{identity.name} ({identity.email}) has no matching entry in employees.json."
                ),
                source="microsoft365",
                instance_id=self.instance_id,
                entities_impacted=[identity.email],
                metadata={
                    "user_id": identity.external_id,
                    "user_email": identity.email,
                    "user_name": identity.name,
                    "user_type": user_type,
                },
            )
        yield from seen.values()
