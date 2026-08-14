import logging
import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Any

from assets_guardian.core.domain.models.finding import Finding, RuleCategory, SeverityType
from assets_guardian.core.domain.models.identity import Identity, IdentityType
from assets_guardian.core.domain.models.rules.compliance import IComplianceRule
from assets_guardian.core.domain.registry.rule_registry import RuleRegistry

logger = logging.getLogger(__name__)


def _normalize_name_part(value: str) -> str:
    """Strips accents/diacritics and non-alphanumeric characters, then lowercases.

    Args:
        value: Raw name part (e.g. a first or last name).

    Returns:
        str: The normalized value (e.g. "Dupré-Lafontaine" -> "duprelafontaine").
    """
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]", "", ascii_only).lower()


def _resolve_severity(rule_id: str, raw_severity: Any, default: SeverityType) -> SeverityType:
    """Resolves a rule's severity from its YAML configuration.

    Args:
        rule_id: Identifier of the rule (for logging purposes).
        raw_severity: Raw 'severity' value read from the YAML configuration, if any.
        default: Hardcoded fallback severity to use when unset or invalid.

    Returns:
        SeverityType: The severity read from configuration, or the default.
    """
    if not raw_severity:
        logger.warning(
            "No severity configured for rule %s, falling back to default: %s",
            rule_id,
            default,
        )
        return default

    try:
        return SeverityType(str(raw_severity).upper())
    except ValueError:
        logger.warning(
            "Invalid severity '%s' configured for rule %s, falling back to default: %s",
            raw_severity,
            rule_id,
            default,
        )
        return default


@RuleRegistry.register("DEFAULT-001")
class MultiFactorAuthRule(IComplianceRule):
    """Verifies that MFA (Multi-Factor Authentication) is enabled for all users.

    Attributes:
        rule_id: Unique rule identifier (DEFAULT-001).
    """

    rule_id: str = "DEFAULT-001"

    def __init__(self, **kwargs: Any) -> None:
        """Retrieves rule configuration from YAML.

        Args:
            **kwargs: Variable arguments containing 'name' and 'description'.
        """

        self.__name = kwargs.get("name", "MFA disabled")
        self.__description = kwargs.get(
            "description",
            "Multi-Factor Authentication must be enabled for user accounts.",
        )
        severity_value = kwargs.get("severity")
        if not severity_value:
            logger.warning(
                "Rule %s: no 'severity' configured in rules_config.yml, defaulting to %s.",
                self.rule_id,
                SeverityType.DANGER,
            )
            severity_value = SeverityType.DANGER
        self.__severity: SeverityType = SeverityType(severity_value)

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects identities to detect absence of MFA.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each user without MFA.
        """
        for identity in entries:
            # If mfa_enabled is False, generate a finding
            if identity.mfa_enabled is False:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=(
                        f"MFA is not enabled for user '{identity.name}' "
                        f"({identity.email or identity.username})."
                    ),
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={
                        "external_id": identity.external_id,
                        "email": identity.email,
                        "username": identity.username,
                    },
                )


@RuleRegistry.register("DEFAULT-002")
class InactivityRule(IComplianceRule):
    """Verifies if an account has exceeded the allowed inactivity threshold.

    Attributes:
        rule_id: Unique rule identifier (DEFAULT-002).
    """

    rule_id: str = "DEFAULT-002"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Prolonged inactivity")
        self.__description = kwargs.get(
            "description", "The account has had no activity for a long time."
        )

        raw_tiers = kwargs.get("inactivity_threshold_days")
        if not raw_tiers:
            logger.warning(
                "Rule %s: no 'inactivity_threshold_days' configured in rules_config.yml, "
                "defaulting to WARNING/90, DANGER/180, CRITICAL/365.",
                self.rule_id,
            )
            raw_tiers = [
                {"severity": "WARNING", "days": 90},
                {"severity": "DANGER", "days": 180},
                {"severity": "CRITICAL", "days": 365},
            ]
        tiers: list[tuple[int, SeverityType]] = []
        for tier in raw_tiers:
            days = tier.get("days")
            if days is None:
                logger.warning(
                    "Rule %s: a threshold tier is missing 'days', skipping it.",
                    self.rule_id,
                )
                continue

            severity = tier.get("severity")
            if not severity:
                logger.warning(
                    "Rule %s: threshold tier at %s days has no 'severity' configured, "
                    "defaulting to %s.",
                    self.rule_id,
                    days,
                    SeverityType.WARNING,
                )
                severity = SeverityType.WARNING

            tiers.append((int(days), SeverityType(severity)))

        self.__tiers: list[tuple[int, SeverityType]] = sorted(tiers, key=lambda tier: tier[0])

    @property
    def rule_category(self) -> RuleCategory:
        return RuleCategory.COMPLIANCE

    @property
    def severity(self) -> SeverityType:
        return self.__tiers[-1][1]

    @property
    def target_entity(self) -> str:
        return "users"

    @property
    def name(self) -> str:
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Compares the last activity with the configured threshold.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration.

        Yields:
            Finding: A finding for each user inactive for too long.
        """
        now = datetime.now(UTC)

        for identity in entries:
            if identity.last_activity_at:
                # Ensure last_activity_at has timezone info for comparison
                last_activity = identity.last_activity_at
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=UTC)

                inactive_days = now - last_activity

                matched_severity: SeverityType | None = None
                for threshold_days, tier_severity in self.__tiers:
                    if inactive_days > timedelta(days=threshold_days):
                        matched_severity = tier_severity

                if matched_severity is not None:
                    yield Finding(
                        rule_id=self.rule_id,
                        rule_category=self.rule_category,
                        severity=matched_severity,
                        title=self.name,
                        description=(
                            f"User '{identity.name}' has had no activity for "
                            f"{inactive_days.days} days (last activity: "
                            f"{last_activity.strftime('%Y-%m-%d')})."
                        ),
                        source=identity.source,
                        instance_id=(config or {}).get("instance_id", "unknown"),
                        entities_impacted=[identity.name],
                        metadata={
                            "last_activity_at": last_activity.isoformat(),
                            "thresholds": [
                                {"days": days, "severity": str(sev)} for days, sev in self.__tiers
                            ],
                        },
                    )


@RuleRegistry.register("DEFAULT-003")
class ExcessivePermissionsRule(IComplianceRule):
    """Verifies if an account possesses high privileges.

    Attributes:
        rule_id: Unique rule identifier (DEFAULT-003).
    """

    rule_id: str = "DEFAULT-003"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Excessive permissions")
        self.__description = kwargs.get(
            "description", "The account possesses administrative or high privileges."
        )
        severity_value = kwargs.get("severity")
        if not severity_value:
            logger.warning(
                "Rule %s: no 'severity' configured in rules_config.yml, defaulting to %s.",
                self.rule_id,
                SeverityType.DANGER,
            )
            severity_value = SeverityType.DANGER
        self.__severity: SeverityType = SeverityType(severity_value)

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Verifies if an account possesses high privileges.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration.

        Yields:
            Finding: A finding for each privileged user.
        """
        for identity in entries:
            if identity.is_privileged is True:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=f"User '{identity.name}' possesses excessive privileges.",
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={"is_privileged": True},
                )


@RuleRegistry.register("DEFAULT-004")
class UnusualLocationRule(IComplianceRule):
    """Verifies if the last sign-in comes from an unusual IP (outside the company network).

    Attributes:
        rule_id: Unique rule identifier (DEFAULT-004).
    """

    rule_id: str = "DEFAULT-004"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Unusual sign-in location")
        self.__description = kwargs.get(
            "description", "The latest sign-in comes from an IP outside the company network."
        )
        self.__company_ip = kwargs.get("company_network_ip")
        severity_value = kwargs.get("severity")
        if not severity_value:
            logger.warning(
                "Rule %s: no 'severity' configured in rules_config.yml, defaulting to %s.",
                self.rule_id,
                SeverityType.WARNING,
            )
            severity_value = SeverityType.WARNING
        self.__severity: SeverityType = SeverityType(severity_value)

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        if not self.__company_ip:
            return

        try:
            company_ip = ip_address(self.__company_ip)
        except ValueError:
            logger.warning("Invalid company IP configured for DEFAULT-004: {self.__company_ip}")
            return

        for identity in entries:
            if identity.last_sign_in_ip and identity.last_sign_in_ip != company_ip:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=(
                        f"User '{identity.name}' signed in from an "
                        f"unusual IP: {identity.last_sign_in_ip}."
                    ),
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={"last_sign_in_ip": str(identity.last_sign_in_ip)},
                )


@RuleRegistry.register("CTRL_HUMAN_LAST_NAME")
class HumanLastNameFormatRule(IComplianceRule):
    """Verifies that human identities have their last name entirely in uppercase.

    Attributes:
        rule_id: Unique rule identifier (CTRL_HUMAN_LAST_NAME).
    """

    rule_id: str = "CTRL_HUMAN_LAST_NAME"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Last name not uppercase")
        self.__description = kwargs.get(
            "description",
            "Last name must be entered entirely in uppercase, while preserving "
            "accents and special characters (e.g. hyphens).",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.WARNING
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects human identities to detect a last name not fully uppercase.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each human identity whose last name is not
                entirely uppercase.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.HUMAN:
                continue

            if identity.last_name and identity.last_name != identity.last_name.upper():
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=(
                        f"Last name '{identity.last_name}' of user '{identity.name}' "
                        "is not entirely in uppercase."
                    ),
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={
                        "external_id": identity.external_id,
                        "last_name": identity.last_name,
                    },
                )


@RuleRegistry.register("CTRL_HUMAN_FIRST_NAME")
class HumanFirstNameFormatRule(IComplianceRule):
    """Verifies that human identities have their first name properly capitalized.

    Note: only applies to sources exposing structured first_name/last_name
    (e.g. Dolibarr). Identities without first_name (e.g. GitLab, which only
    exposes a single merged 'name' field) are silently skipped.

    Attributes:
        rule_id: Unique rule identifier (CTRL_HUMAN_FIRST_NAME).
    """

    rule_id: str = "CTRL_HUMAN_FIRST_NAME"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "First name not properly capitalized")
        self.__description = kwargs.get(
            "description",
            "First name must be entered in lowercase, with an initial capital "
            "letter for each component, while preserving accents and special "
            "characters (e.g. hyphens).",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.WARNING
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    @staticmethod
    def __is_properly_capitalized(first_name: str) -> bool:
        components = [c for c in re.split(r"[-\s]+", first_name) if c]
        return all(component == component.capitalize() for component in components)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects human identities to detect a first name not properly capitalized.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each human identity whose first name is not
                in title case for each hyphen-separated component.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.HUMAN:
                continue

            if identity.first_name and not self.__is_properly_capitalized(identity.first_name):
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=(
                        f"First name '{identity.first_name}' of user '{identity.name}' "
                        "is not properly capitalized."
                    ),
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={
                        "external_id": identity.external_id,
                        "first_name": identity.first_name,
                    },
                )


@RuleRegistry.register("CTRL_HUMAN_FULL_NAME")
class HumanFullNameFormatRule(IComplianceRule):
    """Verifies that human identities have a properly formatted full name.

    The full name must be the concatenation of the first name and last name,
    separated by a space, suffixed with ' (EXT)' for third-party identities.

    Note: only applies to sources exposing structured first_name/last_name
    (e.g. Dolibarr). Identities without first_name/last_name (e.g. GitLab,
    which only exposes a single merged 'name' field) are silently skipped.

    Attributes:
        rule_id: Unique rule identifier (CTRL_HUMAN_FULL_NAME).
    """

    rule_id: str = "CTRL_HUMAN_FULL_NAME"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Full name badly formatted")
        self.__description = kwargs.get(
            "description",
            "Full name is the concatenation of the first name and last name, "
            "separated by a space. For third-party human identities, the full "
            "name is suffixed with ' (EXT)'.",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.WARNING
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    @staticmethod
    def __expected_full_name(identity: Identity) -> str:
        expected = f"{identity.first_name} {identity.last_name}"
        if identity.is_external:
            expected += " (EXT)"
        return expected

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects human identities to detect a badly formatted full name.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each human identity whose full name does
                not match the expected concatenation of first and last name.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.HUMAN:
                continue

            if not identity.first_name or not identity.last_name:
                continue

            expected = self.__expected_full_name(identity)
            if identity.name != expected:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=(
                        f"Full name '{identity.name}' does not match the expected "
                        f"format '{expected}'."
                    ),
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={
                        "external_id": identity.external_id,
                        "name": identity.name,
                        "expected_name": expected,
                    },
                )


@RuleRegistry.register("CTRL_HUMAN_USERNAME")
class HumanUsernameFormatRule(IComplianceRule):
    """Verifies that human identities have a properly formatted username.

    The username must be composed of the first letter of the first name
    (lowercase) followed by the last name (lowercase), without spaces or
    special characters. An optional sequential number may follow in case of
    a duplicate, placed before the '-ext' status suffix (e.g.
    'eduprelafontainemeza2-ext'). Third-party identities require an '-ext'
    suffix.

    Note: only applies to sources exposing structured first_name/last_name
    (e.g. Dolibarr). Identities without first_name/last_name (e.g. GitLab,
    which only exposes a single merged 'name' field) are silently skipped.

    Note: the PDF also requires an '-admin' suffix for identities "dedicated
    to a high-privilege administrative use". This is NOT checked: the closest
    available signal (Identity.is_privileged) reflects technical admin rights
    on a given tool, not a dedicated administrative identity, and using it
    produces false positives for regular staff who simply hold admin rights
    on their everyday account (e.g. a Dolibarr superadmin).

    Attributes:
        rule_id: Unique rule identifier (CTRL_HUMAN_USERNAME).
    """

    rule_id: str = "CTRL_HUMAN_USERNAME"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Username badly formatted")
        self.__description = kwargs.get(
            "description",
            "Username must be unique, composed of the first letter of the "
            "first name (lowercase) followed by the last name (lowercase), "
            "without spaces or special characters, plus a sequential number "
            "in case of a duplicate. Third-party human identities require an "
            "'-ext' suffix.",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.DANGER
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    @staticmethod
    def __expected_pattern(
        first_name: str, last_name: str, is_external: bool | None
    ) -> re.Pattern[str]:
        first_letter = _normalize_name_part(first_name)[:1]
        last_name_part = _normalize_name_part(last_name)
        radical = re.escape(f"{first_letter}{last_name_part}")

        suffix = "-ext" if is_external else ""

        return re.compile(rf"^{radical}(\d+)?{re.escape(suffix)}$")

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects human identities to detect a badly formatted username.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each human identity whose username does
                not match the expected format.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.HUMAN:
                continue

            if not identity.first_name or not identity.last_name:
                continue

            pattern = self.__expected_pattern(
                identity.first_name, identity.last_name, identity.is_external
            )
            if not identity.username or not pattern.match(identity.username):
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=(
                        f"Username '{identity.username}' of user '{identity.name}' "
                        "does not match the expected format."
                    ),
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={
                        "external_id": identity.external_id,
                        "username": identity.username,
                    },
                )


@RuleRegistry.register("CTRL_HUMAN_EMAIL")
class HumanEmailFormatRule(IComplianceRule):
    """Verifies that human identities have a properly formatted email address.

    The email is composed of the first name and last name, separated by a
    dot, both lowercase with spaces/hyphens removed and accents stripped.
    Third-party identities require a '.ext' suffix.

    Note: only applies to sources exposing structured first_name/last_name
    (e.g. Dolibarr). Identities without first_name/last_name (e.g. GitLab,
    which only exposes a single merged 'name' field) are silently skipped.

    Note: the PDF also requires a '+admin'/'.admin' suffix for identities
    "dedicated to a high-privilege administrative use". This is NOT checked:
    the closest available signal (Identity.is_privileged) reflects technical
    admin rights on a given tool, not a dedicated administrative identity,
    and using it produces false positives for regular staff who simply hold
    admin rights on their everyday account (e.g. a Dolibarr superadmin).

    Attributes:
        rule_id: Unique rule identifier (CTRL_HUMAN_EMAIL).
    """

    rule_id: str = "CTRL_HUMAN_EMAIL"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Email badly formatted")
        self.__description = kwargs.get(
            "description",
            "Email address is composed of the first name and last name "
            "separated by a dot, both in lowercase, with spaces/hyphens "
            "removed and accented letters replaced by their unaccented "
            "equivalent. Third-party human identities require a '.ext' "
            "suffix.",
        )
        self.__domain = kwargs.get("email_domain", "apizee.com")
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.DANGER
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def __expected_pattern(
        self, first_name: str, last_name: str, is_external: bool | None
    ) -> re.Pattern[str]:
        local_part = re.escape(
            f"{_normalize_name_part(first_name)}.{_normalize_name_part(last_name)}"
        )
        domain = re.escape(self.__domain)

        if is_external:
            return re.compile(rf"^{local_part}\.ext@{domain}$")
        return re.compile(rf"^{local_part}@{domain}$")

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects human identities to detect a badly formatted email address.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each human identity whose email does not
                match the expected format.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.HUMAN:
                continue

            if not identity.first_name or not identity.last_name:
                continue

            pattern = self.__expected_pattern(
                identity.first_name, identity.last_name, identity.is_external
            )
            if not identity.email or not pattern.match(identity.email):
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=(
                        f"Email '{identity.email}' of user '{identity.name}' "
                        "does not match the expected format."
                    ),
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={
                        "external_id": identity.external_id,
                        "email": identity.email,
                    },
                )


@RuleRegistry.register("CTRL_HUMAN_CREATION")
class HumanCreationDateRule(IComplianceRule):
    """Verifies that human identities have a recorded creation date.

    Attributes:
        rule_id: Unique rule identifier (CTRL_HUMAN_CREATION).
    """

    rule_id: str = "CTRL_HUMAN_CREATION"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Creation date missing")
        self.__description = kwargs.get(
            "description",
            "The date the identity was created must be recorded, including "
            "at least the current date.",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.DANGER
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects human identities to detect a missing creation date.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each human identity without a creation date.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.HUMAN:
                continue

            if identity.created_at is None:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=f"User '{identity.name}' has no recorded creation date.",
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={"external_id": identity.external_id},
                )


@RuleRegistry.register("CTRL_HUMAN_JOB")
class HumanJobRule(IComplianceRule):
    """Verifies that human identities have a job title set.

    Note: Identity has no dedicated 'job' field. The Dolibarr mapper stores
    the job title in Identity.description (see dolibarr/mapper.py), so this
    field is used here for human identities.

    Note: GitLab's mapper never sets Identity.description for identities,
    and GitLab's own 'job_title' profile field is confirmed unused/empty on
    this instance. This rule will therefore systematically flag every GitLab
    human identity — expected noise on that source, not an action item.

    Attributes:
        rule_id: Unique rule identifier (CTRL_HUMAN_JOB).
    """

    rule_id: str = "CTRL_HUMAN_JOB"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Job title missing")
        self.__description = kwargs.get(
            "description",
            "The job title held within the organization must be set, "
            "defining the person's role and missions.",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.WARNING
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects human identities to detect a missing job title.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each human identity without a job title.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.HUMAN:
                continue

            if not identity.description:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=f"User '{identity.name}' has no job title set.",
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={"external_id": identity.external_id},
                )


@RuleRegistry.register("CTRL_SERVICE_FULL_NAME")
class ServiceFullNameFormatRule(IComplianceRule):
    """Verifies that non-human identities have a properly suffixed full name.

    No formatting constraint is required on the name itself (it must simply
    be human-readable and meaningful), only the ' (EXT)' suffix for
    third-party non-human identities is checked.

    Note: the only source populating Identity.is_external for non-human
    identities is GitLab's own "external user" flag, an access-restriction
    setting rather than a genuine "this service belongs to a third party"
    indicator. Kept anyway as the best available signal, same tolerance as
    applied to CTRL_HUMAN_EMAIL/USERNAME.

    Attributes:
        rule_id: Unique rule identifier (CTRL_SERVICE_FULL_NAME).
    """

    rule_id: str = "CTRL_SERVICE_FULL_NAME"
    __EXT_SUFFIX = " (EXT)"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Full name badly suffixed")
        self.__description = kwargs.get(
            "description",
            "No formatting constraint is required, but the full name must be "
            "suffixed with ' (EXT)' for third-party non-human identities.",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.WARNING
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects non-human identities to detect a badly suffixed full name.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each non-human identity whose full name
                does not respect the ' (EXT)' suffix convention.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.NON_HUMAN:
                continue

            is_suffixed = identity.name.endswith(self.__EXT_SUFFIX)
            if bool(identity.is_external) != is_suffixed:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=(
                        f"Full name '{identity.name}' does not respect the "
                        "' (EXT)' suffix convention."
                    ),
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={
                        "external_id": identity.external_id,
                        "name": identity.name,
                        "is_external": identity.is_external,
                    },
                )


@RuleRegistry.register("CTRL_SERVICE_USERNAME")
class ServiceUsernameFormatRule(IComplianceRule):
    """Verifies that non-human identities have a properly formatted username.

    The username must be lowercase, without special characters (accents,
    etc.), using hyphens to separate words.

    Note: the PDF also requires an 'ext-' prefix for third-party non-human
    identities. This is NOT checked: the only source populating
    Identity.is_external for non-human identities is GitLab's own "external
    user" flag, which reflects an access-restriction setting, not whether
    the bot/service belongs to a third-party company.

    Attributes:
        rule_id: Unique rule identifier (CTRL_SERVICE_USERNAME).
    """

    rule_id: str = "CTRL_SERVICE_USERNAME"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Username badly formatted")
        self.__description = kwargs.get(
            "description",
            "Username must be unique and descriptive, entered in lowercase "
            "without special characters (accents, etc.), using hyphens to "
            "separate words.",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.DANGER
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    __PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects non-human identities to detect a badly formatted username.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each non-human identity whose username
                does not match the expected format.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.NON_HUMAN:
                continue

            if not identity.username or not self.__PATTERN.match(identity.username):
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=(
                        f"Username '{identity.username}' of '{identity.name}' "
                        "does not match the expected format."
                    ),
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={
                        "external_id": identity.external_id,
                        "username": identity.username,
                    },
                )


@RuleRegistry.register("CTRL_SERVICE_CREATION")
class ServiceCreationDateRule(IComplianceRule):
    """Verifies that non-human identities have a recorded creation date.

    Attributes:
        rule_id: Unique rule identifier (CTRL_SERVICE_CREATION).
    """

    rule_id: str = "CTRL_SERVICE_CREATION"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Creation date missing")
        self.__description = kwargs.get(
            "description",
            "The date the identity was created must always be recorded, quantified exactly.",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.DANGER
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects non-human identities to detect a missing creation date.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each non-human identity without a
                creation date.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.NON_HUMAN:
                continue

            if identity.created_at is None:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=f"'{identity.name}' has no recorded creation date.",
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={"external_id": identity.external_id},
                )


@RuleRegistry.register("CTRL_SERVICE_DESCRIPTION")
class ServiceDescriptionRule(IComplianceRule):
    """Verifies that non-human identities have a description set.

    Attributes:
        rule_id: Unique rule identifier (CTRL_SERVICE_DESCRIPTION).
    """

    rule_id: str = "CTRL_SERVICE_DESCRIPTION"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Description missing")
        self.__description = kwargs.get(
            "description",
            "A concise description must be set, clear enough for a "
            "non-technical user to understand the identity's purpose.",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.WARNING
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects non-human identities to detect a missing description.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each non-human identity without a
                description.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.NON_HUMAN:
                continue

            if not identity.description:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=f"'{identity.name}' has no description set.",
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={"external_id": identity.external_id},
                )


@RuleRegistry.register("CTRL_GENERIC_FULL_NAME")
class GenericFullNameRule(IComplianceRule):
    """Verifies that generic identities are never marked as third-party.

    Generic identities must never be used by third-party actors.

    Attributes:
        rule_id: Unique rule identifier (CTRL_GENERIC_FULL_NAME).
    """

    rule_id: str = "CTRL_GENERIC_FULL_NAME"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Generic identity used by a third party")
        self.__description = kwargs.get(
            "description", "Generic identities must never be used by third-party actors."
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.DANGER
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects generic identities to detect a third-party usage.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each generic identity marked as external.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.GENERIC:
                continue

            if identity.is_external:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=f"Generic identity '{identity.name}' is marked as third-party.",
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={"external_id": identity.external_id},
                )


@RuleRegistry.register("CTRL_GENERIC_USERNAME")
class GenericUsernameFormatRule(IComplianceRule):
    """Verifies that generic identities have a properly formatted username.

    The username must be lowercase, without special characters (accents,
    etc.), using hyphens to separate words.

    Attributes:
        rule_id: Unique rule identifier (CTRL_GENERIC_USERNAME).
    """

    rule_id: str = "CTRL_GENERIC_USERNAME"
    __PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*(@[a-z0-9.-]+)?$")

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Username badly formatted")
        self.__description = kwargs.get(
            "description",
            "Username must be unique, entered in lowercase without special "
            "characters (accents, etc.), using hyphens to separate words.",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.DANGER
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects generic identities to detect a badly formatted username.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each generic identity whose username does
                not match the expected format.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.GENERIC:
                continue

            if not identity.username or not self.__PATTERN.match(identity.username):
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=(
                        f"Username '{identity.username}' of '{identity.name}' "
                        "does not match the expected format."
                    ),
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={
                        "external_id": identity.external_id,
                        "username": identity.username,
                    },
                )


@RuleRegistry.register("CTRL_GENERIC_CREATOR")
class GenericCreatorRule(IComplianceRule):
    """Verifies that generic identities have a recorded creator.

    Attributes:
        rule_id: Unique rule identifier (CTRL_GENERIC_CREATOR).
    """

    rule_id: str = "CTRL_GENERIC_CREATOR"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Creator missing")
        self.__description = kwargs.get(
            "description",
            "The operational administrator who created the identity should "
            "be recorded, identified via a unique attribute.",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.WARNING
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects generic identities to detect a missing creator.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each generic identity without a recorded
                creator.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.GENERIC:
                continue

            if not identity.created_by:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=f"'{identity.name}' has no recorded creator.",
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={"external_id": identity.external_id},
                )


@RuleRegistry.register("CTRL_GENERIC_CREATION")
class GenericCreationDateRule(IComplianceRule):
    """Verifies that generic identities have a recorded creation date.

    Attributes:
        rule_id: Unique rule identifier (CTRL_GENERIC_CREATION).
    """

    rule_id: str = "CTRL_GENERIC_CREATION"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Creation date missing")
        self.__description = kwargs.get(
            "description",
            "The date the identity was created must be recorded, including "
            "at least the current date.",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.DANGER
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects generic identities to detect a missing creation date.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each generic identity without a creation
                date.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.GENERIC:
                continue

            if identity.created_at is None:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=f"'{identity.name}' has no recorded creation date.",
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={"external_id": identity.external_id},
                )


@RuleRegistry.register("CTRL_GENERIC_DESCRIPTION")
class GenericDescriptionRule(IComplianceRule):
    """Verifies that generic identities have a description set.

    Attributes:
        rule_id: Unique rule identifier (CTRL_GENERIC_DESCRIPTION).
    """

    rule_id: str = "CTRL_GENERIC_DESCRIPTION"

    def __init__(self, **kwargs: Any) -> None:
        self.__name = kwargs.get("name", "Description missing")
        self.__description = kwargs.get(
            "description",
            "A clear description must be set, specifying the business "
            "rationale, the constraints that led to its creation, and the "
            "scope of its use.",
        )
        self.__severity = _resolve_severity(
            self.rule_id, kwargs.get("severity"), SeverityType.DANGER
        )

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
        return str(self.__name)

    @property
    def description(self) -> str:
        return str(self.__description)

    def evaluate(  # type: ignore
        self, entries: Iterable[Identity], config: dict[Any, Any] | None = None
    ) -> Iterable[Finding]:
        """Inspects generic identities to detect a missing description.

        Args:
            entries: List of identities to analyze.
            config: Optional configuration (containing instance_id, etc.).

        Yields:
            Finding: A finding for each generic identity without a
                description.
        """
        for identity in entries:
            if identity.identity_type != IdentityType.GENERIC:
                continue

            if not identity.description:
                yield Finding(
                    rule_id=self.rule_id,
                    rule_category=self.rule_category,
                    severity=self.severity,
                    title=self.name,
                    description=f"'{identity.name}' has no description set.",
                    source=identity.source,
                    instance_id=(config or {}).get("instance_id", "unknown"),
                    entities_impacted=[identity.name],
                    metadata={"external_id": identity.external_id},
                )
