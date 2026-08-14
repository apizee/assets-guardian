import logging
from collections.abc import Iterable
from typing import Any, ClassVar

from assets_guardian.core.domain.models.access import Access
from assets_guardian.core.domain.models.finding import Finding, RuleCategory, SeverityType
from assets_guardian.core.domain.models.rules.matrix import IMatrixRule
from assets_guardian.core.domain.registry.rule_registry import RuleRegistry

from .constants import ROLES_MAP

logger = logging.getLogger(__name__)


@RuleRegistry.register("MATRIX-001")
class InstanceAdminRule(IMatrixRule):
    """Verifies that GitLab instance administrators are authorized by the matrix."""

    rule_id = "MATRIX-001"

    def __init__(self, **kwargs: Any) -> None:
        """Retrieves the rule configuration from YAML."""

        self.__name: str = kwargs.get("name", "Unauthorized GitLab instance administrator")
        self.__description: str = kwargs.get(
            "description",
            "Detects users with GitLab instance administrator privileges "
            "without authorization in the matrix.",
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

    _ADMIN_ROLES = frozenset({"Administrator", "Administrator*"})

    def evaluate(  # type: ignore
        self,
        accesses: Iterable[Access],
        matrix: dict[tuple[str, str], str],
        profiles: dict[str, list[str]],
    ) -> Iterable[Finding]:
        """Verifies that each instance administrator is authorized by the matrix.

        Args:
            accesses: List of accesses to evaluate.
            matrix: Authorization matrix (profile, resource) -> role.
            profiles: Dictionary of profiles associated with each user by their email.

        Yields:
            Finding: Anomalies for each detected unauthorized access.
        """
        for access in accesses:
            if not self.__is_instance_access(access):
                continue
            finding = self.__check_access(access, matrix, profiles)
            if finding is not None:
                yield finding

    def __is_instance_access(self, access: Access) -> bool:
        """Determines if the access concerns an instance-wide resource.

        Args:
            access: Access to verify.

        Returns:
            bool: True if the access is instance-wide, False otherwise.
        """
        return access.asset is not None and access.asset.asset_type.lower() == "instance"

    def __check_access(
        self,
        access: Access,
        matrix: dict[tuple[str, str], str],
        profiles: dict[str, list[str]],
    ) -> Finding | None:
        """Verifies a specific access against the matrix and user profiles.

        Args:
            access: The access to verify.
            matrix: Authorization matrix.
            profiles: Profiles of all users.

        Returns:
            Finding | None: An anomaly if the access is not authorized, None otherwise.
        """
        meta = access.metadata or {}
        email = meta.get("user_email")
        user_name = meta.get("user_name", email or "Unknown")
        user_profiles = profiles.get(email, []) if email else []

        if self.__is_authorized(user_profiles, matrix):
            return None

        return self.__build_finding(access, meta, email, user_name, user_profiles)

    def __is_authorized(self, user_profiles: list[str], matrix: dict[tuple[str, str], str]) -> bool:
        """Verifies if the user's profiles authorize them to have an administrator role.

        Args:
            user_profiles: List of user profiles.
            matrix: Authorization matrix.

        Returns:
            bool: True if one of the profiles authorizes it, False otherwise.
        """
        return any(
            matrix.get((profile, "Instance")) in self._ADMIN_ROLES for profile in user_profiles
        )

    def __build_finding(
        self,
        access: Access,
        meta: dict[str, Any],
        email: str | None,
        user_name: str,
        user_profiles: list[str],
    ) -> Finding:
        """Builds a Finding for an unauthorized access anomaly.

        Args:
            access: The unauthorized access.
            meta: Access metadata.
            email: User's email.
            user_name: User name or identifier.
            user_profiles: List of user profiles.

        Returns:
            Finding: The formatted anomaly.
        """
        profile_str = ", ".join(user_profiles) if user_profiles else "no known profile"
        return Finding(
            rule_id=self.rule_id,
            rule_category=self.rule_category,
            severity=self.severity,
            title=self.name,
            description=(
                f"User {user_name} ({email or 'unknown email'}) is an Administrator"
                f" at the instance level but their profiles ({profile_str})"
                f" do not authorize it according to the authorization matrix."
            ),
            source=access.source,
            instance_id=meta.get("asset_external_id", "unknown"),
            entities_impacted=[email or user_name],
            metadata={
                "user_email": email,
                "user_profiles": user_profiles,
                "access_name": access.name,
            },
        )


@RuleRegistry.register("MATRIX-002")
class GitlabGroupProjectAccessRule(IMatrixRule):
    """Verifies that GitLab group and project roles are authorized by the matrix."""

    rule_id = "MATRIX-002"

    _ROLE_LEVELS: ClassVar[dict[str, int]] = {
        role_name: level for level, role_name in ROLES_MAP.items()
    }

    def __init__(self, **kwargs: Any) -> None:
        """Retrieves the rule configuration from YAML."""
        self.__name: str = kwargs.get("name", "Unauthorized GitLab group/project access")
        self.__description: str = kwargs.get(
            "description",
            "Detects users with GitLab group/project roles exceeding authorized levels.",
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
        if asset_type not in ("group", "project"):
            return False
        scope_name = f"{asset_type.capitalize()}: {access.asset.name}"
        return scope_name in configured_scopes

    def _get_max_authorized_level(
        self,
        user_profiles: list[str],
        scope_name: str,
        matrix: dict[tuple[str, str], str],
    ) -> int:
        """Helper to compute the maximum role level authorized by user's profiles."""
        max_authorized_level = -1
        for profile in user_profiles:
            auth_role = matrix.get((profile, scope_name))
            if auth_role:
                level = self._ROLE_LEVELS.get(auth_role, 0)
                if level > max_authorized_level:
                    max_authorized_level = level
        return max_authorized_level

    def evaluate(  # type: ignore
        self,
        accesses: Iterable[Access],
        matrix: dict[tuple[str, str], str],
        profiles: dict[str, list[str]],
    ) -> Iterable[Finding]:
        """Verifies GitLab group and project accesses against the authorization matrix.

        Args:
            accesses: List of accesses to evaluate.
            matrix: Authorization matrix (profile, resource) -> role.
            profiles: Dictionary of profiles associated with each user by their email.

        Yields:
            Finding: Anomalies for each detected unauthorized or excessive access.
        """
        configured_scopes = {scope for (_, scope) in matrix}

        for access in accesses:
            if not self._is_relevant_access(access, configured_scopes):
                continue

            asset_type = access.asset.asset_type.lower()  # type: ignore[union-attr]
            scope_name = f"{asset_type.capitalize()}: {access.asset.name}"  # type: ignore[union-attr]

            meta = access.metadata or {}
            email = meta.get("user_email")
            user_name = meta.get("user_name", email or "Unknown")
            user_profiles = profiles.get(email, []) if email else []

            max_auth = self._get_max_authorized_level(user_profiles, scope_name, matrix)
            actual_role = access.name
            actual_level = self._ROLE_LEVELS.get(actual_role, 0)

            if max_auth == -1 or actual_level > max_auth:
                yield self._build_finding(
                    access,
                    meta,
                    email,
                    user_name,
                    user_profiles,
                    scope_name,
                    actual_role,
                    max_auth,
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
        max_authorized_level: int,
    ) -> Finding:
        """Builds a Finding for an unauthorized group or project access.

        Args:
            access: The unauthorized access.
            meta: Access metadata.
            email: User's email.
            user_name: User name or identifier.
            user_profiles: List of user profiles.
            scope_name: Name of the scope checked.
            actual_role: Current role of the user.
            max_authorized_level: Maximum authorized level value.

        Returns:
            Finding: The formatted anomaly.
        """
        profile_str = ", ".join(user_profiles) if user_profiles else "no known profile"
        if max_authorized_level == -1:
            auth_str = "no access authorized"
        else:
            # Find matching role name for the maximum authorized level
            auth_roles = [r for r, lvl in self._ROLE_LEVELS.items() if lvl == max_authorized_level]
            auth_str = f"up to {auth_roles[0]}" if auth_roles else "unknown role"

        desc = (
            f"User {user_name} ({email or 'unknown email'}) has '{actual_role}' role "
            f"on {scope_name} but their profiles ({profile_str}) only authorize {auth_str} "
            f"according to the authorization matrix."
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
                "authorized_role_level": max_authorized_level,
            },
        )
