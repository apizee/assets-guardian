import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from assets_guardian.core.cache.cache import CacheManager
from assets_guardian.core.config.loader import load_employees_profiles, load_yaml_config
from assets_guardian.core.domain.engines.collector_engine import CollectorEngine
from assets_guardian.core.domain.engines.compliance_engine import ComplianceEngine
from assets_guardian.core.domain.models.context import AssetsGuardianMode, Context
from assets_guardian.core.domain.models.finding import Finding
from assets_guardian.core.domain.models.report import Report
from assets_guardian.core.domain.models.rules.rule import IRule
from assets_guardian.core.domain.registry.rule_registry import RuleRegistry
from assets_guardian.core.microsoft365.download_microsoft365 import resolve_location_path
from assets_guardian.core.reporting.excel.reader import read_workbook
from assets_guardian.utils.dates import add_date_to_filename

if TYPE_CHECKING:
    from assets_guardian.core.domain.models.location import Location
logger = logging.getLogger(__name__)


class AuditEngine:
    """
    IAM audit orchestrator.

    Coordinates data collection for each source and applies the
    configured compliance, comparison, and matrix rules.

    Attributes:
        cache: Cache service for storing temporary collection and analysis results.
        collector_engine: Engine responsible for running collectors.
    """

    cache: CacheManager
    collector_engine: CollectorEngine

    def __init__(self, cache: CacheManager | None = None) -> None:
        """Initializes the AuditEngine.

        Args:
            cache: Cache manager instance. If None, a new instance is created.
        """
        self.cache = cache or CacheManager()
        self.collector_engine = CollectorEngine(cache=self.cache)

    def run(self, collectors: list[Any], ctx: Context) -> dict[tuple[str, str], Report]:
        """
        Launches the complete audit process for all provided collectors.

        Args:
            collectors: List of collector instances to run.
            ctx: The application context.

        Returns:
            dict[tuple[str, str], Report]: Dictionary of generated reports indexed
                by (source_name, instance_id).
        """
        results: dict[tuple[str, str], Report] = {}

        if not collectors:
            logger.warning("No collectors provided to AuditEngine.")
            return results

        logger.info("Starting audit for %d collector(s)...", len(collectors))

        for collector in collectors:
            key = (collector.source_name, collector.instance_id)
            results[key] = self.__launch_audit(collector, ctx)

        logger.info("Audit completed for all sources.")
        total_findings = sum(len(report) for report in results.values())
        logger.info("Total: %d anomalies detected.", total_findings)
        return results

    def __launch_audit(self, collector: Any, ctx: Context) -> Report:
        """Runs the audit for a single collector in a resilient manner.

        Args:
            collector: Collector instance to audit.
            ctx: The application context.

        Returns:
            Report: Report of anomalies (findings) detected for this collector instance.
        """
        source_name = collector.source_name
        instance_id = collector.instance_id
        key_log = f"[{source_name}:{instance_id}]"

        logger.info("%s Starting audit...", key_log)
        report = Report()

        try:
            # Determine the cache path
            findings_path = self.cache.get_file_path(
                AssetsGuardianMode.AUDIT, source_name, instance_id, "findings"
            )

            # Retrieve and instantiate active rules for this source
            rules = self.__get_active_rules(source_name, instance_id, ctx)
            if not rules:
                logger.warning("%s No rules configured. Skipping audit.", key_log)
                return report

            # COLLECT (via CollectorEngine)
            collect_result = self.collector_engine.run_collect(
                collector, mode=AssetsGuardianMode.AUDIT
            )

            if not collect_result.success:
                logger.error("%s Audit failed for this instance during collection.", key_log)
                return report

            identities: Any = collect_result.identities
            assets: Any = collect_result.assets
            accesses: Any = collect_result.accesses

            # Set up the compliance engine
            compliance_engine = ComplianceEngine(rules=rules)

            current_data: dict[str, Any] = {
                "users": identities,
                "assets": assets,
                "accesses": accesses,
            }

            # Load matrix and profiles
            matrix, profiles = self.__load_matrix_and_profiles(ctx, source_name, instance_id)

            # Load the baseline (old state)
            old_data: dict[str, list[Any]] = self.__load_old_data(ctx, rules)

            # Execute evaluation stream (generator)
            evaluation_stream = compliance_engine.run_all(
                old_data=old_data,
                new_data=current_data,
                live_data=current_data,
                config=ctx.app_config.integrations.get(source_name, {}).get(instance_id, {}),
                accesses=accesses,
                matrix=matrix,
                profiles=profiles,
            )

            # Atomic persistence of findings for this instance
            self.cache.save(evaluation_stream, findings_path)

            # Return a streaming report that reads from cache as needed
            return Report(findings=self.cache.load_iterable(findings_path, Finding))

        except Exception:
            logger.exception("%s Audit failed for this instance.", key_log)
            return report

        else:
            logger.info("%s Audit succeeded: %d anomalies detected.", key_log, report.total_count)
            return report

    def __load_old_data(self, ctx: Context, rules: list[IRule]) -> dict[str, list[Any]]:
        """Loads the baseline state from the existing Excel file for the active comparison rules.

        This method is fully generic and modular: it has no specific knowledge of GitLab or
        any other plugin. It relies on the active comparison rules to parse their own baseline
        data from the Excel workbook.

        Args:
            ctx: The application context containing file paths.
            rules: List of active rules to evaluate.

        Returns:
            dict[str, list[Any]]: Baseline data indexed by target entity type (e.g., 'users').
        """
        comparison_rules = self.__filter_comparison_rules(rules)
        if not comparison_rules:
            return {}

        excel_location = ctx.app_config.paths.excel
        excel_filename = Path(add_date_to_filename(excel_location.clean_path)).name
        excel_path_str = resolve_location_path(ctx, excel_location, excel_filename)
        excel_path = Path(excel_path_str) if excel_path_str else None
        if excel_path is None or not excel_path.exists():
            logger.warning("No reference Excel repository found for the baseline state.")
            return {}

        old_data: dict[str, list[Any]] = {}
        for rule in comparison_rules:
            try:
                entries = rule.load_baseline(excel_path)
                if entries:
                    target = getattr(rule, "target_entity", "unknown")
                    if target not in old_data:
                        old_data[target] = []
                    old_data[target].extend(entries)
            except Exception:
                logger.exception(
                    "Error loading baseline for rule %s",
                    getattr(rule, "rule_id", "unknown"),
                )

        return old_data

    def __filter_comparison_rules(self, rules: list[IRule]) -> list[Any]:
        """Filters and returns only active comparison rules.

        Args:
            rules: Complete list of rules to filter.

        Returns:
            list[Any]: Filtered list containing only active comparison rules.
        """
        from assets_guardian.core.domain.models.finding import RuleCategory
        from assets_guardian.core.domain.models.rules.comparison import IComparisonRule

        return [
            rule
            for rule in rules
            if isinstance(rule, IComparisonRule)
            or getattr(rule, "rule_category", None) == RuleCategory.COMPARISON
        ]

    def __get_active_rules(self, source_name: str, instance_id: str, ctx: Context) -> list[IRule]:
        """Retrieves and instantiates the active rules for a given source.

        Args:
            source_name: Name of the source (e.g., 'gitlab').
            instance_id: Identifier of the audited instance.
            ctx: Context containing path to rules configuration.

        Returns:
            list[IRule]: List of instantiated active rules ready for evaluation.
        """

        rules_config: Location = ctx.app_config.paths.rules

        rules_path = resolve_location_path(ctx, rules_config, "rules_config.yml")
        if rules_path is None:
            logger.error("Unsupported rules configuration location.")
            return []

        try:
            raw_rules = load_yaml_config(rules_path)
            source_rules_config = raw_rules.get(source_name, {})
        except Exception:
            logger.exception("Unable to load rules configuration file: %s", rules_path)
            return []

        if not source_rules_config:
            return []

        employees_path = resolve_location_path(
            ctx, ctx.app_config.paths.employees, "employees.json"
        )

        active_rules = []
        for rule_id, rule_params in source_rules_config.items():
            if rule_id == "<<":
                continue

            try:
                rule_cls = RuleRegistry.get_rule(rule_id, source=source_name)
                params = dict(rule_params or {})
                params["instance_id"] = instance_id
                params.setdefault("employees_file_path", employees_path)
                instance = rule_cls(**params)
                instance.rule_id = rule_id
                active_rules.append(instance)
            except Exception:
                logger.exception("Error instantiating rule %s:%s", source_name, rule_id)

        return active_rules

    def __load_matrix_and_profiles(
        self, ctx: Context, source_name: str, instance_id: str | None = None
    ) -> tuple[dict[tuple[str, str], str], dict[str, list[str]]]:
        """Loads the permissions matrix and employee profiles from the baseline Excel file.

        Args:
            ctx: Application context containing Excel paths.
            source_name: Name of the source to filter the matrix for.
            instance_id: Optional identifier of the audited instance.

        Returns:
            tuple[dict[tuple[str, str], str], dict[str, list[str]]]: The matrix mapping and
                employee profiles mapping.
        """
        excel_location = ctx.app_config.paths.excel
        excel_filename = Path(add_date_to_filename(excel_location.clean_path)).name
        excel_path_str = resolve_location_path(ctx, excel_location, excel_filename)
        excel_path = Path(excel_path_str) if excel_path_str else None

        if excel_path is None or not excel_path.exists():
            logger.warning("No reference Excel repository found.")
            return {}, {}

        try:
            workbook_data = read_workbook(excel_path)
        except Exception:
            logger.exception("Error loading matrix/profiles from %s", excel_path)
            return {}, {}
        else:
            matrix = self.__extract_matrix(workbook_data, source_name, instance_id)
            employees_path = resolve_location_path(
                ctx, ctx.app_config.paths.employees, "employees.json"
            )
            employees_profiles = load_employees_profiles(employees_path)
            return matrix, employees_profiles

    def __resolve_matrix_sheet_name(
        self, workbook_data: dict[str, Any], source_name: str, instance_id: str | None
    ) -> str | None:
        """Finds the matrix sheet name in workbook_data."""
        if instance_id:
            target = f"{source_name} ({instance_id}) matrix".lower()
            for name in workbook_data:
                if name.lower() == target:
                    return name
        target = f"{source_name} matrix".lower()
        for name in workbook_data:
            if name.lower() == target:
                return name
        return None

    def __extract_matrix(
        self, workbook_data: dict[str, Any], source_name: str, instance_id: str | None = None
    ) -> dict[tuple[str, str], str]:
        """Extracts the permissions matrix (Profile, Scope) -> Role mapping from the workbook.

        Args:
            workbook_data: Complete workbook sheets data.
            source_name: Name of the source to identify the correct matrix sheet.
            instance_id: Optional identifier of the audited instance.

        Returns:
            dict[tuple[str, str], str]: Matrix mapping (profile, scope) to a target role.
        """
        sheet_name = self.__resolve_matrix_sheet_name(workbook_data, source_name, instance_id)
        if not sheet_name:
            return {}

        sheet = workbook_data[sheet_name]
        header, content = sheet["header"], sheet["content"]
        scopes = {i: header[i]["title"].strip() for i in header if i > 1}

        matrix = {}
        for row in content:
            matrix.update(self.__process_matrix_row(row, scopes))

        logger.debug("%s Matrix loaded (%d entry/entries).", source_name, len(matrix))
        return matrix

    def __process_matrix_row(
        self, row: list[Any], scopes: dict[int, str]
    ) -> dict[tuple[str, str], str]:
        """Processes a single row of the permissions matrix.

        Args:
            row: Raw row data from the Excel sheet.
            scopes: Scopes mapped by column index.

        Returns:
            dict[tuple[str, str], str]: Mapping of (profile, scope) to a role for this row.
        """
        if not row or not row[0]:
            return {}

        profile = row[0].strip() if isinstance(row[0], str) else row[0]
        row_matrix = {}
        for col_idx, scope_name in scopes.items():
            role = row[col_idx - 1] if col_idx - 1 < len(row) else None
            if role:
                row_matrix[(profile, scope_name)] = role
        return row_matrix
