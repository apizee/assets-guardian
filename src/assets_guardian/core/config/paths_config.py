from dataclasses import dataclass
from typing import Any

from assets_guardian.core.config.loader import get_config_value
from assets_guardian.core.domain.models.location import Location
from assets_guardian.core.domain.models.validator import validate_field

DEFAULT_PATH_EXCEL = "local:outputs/assets_guardian.xlsx"
DEFAULT_PATH_PDF = "local:outputs/audit_report.pdf"
DEFAULT_PATH_RULES = "local:config/rules_config.yml"
DEFAULT_PATH_EXCEL_CONFIG = "local:config/excel_config.json"
DEFAULT_PATH_PDF_CONFIG = "local:config/pdf_config.json"
DEFAULT_PATH_EMPLOYEES = "local:config/employees.json"


@dataclass
class PathsConfig:
    """Configuration of file paths.

    Attributes:
        excel (Location): Path to the Excel repository.
        pdf (Location): Path to the PDF report.
        rules (Location): Path to the rules configuration file.
        excel_config (Location): Path to the Excel rules configuration file.
        pdf_config (Location): Path to the PDF rules configuration file.
    """

    excel: Location
    pdf: Location
    rules: Location
    excel_config: Location
    pdf_config: Location
    employees: Location
    config_path: Location

    def __post_init__(self) -> None:
        """Validates the configuration of file paths."""
        validate_field(self, "excel", Location)
        validate_field(self, "pdf", Location)
        validate_field(self, "rules", Location)
        validate_field(self, "excel_config", Location)
        validate_field(self, "pdf_config", Location)
        validate_field(self, "employees", Location)
        validate_field(self, "config_path", Location)

    @classmethod
    def from_dict(cls, data: dict[str, Any], config_path: str) -> "PathsConfig":
        return cls(
            excel=Location(
                get_config_value(
                    "excel",
                    data,
                    default=DEFAULT_PATH_EXCEL,
                    env_name="PATH_EXCEL",
                )
            ),
            pdf=Location(
                get_config_value(
                    "pdf",
                    data,
                    default=DEFAULT_PATH_PDF,
                    env_name="PATH_PDF",
                )
            ),
            rules=Location(
                get_config_value(
                    "rules",
                    data,
                    default=DEFAULT_PATH_RULES,
                    env_name="PATH_RULES",
                )
            ),
            excel_config=Location(
                get_config_value(
                    "excel_config",
                    data,
                    default=DEFAULT_PATH_EXCEL_CONFIG,
                    env_name="PATH_EXCEL_CONFIG",
                )
            ),
            pdf_config=Location(
                get_config_value(
                    "pdf_config",
                    data,
                    default=DEFAULT_PATH_PDF_CONFIG,
                    env_name="PATH_PDF_CONFIG",
                )
            ),
            employees=Location(
                get_config_value(
                    "employees",
                    data,
                    default=DEFAULT_PATH_EMPLOYEES,
                    env_name="PATH_EMPLOYEES",
                )
            ),
            config_path=Location(f"local:{config_path}"),
        )
