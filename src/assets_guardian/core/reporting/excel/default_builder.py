import datetime
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from assets_guardian.core.domain.ports.sheet_builders import ISheetBuilder
from assets_guardian.core.reporting.excel.rules_loader import load_rules

logger = logging.getLogger(__name__)


class DefaultSheetBuilder(ISheetBuilder):
    """Default transverse Excel sheet builder.

    Handles building standard core application sheets
    (Access Review Scope List, Employees list) independently of plugins.
    """

    def __init__(
        self,
        employees_file_path: str | Path | None,
        rules_file_path: str | Path | None,
        author: str | None = None,
    ) -> None:
        """Initializes the default transverse sheet builder.

        Args:
            employees_file_path: Path to the JSON file containing the employee list.
            rules_file_path: Path to the JSON Excel rules configuration file.
            author: Full name of the audit author.
        """
        self.employees_file_path = employees_file_path
        self.rules_file_path = rules_file_path
        self.author = author
        self.source_name = "default"

    @property
    def sheet_names(self) -> list[str]:
        """Returns the list of default sheets defined in the rules file.

        Returns:
            list[str]: The list of transverse sheet names to create.
        """
        if not self.rules_file_path:
            return []

        global_rules = load_rules(self.rules_file_path)
        return [name for name in global_rules if name != "sheet_name"]

    @property
    def preserved_columns(self) -> dict[str, dict[str, list[str]]]:
        """Defines columns to preserve for default sheets.

        Returns:
            dict[str, dict[str, list[str]]]: An empty dict since no columns
                need to be preserved for these sheets.
        """
        return {}

    def get_rules(self) -> dict[str, Any]:
        """Loads and returns global formatting and validation rules.

        Returns:
            dict[str, Any]: A dictionary containing validation rules for transverse sheets.
        """
        if not self.rules_file_path:
            return {}
        return load_rules(self.rules_file_path)

    def build(
        self,
        worksheet: Any,
        data: Any,
        preserved: Any,  # noqa: ARG002
        rules: Any,
    ) -> None:
        """Builds the requested sheet based on its name.

        Args:
            worksheet: The Excel worksheet currently being written (ExcelWorksheet).
            data: Structured collected results.
            preserved: Preserved data.
            rules: Formatting rules for the current sheet.
        """
        sheet_name = worksheet.title
        logger.info("Building default sheet: %s", sheet_name)

        if sheet_name == "Access Review Scope List":
            self.__build_scope_list(worksheet, data, rules)
        elif sheet_name == "Employees list":
            self.__build_employees_list(worksheet, rules)

    def __extract_location(self, result: Any) -> str:
        """Extracts the root URL (location) from collector metadata.

        Args:
            result: The collector result (CollectorResult).

        Returns:
            str: The base URL or 'Unknown' if not found.
        """
        for identity in getattr(result, "identities", []):
            if identity.metadata and "web_url" in identity.metadata:
                url = identity.metadata["web_url"]
                parsed = urlparse(url)
                if parsed.netloc:
                    return f"{parsed.scheme}://{parsed.netloc}/"

        for asset in getattr(result, "assets", []):
            if asset.metadata and "web_url" in asset.metadata:
                url = asset.metadata["web_url"]
                parsed = urlparse(url)
                if parsed.netloc:
                    return f"{parsed.scheme}://{parsed.netloc}/"

        return "Unknown"

    def __build_scope_list(self, worksheet: Any, data: Any, rules: Any) -> None:
        """Populates the 'Access Review Scope List' sheet with collection information.

        Args:
            worksheet: The Excel worksheet currently being written.
            data: Collected results from active integrations.
            rules: Configured rules and columns.
        """
        widths = [25, 35, 30, 25, 20, 25, 20]
        worksheet.set_column_widths(widths)

        headers = [
            col.get("column_name")
            for col in rules
            if isinstance(col, dict) and "column_name" in col
        ]
        if not headers:
            headers = [
                "Asset",
                "Asset Location",
                "Access Review Method",
                "Latest Access Review (UTC)",
                "Author",
                "Latest Sync (UTC)",
                "Sync Author",
            ]
        worksheet.append_row(headers, is_header=True)

        if isinstance(data, dict):
            for (source_name, instance_id), result in sorted(data.items()):
                location = self.__extract_location(result)
                now_utc = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
                row = [
                    f"{source_name.capitalize()} - {instance_id}",  # Asset
                    location,  # Asset Location
                    "Automated (Assets Guardian)",  # Access Review Method
                    now_utc,  # Latest Access Review (UTC)
                    self.author or "",  # Author
                    now_utc,  # Latest Sync (UTC)
                    self.author or "",  # Sync Author
                ]
                worksheet.append_row(row)

    def __load_employees(self) -> list[dict[str, Any]]:
        """Loads the employee list from the JSON registry file.

        Returns:
            list[dict[str, Any]]: The list of employees as dictionaries.
        """
        if not self.employees_file_path or not Path(self.employees_file_path).exists():
            return []

        try:
            with Path(self.employees_file_path).open(encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            logger.exception(
                "Error reading employees from %s",
                self.employees_file_path,
            )
            return []

    def __build_employees_list(self, worksheet: Any, rules: Any) -> None:
        """Populates the 'Employees list' sheet from the HR reference file.

        Args:
            worksheet: The Excel worksheet currently being written.
            rules: Configured rules and columns.
        """
        widths = [20, 20, 40, 20, 70]
        worksheet.set_column_widths(widths)

        headers = [
            col.get("column_name")
            for col in rules
            if isinstance(col, dict) and "column_name" in col
        ]
        if not headers:
            headers = ["First Name", "Last Name", "Email", "Username", "Access Profiles"]
        worksheet.append_row(headers, is_header=True)

        employees = self.__load_employees()
        for emp in employees:
            if not isinstance(emp, dict):
                continue
            row = [
                emp.get("first_name", ""),
                emp.get("last_name", ""),
                self.__join_field(emp.get("email", "")),
                self.__join_field(emp.get("username", "")),
                emp.get("profiles", ""),
            ]
            worksheet.append_row(row)

    def __join_field(self, value: Any) -> str:
        """Normalizes a field that may hold a single value or a list of values.

        Args:
            value: The raw field value, either a string or a list of strings.

        Returns:
            str: The values joined with ", " if value is a list, otherwise value as a string.
        """
        if isinstance(value, list):
            return ", ".join(str(x) for x in value)
        return str(value)
