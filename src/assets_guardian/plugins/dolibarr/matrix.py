import logging
from collections.abc import Iterable
from typing import Any

from assets_guardian.core.domain.models.access import Access
from assets_guardian.core.domain.models.finding import Finding, RuleCategory, SeverityType
from assets_guardian.core.domain.models.rules.matrix import IMatrixRule
from assets_guardian.core.domain.registry.rule_registry import RuleRegistry
from assets_guardian.plugins.dolibarr.constants import CRITICAL_MODULES

logger = logging.getLogger(__name__)


@RuleRegistry.register("MATRIX-001")
class DolibarrSuperadminRule(IMatrixRule):
    """Verifies that Dolibarr superadmins are authorized by the authorization matrix.

    A user is superadmin if their `admin` field is 1 in Dolibarr.
    The matrix is queried with the key (profile, "Dolibarr") to determine
    if the profile authorizes superadmin access.
    """

    rule_id = "MATRIX-001"
    _ADMIN_ROLES = frozenset({"Administrateur", "Administrateur*", "Administrator"})

    def __init__(self, **kwargs: Any) -> None:
        self.__name: str = kwargs.get("name", "Unauthorized Dolibarr superadmin")
        self.__description: str = kwargs.get(
            "description",
            "Detects users with Dolibarr superadmin privileges without authorization "
            "in the authorization matrix.",
        )
        severity_value = kwargs.get("severity")
        if not severity_value:
            logger.warning(
                "Rule %s: no 'severity' configured in rules_config.yml, defaulting to %s.",
                self.rule_id,
                SeverityType.CRITICAL,
            )
            severity_value = SeverityType.CRITICAL
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

    def evaluate(  # type: ignore
        self,
        accesses: Iterable[Access],
        matrix: dict[tuple[str, str], str],
        profiles: dict[str, list[str]],
    ) -> Iterable[Finding]:
        """Verifies each access of type `group` where the user is superadmin.

        For each group access carrying the `is_admin` flag, we verify
        that the user's profile authorizes the superadmin role in the matrix.

        ARCH-LIMIT: The `is_admin` flag (Dolibarr admin) is duplicated in
        `Access.metadata` because `IMatrixRule` only receives accesses, not
        identities. See `DolibarrCollector.__build_accesses_for_user()`.

        Args:
            accesses: All collected accesses for Dolibarr.
            matrix: Authorization matrix `(profile, role)` -> authorized permission.
            profiles: Mapping `email` -> list of profiles.

        Yields:
            Finding: One Finding per unauthorized superadmin according to the matrix.
        """
        seen_users: set[str] = set()
        for access in accesses:
            if access.access_type != "group":
                continue
            meta = access.metadata or {}
            if not meta.get("is_admin"):
                continue
            email = meta.get("user_email")
            dedup = email or meta.get("user_external_id", "")
            if dedup in seen_users:
                continue
            seen_users.add(dedup)

            user_profiles = profiles.get(email, []) if email else []
            if not self._is_authorized(user_profiles, matrix):
                yield self.__superadmin_finding(access, meta, email, user_profiles)

    def __superadmin_finding(
        self,
        access: Access,
        meta: dict[str, Any],
        email: str | None,
        user_profiles: list[str],
    ) -> Finding:
        """Builds a Finding for an unauthorized Dolibarr superadmin.

        Args:
            access: The group access carrying the user's metadata.
            meta: Metadata extracted from the access.
            email: User's email.
            user_profiles: List of user profiles.

        Returns:
            Finding: The generated Finding.
        """
        user_name = meta.get("user_name", email or "Unknown")
        profile_str = ", ".join(user_profiles) if user_profiles else "no known profile"
        return Finding(
            rule_id=self.rule_id,
            rule_category=self.rule_category,
            severity=self.severity,
            title=self.name,
            description=(
                f"User {user_name} ({email or 'unknown email'}) is a Dolibarr superadmin "
                f"but their profiles ({profile_str}) do not authorize it "
                f"according to the authorization matrix."
            ),
            source=access.source,
            instance_id=str(meta.get("group_id") or "unknown"),
            entities_impacted=[email or user_name],
            metadata={
                "user_email": email,
                "user_profiles": user_profiles,
                "access_name": access.name,
            },
        )

    def _is_authorized(self, user_profiles: list[str], matrix: dict[tuple[str, str], str]) -> bool:
        """Returns True if at least one profile authorizes the superadmin role in the matrix.

        Args:
            user_profiles: List of user profiles.
            matrix: Authorization matrix `(profile, role)` -> authorized permission.

        Returns:
            bool: True if superadmin access is authorized for at least one profile.
        """
        return any(
            matrix.get((profile, "Dolibarr")) in self._ADMIN_ROLES for profile in user_profiles
        )


@RuleRegistry.register("MATRIX-002")
class DolibarrCriticalModuleAccessRule(IMatrixRule):
    """Verifies that rights on Dolibarr critical modules are authorized.

    This rule inspects accesses of type `module_permission` on modules
    declared in `CRITICAL_MODULES` and verifies that the user's profile
    authorizes this right in the matrix.

    The matrix key used is `(profile, module)` -> permission_level.
    Example: `("Direction", "banque")` -> `"modifier"`

    Dolibarr permissions are modeled as virtual Assets
    representing critical modules, which respects the asset-centric
    structure of Assets Guardian.
    """

    rule_id = "MATRIX-002"

    def __init__(self, **kwargs: Any) -> None:
        self.__name: str = kwargs.get("name", "Unauthorized critical module access")
        self.__description: str = kwargs.get(
            "description",
            "Detects users with unauthorized rights on critical Dolibarr modules "
            "(bank, users, billing, third parties) according to the matrix.",
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

    def evaluate(  # type: ignore
        self,
        accesses: Iterable[Access],
        matrix: dict[tuple[str, str], str],
        profiles: dict[str, list[str]],
    ) -> Iterable[Finding]:
        """Verifies that each right on a critical module is authorized by the matrix.

        The matrix must contain entries of the form:
        `(profile, module)` -> `permission_key`
        (e.g., `("Direction", "banque")` -> `"modifier"`).

        A right is considered authorized if at least one of the user's profiles
        has a matrix entry covering this module.

        Args:
            accesses: All collected accesses for Dolibarr.
            matrix: Authorization matrix `(profile, module)` -> authorized permission.
            profiles: Mapping `email` -> list of profiles.

        Yields:
            Finding: One Finding per unauthorized right on a critical module.
        """
        seen: set[tuple[str, str]] = set()
        for access in accesses:
            if access.access_type != "module_permission":
                continue
            meta = access.metadata or {}
            module: str = meta.get("module", "")
            if not module or module.split(".")[0] not in CRITICAL_MODULES:
                continue
            email = meta.get("user_email")
            dedup_key = (email or meta.get("user_external_id", ""), module)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            user_profiles = profiles.get(email, []) if email else []
            base_module = module.split(".")[0]
            if not self._is_authorized(user_profiles, base_module, matrix):
                yield self.__critical_finding(access, meta, email, user_profiles, base_module)

    def __critical_finding(
        self,
        access: Access,
        meta: dict[str, Any],
        email: str | None,
        user_profiles: list[str],
        base_module: str,
    ) -> Finding:
        """Builds a Finding for an unauthorized right on a critical module.

        Args:
            access: The offending `module_permission` access.
            meta: Metadata extracted from the access.
            email: User's email.
            user_profiles: List of user profiles.
            base_module: Base module name (without sub-module).

        Returns:
            Finding: The generated Finding.
        """
        user_name = meta.get("user_name", email or "Unknown")
        profile_str = ", ".join(user_profiles) if user_profiles else "no known profile"
        asset_name = access.asset.name if access.asset else f"module '{base_module}'"
        return Finding(
            rule_id=self.rule_id,
            rule_category=self.rule_category,
            severity=self.severity,
            title=self.name,
            description=(
                f"User {user_name} ({email or 'unknown email'}) has rights "
                f"on {asset_name} but their profiles ({profile_str}) "
                f"do not authorize it according to the authorization matrix."
            ),
            source=access.source,
            instance_id="dolibarr",
            entities_impacted=[email or user_name],
            metadata={
                "user_email": email,
                "user_profiles": user_profiles,
                "module": meta.get("module"),
                "permission_key": meta.get("permission_key"),
            },
        )

    @staticmethod
    def _is_authorized(
        user_profiles: list[str],
        module: str,
        matrix: dict[tuple[str, str], str],
    ) -> bool:
        """Returns True if at least one profile authorizes access to the module in the matrix.

        Args:
            user_profiles: List of user profiles.
            module: Dolibarr module name to verify.
            matrix: Authorization matrix `(profile, module)` -> authorized permission.

        Returns:
            bool: True if access to the module is authorized for at least one profile.
        """
        return any(matrix.get((profile, module)) is not None for profile in user_profiles)
