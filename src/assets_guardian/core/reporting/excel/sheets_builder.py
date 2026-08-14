import logging
import typing
from datetime import datetime
from enum import Enum
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path
from typing import Any

from assets_guardian.core.domain.ports.sheet_builders import ISheetBuilder
from assets_guardian.core.reporting.excel.rules_loader import load_rules
from assets_guardian.utils.dates import format_datetime

logger = logging.getLogger(__name__)


class GenericSheetBuilder(ISheetBuilder):
    """Generic Excel sheet builder driven by configuration metadata.

    Attributes:
        source_name: Unique name of the source (e.g., 'gitlab').
    """

    def __init__(self, source_name: str, instance_id: str, rules_file_path: str | Path):
        """Initializes the generic sheet builder.

        Args:
            source_name: Technical name of the source plugin.
            rules_file_path: Absolute or relative path to the JSON rules file.
        """
        self.source_name = source_name.lower()
        self.instance_id = instance_id.lower()
        self._rules_file_path = Path(rules_file_path)
        self._loaded_rules = load_rules(self._rules_file_path)

    def _rename_sheet(self, sheet_name: str) -> str:
        """Renames a sheet to its instance-specific name."""
        prefix = self.source_name.capitalize()
        if sheet_name.startswith(prefix):
            return sheet_name.replace(prefix, f"{prefix} ({self.instance_id})", 1)
        return f"{sheet_name} ({self.instance_id})"

    @property
    def sheet_names(self) -> list[str]:
        """Returns the list of Excel sheet names defined in the rules.

        Returns:
            list[str]: List of sheet names.
        """
        return [self._rename_sheet(name) for name in self._loaded_rules]

    @property
    def preserved_columns(self) -> dict[str, dict[str, list[str]]]:
        """Dynamically defines the columns to preserve from the configuration.

        Returns:
            dict[str, dict[str, list[str]]]: Preservation configuration.
        """
        preserved_config = {}

        for sheet_name, sheet_config in self._loaded_rules.items():
            if isinstance(sheet_config, list):
                columns = sheet_config
            else:
                columns = sheet_config.get("columns", [])

            primary_keys = [
                column["column_name"] for column in columns if column.get("is_primary_key")
            ]
            preserved_cols = [
                column["column_name"] for column in columns if column.get("is_preserved")
            ]

            renamed_name = self._rename_sheet(sheet_name)
            preserved_config[renamed_name] = {
                "primary_keys": primary_keys,
                "columns": preserved_cols,
            }

        return preserved_config

    def get_rules(self) -> dict[str, list[dict[str, Any]]]:
        """Returns the formatting rules in the format expected by the ExcelWriter.

        This method extracts only the list of columns for each sheet.

        Returns:
            dict[str, list[dict[str, Any]]]: Dictionary of rules per sheet.
        """
        formatted_rules = {}

        for sheet_name, sheet_config in self._loaded_rules.items():
            if isinstance(sheet_config, list):
                cols = sheet_config
            else:
                cols = sheet_config.get("columns", [])

            renamed_name = self._rename_sheet(sheet_name)
            formatted_rules[renamed_name] = cols

        return formatted_rules

    def __collect_matching_items(
        self, data: Any, data_source: str, filter_by_asset_type: str | None
    ) -> list[Any]:
        """Collects and filters elements from a specific data source.

        Args:
            data: Dictionary of collection results indexed by (source, instance).
            data_source: Name of the attribute containing the list of data to collect.
            filter_by_asset_type: Optional asset type to filter the collection.

        Returns:
            list[Any]: Consolidated and filtered list of collected items.
        """
        collected: list[type] = []
        for (source, instance), result in data.items():
            if source != self.source_name or instance != self.instance_id:
                continue
            items_list = getattr(result, data_source, [])
            if filter_by_asset_type:
                items_list = self.__filter_by_asset_type(
                    items_list, data_source, filter_by_asset_type
                )
            collected.extend(items_list)
        return collected

    def __filter_by_asset_type(
        self, items_list: list[Any], data_source: str, asset_type: str
    ) -> list[Any]:
        """Filters items whose asset type matches, for both assets and accesses sources.

        Args:
            items_list: The items to filter (Asset or Access instances).
            data_source: Name of the source attribute ("assets" or "accesses").
            asset_type: The asset type to match against.

        Returns:
            list[Any]: Items matching the given asset type.
        """
        if data_source == "assets":
            return [item for item in items_list if item.asset_type == asset_type]
        return [item for item in items_list if item.asset and item.asset.asset_type == asset_type]

    def build(
        self,
        worksheet: Any,
        data: Any,
        preserved: Any,
        rules: Any,
    ) -> None:
        """Builds the Excel sheet by applying filters and mappings from the rules file.

        Args:
            worksheet: The Excel worksheet (ExcelWorksheet).
            data: Collection data (source, instance) -> CollectorResult.
            preserved: Manual data indexed by its primary key.
            rules: Column definition (list of dictionaries).
        """
        sheet_config = None
        for orig_name, config in self._loaded_rules.items():
            if self._rename_sheet(orig_name) == worksheet.title:
                sheet_config = config
                break

        if not sheet_config:
            if not worksheet.title.lower().endswith(" matrix"):
                logger.warning(
                    "Unable to generate sheet '%s': configuration not found.",
                    worksheet.title,
                )
            return

        # Determine data source and optional filter
        if isinstance(sheet_config, list):
            data_source = "identities"
            filter_by_asset_type = None
        else:
            data_source = sheet_config.get("data_source", "identities")
            filter_by_asset_type = sheet_config.get("filter_by_asset_type")
            if sheet_config.get("row_height") == "auto":
                worksheet.auto_row_height = True

        # Setup headers and column widths
        self.__setup_worksheet_header(worksheet, rules)

        # Collect and filter items
        collected_items = self.__collect_matching_items(data, data_source, filter_by_asset_type)

        # Retrieve primary keys and preservation columns
        sheet_preserved_config = self.preserved_columns.get(worksheet.title, {})
        primary_keys = sheet_preserved_config.get("primary_keys", [])
        preserved_columns = set(sheet_preserved_config.get("columns", []))

        # Map columns to their corresponding fields
        column_to_field_mapping = {
            column.get("column_name"): column.get("field", column.get("column_name"))
            for column in rules
        }

        # Write rows in the Excel sheet
        for item in collected_items:
            row_data = self.__build_worksheet_row(
                item=item,
                rules=rules,
                primary_keys=primary_keys,
                preserved_columns=preserved_columns,
                preserved_data=preserved,
                column_to_field=column_to_field_mapping,
            )
            worksheet.append_row(row_data)

    def __setup_worksheet_header(
        self, worksheet: Any, columns_configuration: list[dict[str, Any]]
    ) -> None:
        """Configures the titles and widths of the sheet columns.

        Args:
            worksheet: The Excel worksheet.
            columns_configuration: Columns configuration.
        """
        widths = [col.get("width", 20) for col in columns_configuration]
        headers = [col.get("column_name", "Unknown") for col in columns_configuration]
        worksheet.set_column_widths(widths)
        worksheet.append_row(headers, is_header=True)

    def __build_worksheet_row(
        self,
        item: Any,
        rules: list[dict[str, Any]],
        primary_keys: list[str],
        preserved_columns: set[str],
        preserved_data: dict[tuple[Any, ...], dict[str, Any]],
        column_to_field: dict[str, str],
    ) -> list[Any]:
        """Builds an Excel data row for a domain item.

        Args:
            item: The domain object (e.g., Identity, Access).
            rules: List of sheet columns.
            primary_keys: Primary keys of the row.
            preserved_columns: Manual columns to preserve.
            preserved_data: Dictionary of preserved data.
            column_to_field: Column name -> field name mapping.

        Returns:
            list[Any]: The formatted row values.
        """
        # Generate primary key tuple to identify the row
        primary_key_tuple = tuple(
            self.__get_domain_item_value(item, column_to_field.get(pk_name, pk_name))
            for pk_name in primary_keys
        )

        row_values = []
        for column in rules:
            column_name = column.get("column_name", "Unknown")
            field_name = column.get("field", column_name)
            mapping = column.get("mapping")

            if column_name in preserved_columns:
                cell_value = preserved_data.get(primary_key_tuple, {}).get(column_name, "")
            else:
                cell_value = self.__get_domain_item_value(item, field_name, mapping)

            row_values.append(cell_value)

        return row_values

    def __get_domain_item_value(
        self, item: Any, field_name: str, mapping: dict[str, Any] | None = None
    ) -> Any:
        """Extracts the value of a field or metadata from an item.

        Args:
            item: The domain object to inspect.
            field_name: The name of the field or key in metadata.
            mapping: Optional dictionary to map the raw value.

        Returns:
            Any: The raw or formatted value extracted from the item.
        """
        # Direct attribute lookup
        value = getattr(item, field_name, None)

        # Fallback lookup in the metadata dictionary
        if value is None and hasattr(item, "metadata") and isinstance(item.metadata, dict):
            value = item.metadata.get(field_name)

        # Apply reverse mapping dictionary before string formatting
        if mapping and value is not None:
            raw_compare = value.value if isinstance(value, Enum) else value
            mapped_value = next((k for k, v in mapping.items() if v == raw_compare), None)
            if mapped_value is not None:
                value = mapped_value

        return self.__format_cell_value(value, field_name, item)

    def __check_if_date_field(self, item: Any, field_name: str) -> bool:
        """Determines via type hints if a model field is of type date.

        Args:
            item: Domain object to inspect.
            field_name: Name of the field or attribute to analyze.

        Returns:
            bool: True if the field is of type date or datetime, False otherwise.
        """
        try:
            type_hints = typing.get_type_hints(type(item))
            target_type = type_hints.get(field_name, Any)
            type_args = typing.get_args(target_type)
            if type_args:
                base_types = [t for t in type_args if t is not type(None)]
            else:
                base_types = [target_type]
        except Exception:
            logger.debug("Unable to inspect type hints of item %s", type(item))
            return False

        return datetime in base_types

    def __format_cell_value(self, value: Any, field_name: str, item: Any) -> Any:
        """Formats a raw value to the expected Excel format.

        Args:
            value: The raw value to format.
            field_name: The target field name.
            item: The parent object containing the value.

        Returns:
            Any: The formatted value.
        """
        if isinstance(value, bool):
            # Default to string True/False if no specific mapping is configured
            return "True" if value else "False"

        if isinstance(value, (IPv4Address, IPv6Address)):
            return str(value)

        if isinstance(value, Enum):
            return value.value

        is_date = isinstance(value, datetime) or (
            value is None and self.__check_if_date_field(item, field_name)
        )
        if is_date:
            return format_datetime(value)

        return value if value is not None else ""
