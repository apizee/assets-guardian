import logging
from collections.abc import Iterable
from typing import Any

from assets_guardian.core.domain.models.finding import Finding, SeverityType
from assets_guardian.core.domain.models.identity import Identity
from assets_guardian.core.domain.models.rules.comparison import IComparisonRule
from assets_guardian.core.domain.registry.rule_registry import RuleRegistry

logger = logging.getLogger(__name__)


def index_users(users: Iterable[Identity]) -> dict[str, Identity]:
    """Indexes users by their external identifier.

    Args:
        users: The user identities to index.

    Returns:
        dict[str, Identity]: Dictionary mapping external_id to the Identity object.
    """
    return {u.external_id: u for u in users if u.external_id}


@RuleRegistry.register("COMPARE-001")
class GitlabNewUserComparisonRule(IComparisonRule):
    """Detects new GitLab users created or added."""

    rule_id: str = "COMPARE-001"

    def __init__(self, **kwargs: Any) -> None:
        self.instance_id = kwargs.get("instance_id", "default")
        self._name = kwargs.get("name", "GitLab user additions")
        self._description = kwargs.get(
            "description", "Detects the creation or addition of new users on GitLab."
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

    def evaluate(  # type: ignore
        self, old_entries: Iterable[Identity], new_entries: Iterable[Identity]
    ) -> Iterable[Finding]:
        """Compares lists to identify new users.

        Args:
            old_entries: The old identities (baseline).
            new_entries: The new collected identities.

        Yields:
            Finding: Detected discrepancy for each new user.
        """
        old_entries_list = list(old_entries)
        if not old_entries_list:
            old_entries_list = list(self.load_baseline())

        old_users = index_users(old_entries_list)
        new_users = index_users(new_entries)

        for user_id, new_user in new_users.items():
            if user_id not in old_users:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=f"New GitLab user: {new_user.name}",
                    description=(
                        f"User '{new_user.name}' ({new_user.email or new_user.username}) "
                        f"was created or added in GitLab."
                    ),
                    source="gitlab",
                    instance_id=self.instance_id,
                    entities_impacted=[new_user.name],
                    metadata={
                        "external_id": new_user.external_id,
                        "email": new_user.email,
                        "username": new_user.username,
                        "state": str(new_user.state) if new_user.state else None,
                    },
                )


@RuleRegistry.register("COMPARE-002")
class GitlabDeletedUserComparisonRule(IComparisonRule):
    """Detects deleted users in GitLab."""

    rule_id: str = "COMPARE-002"

    def __init__(self, **kwargs: Any) -> None:
        self.instance_id = kwargs.get("instance_id", "default")
        self._name = kwargs.get("name", "GitLab user deletions")
        self._description = kwargs.get("description", "Detects user deletions from GitLab.")
        severity_value = kwargs.get("severity")
        if not severity_value:
            logger.warning(
                "Rule %s: no 'severity' configured in rules_config.yml, defaulting to %s.",
                self.rule_id,
                SeverityType.WARNING,
            )
            severity_value = SeverityType.WARNING
        self._severity = severity_value

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

    def evaluate(  # type: ignore
        self, old_entries: Iterable[Identity], new_entries: Iterable[Identity]
    ) -> Iterable[Finding]:
        """Compares lists to identify deleted users.

        Args:
            old_entries: The old identities (baseline).
            new_entries: The new collected identities.

        Yields:
            Finding: Detected discrepancy for each deleted user.
        """
        old_entries_list = list(old_entries)
        if not old_entries_list:
            old_entries_list = list(self.load_baseline())

        old_users = index_users(old_entries_list)
        new_users = index_users(new_entries)

        for user_id, old_user in old_users.items():
            if user_id not in new_users:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=f"User deleted in GitLab: {old_user.name}",
                    description=(
                        f"User '{old_user.name}' ({old_user.email or old_user.username}) "
                        f"was deleted from GitLab."
                    ),
                    source="gitlab",
                    instance_id=self.instance_id,
                    entities_impacted=[old_user.name],
                    metadata={
                        "external_id": old_user.external_id,
                        "email": old_user.email,
                        "username": old_user.username,
                    },
                )


@RuleRegistry.register("COMPARE-003")
class GitlabUserStatusComparisonRule(IComparisonRule):
    """Detects user status changes (active/blocked) on GitLab."""

    rule_id: str = "COMPARE-003"

    def __init__(self, **kwargs: Any) -> None:
        self.instance_id = kwargs.get("instance_id", "default")
        self._name = kwargs.get("name", "GitLab status changes")
        self._description = kwargs.get(
            "description",
            "Detects status changes (active/blocked) of GitLab users.",
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

    def evaluate(  # type: ignore
        self, old_entries: Iterable[Identity], new_entries: Iterable[Identity]
    ) -> Iterable[Finding]:
        """Compares lists to identify status changes.

        Args:
            old_entries: The old identities (baseline).
            new_entries: The new collected identities.

        Yields:
            Finding: Detected discrepancy for each user whose status changed.
        """
        old_entries_list = list(old_entries)
        if not old_entries_list:
            old_entries_list = list(self.load_baseline())

        old_users = index_users(old_entries_list)
        new_users = index_users(new_entries)

        for user_id, new_user in new_users.items():
            old_user = old_users.get(user_id)
            if not old_user or not new_user.state or old_user.state == new_user.state:
                continue

            yield Finding(
                rule_id=self.rule_id,
                rule_category=self.rule_category,
                severity=self.severity,
                title=f"GitLab status change: {new_user.name}",
                description=(
                    f"The status of user '{new_user.name}' changed from "
                    f"'{old_user.state}' to '{new_user.state}'."
                ),
                source="gitlab",
                instance_id=self.instance_id,
                entities_impacted=[new_user.name],
                metadata={
                    "external_id": new_user.external_id,
                    "email": new_user.email,
                    "username": new_user.username,
                    "old_state": str(old_user.state) if old_user.state else None,
                    "new_state": str(new_user.state),
                },
            )


@RuleRegistry.register("COMPARE-004")
class GitlabUserPrivilegeComparisonRule(IComparisonRule):
    """Detects changes in GitLab users' administrator privileges."""

    rule_id: str = "COMPARE-004"

    def __init__(self, **kwargs: Any) -> None:
        self.instance_id = kwargs.get("instance_id", "default")
        self._name = kwargs.get("name", "GitLab privilege changes")
        self._description = kwargs.get(
            "description",
            "Detects changes in user administrator privileges on GitLab.",
        )
        severity_value = kwargs.get("severity")
        if not severity_value:
            logger.warning(
                "Rule %s: no 'severity' configured in rules_config.yml, defaulting to %s.",
                self.rule_id,
                SeverityType.DANGER,
            )
            severity_value = SeverityType.DANGER
        self._severity = severity_value

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

    def evaluate(  # type: ignore
        self, old_entries: Iterable[Identity], new_entries: Iterable[Identity]
    ) -> Iterable[Finding]:
        """Compares lists to identify privilege changes.

        Args:
            old_entries: The old identities (baseline).
            new_entries: The new collected identities.

        Yields:
            Finding: Detected discrepancy for each user whose admin role changed.
        """
        old_entries_list = list(old_entries)
        if not old_entries_list:
            old_entries_list = list(self.load_baseline())

        old_users = index_users(old_entries_list)
        new_users = index_users(new_entries)

        for user_id, new_user in new_users.items():
            old_user = old_users.get(user_id)
            if not old_user or old_user.is_privileged == new_user.is_privileged:
                continue

            action = (
                "promoted to administrator"
                if new_user.is_privileged
                else "demoted from administrator role"
            )
            yield Finding(
                rule_id=self.rule_id,
                rule_category=self.rule_category,
                severity=self.severity,
                title=f"GitLab privilege modification: {new_user.name}",
                description=f"User '{new_user.name}' was {action}.",
                source="gitlab",
                instance_id=self.instance_id,
                entities_impacted=[new_user.name],
                metadata={
                    "external_id": new_user.external_id,
                    "email": new_user.email,
                    "username": new_user.username,
                    "was_admin": old_user.is_privileged,
                    "is_admin": new_user.is_privileged,
                },
            )
