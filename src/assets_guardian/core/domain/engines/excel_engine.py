import logging
from typing import Any

from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.domain.registry.sheet_builder_registry import SheetBuilderRegistry
from assets_guardian.core.microsoft365.download_microsoft365 import resolve_location_path
from assets_guardian.core.reporting.excel.default_builder import DefaultSheetBuilder
from assets_guardian.core.reporting.excel.writer import ExcelWriter
from assets_guardian.utils.dates import add_date_to_filename

logger = logging.getLogger(__name__)


class ExcelEngine:
    """Engine responsible for generating the reference Excel repository."""

    def generate(self, data: Any, ctx: Context, output_path: str | None = None) -> None:
        """Generates the Excel file from data collection results.

        Args:
            data: Data collection results.
            ctx: The application context.
            output_path: Destination path for the Excel file. If not provided, it is
                computed from the configured path, replacing the 'DATE' placeholder
                with today's date if present.
        """
        builders = SheetBuilderRegistry.get_builders()

        # Dynamically load generic builders for plugins without a custom Python builder
        from assets_guardian import DIR_PLUGINS
        from assets_guardian.core.reporting.excel.sheets_builder import GenericSheetBuilder

        for integration, instances in ctx.app_config.integrations.items():
            for instance_id in instances:
                # Check if a custom builder already exists for this integration/instance
                integration_lower = integration.lower()
                has_custom_builder = any(
                    getattr(builder, "source_name", "").lower() == integration_lower
                    and getattr(builder, "instance_id", "").lower() == instance_id.lower()
                    for builder in builders
                )
                if not has_custom_builder:
                    plugin_rules_path = DIR_PLUGINS / integration / "excel_config.json"
                    if plugin_rules_path.is_file():
                        generic_builder = GenericSheetBuilder(
                            source_name=integration,
                            instance_id=instance_id,
                            rules_file_path=plugin_rules_path,
                        )
                        builders.append(generic_builder)

        if not builders:
            logger.warning(
                "No ISheetBuilder found or configuration file missing. Excel generation canceled."
            )
            return

        if output_path is None:
            output_path = add_date_to_filename(ctx.app_config.paths.excel.clean_path)
        rules_path = ctx.app_config.paths.excel_config.clean_path
        employees_path = resolve_location_path(
            ctx, ctx.app_config.paths.employees, "employees.json"
        )
        author = ctx.app_config.author.fullname

        # Prepend the default sheet builder
        default_builder = DefaultSheetBuilder(
            employees_file_path=employees_path,
            rules_file_path=rules_path,
            author=author,
        )
        builders.insert(0, default_builder)

        writer = ExcelWriter(sheet_builders=builders)

        logger.info("Launching reference Excel repository generation...")
        writer.write(
            data=data,
            output_path=output_path,
            existing_file_path=output_path,  # Preserve and append to the existing file
            rules_file_path=rules_path,
            employees_file_path=employees_path,
        )
        logger.info("Reference Excel repository generation completed successfully.")
