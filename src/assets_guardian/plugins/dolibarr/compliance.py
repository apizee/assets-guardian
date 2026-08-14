import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from assets_guardian.core.config.loader import to_str_list
from assets_guardian.core.domain.models.finding import Finding, RuleCategory, SeverityType
from assets_guardian.core.domain.models.identity import Identity, IdentityState
from assets_guardian.core.domain.models.rules.compliance import IComplianceRule
from assets_guardian.core.domain.registry.rule_registry import RuleRegistry

logger = logging.getLogger(__name__)


@RuleRegistry.register("COMPLIANCE-001")
class DolibarrUnknownMailComplianceRule(IComplianceRule):
    """Detects Dolibarr mailboxes that do not match any employee in employees.json."""

    rule_id: str = "COMPLIANCE-001"

    def __init__(self, **kwargs: Any) -> None:
        self.instance_id = kwargs.get("instance_id", "default")
        self._name = kwargs.get("name", "Dolibarr unknown employee email")
        self._description = kwargs.get(
            "description",
            "Detects Dolibarr mailboxes that do not match any employee in employees.json.",
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
                emp_emails = to_str_list(emp.get("email", ""))
                for email in emp_emails:
                    emails.add(email.strip())
            return sorted(emails)
        except Exception:
            return []

    def evaluate(  # type: ignore
        self,
        entries: Iterable[Identity],
        config: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> Iterable[Finding]:
        """Reports each Dolibarr user whose email has no matching employee entry.

        Yields:
            Finding: One finding per unknown employee email detected.
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

            seen[identity.external_id] = Finding(
                rule_id=self.rule_id,
                rule_category=self.rule_category,
                severity=self.severity,
                title=f"Unknown employee mailbox: {identity.name}",
                description=(
                    f"{identity.name} ({identity.email}) has no matching entry in employees.json."
                ),
                source="dolibarr",
                instance_id=self.instance_id,
                entities_impacted=[identity.email],
                metadata={
                    "user_id": identity.external_id,
                    "user_email": identity.email,
                    "user_name": identity.name,
                },
            )
        yield from seen.values()


@RuleRegistry.register("DOLIBARR-005")
class DolibarrDeactivatedUsersRule(IComplianceRule):
    """Lists disabled user accounts in Dolibarr.

    An account is considered disabled if its `statut` field is "0" in the Dolibarr API,
    which is mapped to IdentityState.INACTIVE during collection.
    """

    rule_id: str = "DOLIBARR-005"

    def __init__(self, **kwargs: Any) -> None:
        self.__name: str = kwargs.get("name", "Disabled user accounts")
        self.__description: str = kwargs.get(
            "description",
            "Lists user accounts whose status is deactivated in Dolibarr.",
        )
        severity_value = kwargs.get("severity")
        if not severity_value:
            logger.warning(
                "Rule %s: no 'severity' configured in rules_config.yml, defaulting to %s.",
                self.rule_id,
                SeverityType.INFO,
            )
            severity_value = SeverityType.INFO
        self.__severity = SeverityType(severity_value)
        self.instance_id: str = kwargs.get("instance_id", "default")

    @property
    def rule_category(self) -> RuleCategory:
        return RuleCategory.COMPLIANCE

    @property
    def severity(self) -> SeverityType:
        return self.__severity

    @property
    def target_entity(self) -> str:
        return "users"

    @property
    def name(self) -> str:
        return self.__name

    @property
    def description(self) -> str:
        return self.__description

    def evaluate(  # type: ignore
        self,
        entries: Iterable[Identity],
        config: dict[Any, Any] | None = None,  # noqa: ARG002
    ) -> Iterable[Finding]:
        for identity in entries:
            if identity.state != IdentityState.INACTIVE:
                continue
            yield Finding(
                rule_id=self.rule_id,
                rule_category=self.rule_category,
                severity=self.severity,
                title=f"Disabled account: {identity.name}",
                description=(
                    f"Account '{identity.name}' ({identity.email or identity.username}) "
                    f"is disabled in Dolibarr (status=0)."
                ),
                source="dolibarr",
                instance_id=self.instance_id,
                entities_impacted=[identity.name],
                metadata={
                    "external_id": identity.external_id,
                    "email": identity.email,
                    "username": identity.username,
                },
            )
