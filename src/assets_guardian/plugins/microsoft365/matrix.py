import logging
from collections.abc import Iterable
from typing import Any

from assets_guardian.core.domain.models.access import Access
from assets_guardian.core.domain.models.finding import Finding, RuleCategory, SeverityType
from assets_guardian.core.domain.models.rules.matrix import IMatrixRule
from assets_guardian.core.domain.registry.rule_registry import RuleRegistry

logger = logging.getLogger(__name__)


@RuleRegistry.register("MATRIX-001")
class Microsoft365GroupProjectAccessRule(IMatrixRule):
    """Verifies that Microsoft365 group memberships are authorized by the matrix."""

    rule_id = "MATRIX-001"

    def __init__(self, **kwargs: Any) -> None:
        """Retrieves the rule configuration from YAML."""
        self.__name: str = kwargs.get("name", "Unauthorized Microsoft365 group access")
        self.__description: str = kwargs.get(
            "description",
            "Detects users with unauthorized Microsoft365 group membership.",
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
        return RuleCategory.MATRIX

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

    def _is_relevant_access(self, access: Access, configured_scopes: set[str]) -> bool:
        """Helper to determine if the access should be evaluated."""
        if access.asset is None:
            return False
        asset_type = access.asset.asset_type.lower()
        if asset_type != "group":
            return False
        scope_name = f"{asset_type.capitalize()}: {access.asset.name}"
        return scope_name in configured_scopes

    def evaluate(  # type: ignore
        self,
        accesses: Iterable[Access],
        matrix: dict[tuple[str, str], str],
        profiles: dict[tuple[str | None, str | None], list[str]],
    ) -> Iterable[Finding]:
        """Verifies Microsoft365 group memberships against the authorization matrix.

        Args:
            accesses: List of accesses to evaluate.
            matrix: Authorization matrix (profile, resource) -> role.
            profiles: Dictionary of profiles associated with each user by their (email, username).

        Yields:
            Finding: Anomalies for each detected unauthorized group membership.
        """
        configured_scopes = {scope for (_, scope) in matrix}
        logger.debug("MATRIX-002 configured_scopes=%r", configured_scopes)

        for access in accesses:
            if not self._is_relevant_access(access, configured_scopes):
                continue

            asset_type = access.asset.asset_type.lower()  # type: ignore[union-attr]
            scope_name = f"{asset_type.capitalize()}: {access.asset.name}"  # type: ignore[union-attr]
            meta = access.metadata or {}
            email = meta.get("user_email")
            user_name = meta.get("user_name", email or "Unknown")
            user_profiles = profiles.get(email, []) if email else []
            actual_role = access.name
            logger.debug(
                "MATRIX-001 user=%r scope=%r profiles=%r", email, scope_name, user_profiles
            )
            if not any(matrix.get((profile, scope_name)) for profile in user_profiles):
                yield self._build_finding(
                    access, meta, email, user_name, user_profiles, scope_name, actual_role
                )

    def _build_finding(
        self,
        access: Access,
        meta: dict[str, Any],
        email: str | None,
        user_name: str,
        user_profiles: list[str],
        scope_name: str,
        actual_role: str,
    ) -> Finding:
        """Builds a Finding for an unauthorized group membership.

        Args:
            access: The unauthorized access.
            meta: Access metadata.
            email: User's email.
            user_name: User name or identifier.
            user_profiles: List of user profiles.
            scope_name: Name of the scope checked.
            actual_role: Current role of the user.

        Returns:
            Finding: The formatted anomaly.
        """
        profile_str = ", ".join(user_profiles) if user_profiles else "no known profile"

        desc = (
            f"User {user_name} ({email or 'unknown email'}) has '{actual_role}' role "
            f"on {scope_name} but their profiles ({profile_str})"
            f" only authorize 'no access authorized'"
            f" according to the authorization matrix."
        )

        return Finding(
            rule_id=self.rule_id,
            rule_category=self.rule_category,
            severity=self.severity,
            title=self.name,
            description=desc,
            source=access.source,
            instance_id=meta.get("asset_external_id", "unknown"),
            entities_impacted=[email or user_name],
            metadata={
                "user_email": email,
                "user_profiles": user_profiles,
                "access_name": access.name,
                "scope_name": scope_name,
            },
        )
