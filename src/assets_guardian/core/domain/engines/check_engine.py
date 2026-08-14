import logging
import os
import re
from pathlib import Path
from typing import Any

import click

from assets_guardian.core.config.loader import load_json, load_yaml_config
from assets_guardian.core.config.validator import validate_config
from assets_guardian.core.domain.models.context import AssetsGuardianMode, Context
from assets_guardian.core.domain.registry.client_registry import ClientProviderRegistry
from assets_guardian.core.microsoft365.download_microsoft365 import DownloadMicrosoft365
from assets_guardian.core.microsoft365.resolve_path_microsoft365 import ResolvePathMicrosoft365

logger = logging.getLogger(__name__)


LABELS = {
    "config": "Configuration (config.yml)",
    "logging_path": "Logging path",
    "logging_folder": "Logging folder",
    "employees": "Employees (employees.json)",
    "excel": "Excel Rules (excel_config.json)",
    "rules_config": "Audit Rules (rules_config.yml)",
    "pdf": "PDF Rules (pdf_config.json)",
    "output_paths": "Output paths (excel, pdf)",
    "cache_dir": "Cache directory",
    "email": "Notification emails (notification_email)",
}

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CheckEngine:
    """Validation engine for connectivity and configurations."""

    def __init__(self) -> None:
        self.details: dict[str, Any] = {}
        self.email_warning: bool = False

    def run(self, ctx: Context) -> bool:
        """Runs global system checks and returns True if no errors are detected.

        Args:
            ctx: The application context.

        Returns:
            bool: True if all configurations and connections are operational, False otherwise.
        """
        self.details = self.run_details(ctx)
        self.__log_report(ctx)
        return self.__is_overall_valid(ctx)

    def __log_report(self, ctx: Context) -> None:
        """Prints the detailed check report to the console.

        Args:
            ctx: The application context containing execution options.
        """
        self.__log_details_to_file()

        if ctx.mode != AssetsGuardianMode.CHECK:
            return

        box_width = 60
        self.__print_header(box_width)
        self.__print_system_checks(box_width)

        instances_status = self.details.get("instances", {})
        self.__print_instances_checks(instances_status, box_width)
        self.__print_bilan(instances_status, box_width)

    def __log_details_to_file(self) -> None:
        """Logs the raw report details at the DEBUG level."""
        logger.debug("--- Detailed Check Report ---")
        for key, label in LABELS.items():
            if key in self.details:
                status = "OK" if self.details[key] else "ERR"
                logger.debug("%s: %s", label, status)

        instances_status = self.details.get("instances", {})
        logger.debug("Instances connectivity:")
        for instance_key, status in instances_status.items():
            logger.debug("  - %s: %s", instance_key, "Accessible" if status else "Inaccessible")

        success = sum(1 for status in instances_status.values() if status)
        total = len(instances_status)
        logger.debug("Health check summary: %d/%d operational source(s).", success, total)

    def __print_header(self, box_width: int) -> None:
        """Prints the check report header.

        Args:
            box_width: The total box width in characters.
        """
        title = "ASSETS GUARDIAN - HEALTH CHECK"
        padded_title = title.center(box_width)

        click.echo()
        click.secho(f" ┌{'─' * box_width}┐", fg="cyan")
        click.secho(f" │{padded_title}│", fg="cyan", bold=True)
        click.secho(f" └{'─' * box_width}┘", fg="cyan")
        click.echo()

    def __print_system_checks(self, box_width: int) -> None:
        """Prints system and configuration check statuses.

        Args:
            box_width: The total box width in characters.
        """
        click.secho("  CONFIGURATION & SYSTEM CHECKS", fg="cyan", bold=True)
        click.secho("  " + "─" * box_width, fg="cyan")

        ok_sym = click.style("✔", fg="green", bold=True)
        err_sym = click.style("✘", fg="red", bold=True)
        warn_sym = click.style("⚠", fg="yellow", bold=True)
        ok_tag = click.style("[OK]", fg="green", bold=True)
        err_tag = click.style("[ERR]", fg="red", bold=True)
        warn_tag = click.style("[WARN]", fg="yellow", bold=True)

        for key, label in LABELS.items():
            if key in self.details:
                status_ok = self.details[key]
                if key == "email" and status_ok and self.email_warning:
                    symbol, tag = warn_sym, warn_tag
                else:
                    symbol = ok_sym if status_ok else err_sym
                    tag = ok_tag if status_ok else err_tag
                dots_count = max(3, box_width - len(label) - 10)
                dots = click.style("." * dots_count, fg="white", dim=True)
                click.echo(f"  {symbol}  {label} {dots} {tag}")

    def __print_instances_checks(self, instances_status: dict[str, bool], box_width: int) -> None:
        """Prints the connectivity status of configured instances.

        Args:
            instances_status: Dictionary containing connectivity statuses.
            box_width: The total box width in characters.
        """
        click.echo()
        click.secho("  INSTANCES CONNECTIVITY", fg="cyan", bold=True)
        click.secho("  " + "─" * box_width, fg="cyan")

        ok_sym = click.style("✔", fg="green", bold=True)
        err_sym = click.style("✘", fg="red", bold=True)
        accessible_tag = click.style("[ACCESSIBLE]", fg="green", bold=True)
        inaccessible_tag = click.style("[INACCESSIBLE]", fg="red", bold=True)

        if not instances_status:
            click.echo("  No instances configured.")
        else:
            for instance_key, status_ok in instances_status.items():
                symbol = ok_sym if status_ok else err_sym
                tag = accessible_tag if status_ok else inaccessible_tag
                dots_count = max(3, box_width - len(instance_key) - 18)
                dots = click.style("." * dots_count, fg="white", dim=True)
                click.echo(f"  {symbol}  {instance_key} {dots} {tag}")

    def __print_bilan(self, instances_status: dict[str, bool], box_width: int) -> None:
        """Prints the final connectivity summary.

        Args:
            instances_status: Dictionary containing connectivity statuses.
            box_width: The total box width in characters.
        """
        click.echo()
        click.secho("  " + "─" * box_width, fg="cyan")

        total = len(instances_status)
        success = sum(1 for status in instances_status.values() if status)

        if total > 0:
            if success == total:
                bilan_color = "green"
            elif success > 0:
                bilan_color = "yellow"
            else:
                bilan_color = "red"
            bilan_text = f"{success}/{total} operational source(s)"
            styled_bilan = click.style(bilan_text, fg=bilan_color, bold=True)
            click.echo(f"  Connectivity report: {styled_bilan}")
        else:
            click.echo("  Connectivity report: No sources configured.")

    def __is_overall_valid(self, ctx: Context) -> bool:
        """Determines if the global system state is valid and logs/prints the final verdict.

        Args:
            ctx: The application context containing execution options.

        Returns:
            bool: True if all validation steps and connectivity are successful, False otherwise.
        """
        instances_status = self.details.get("instances", {})
        steps_valid = all(status for name, status in self.details.items() if name != "instances")
        instances_valid = all(instances_status.values())
        overall_valid = steps_valid and instances_valid

        if overall_valid:
            logger.debug("Global verification: EVERYTHING IS OPERATIONAL")
        else:
            logger.debug("Global verification: ERRORS HAVE BEEN DETECTED")

        if ctx.mode == AssetsGuardianMode.CHECK:
            box_width = 60
            if overall_valid:
                msg = "VERDICT: EVERYTHING IS OPERATIONAL"
                padded_msg = msg.center(box_width)
                click.secho(f"  ┌{'─' * box_width}┐", fg="green", bold=True)
                click.secho(f"  │{padded_msg}│", fg="green", bold=True)
                click.secho(f"  └{'─' * box_width}┘", fg="green", bold=True)
            else:
                msg = "VERDICT: ERRORS HAVE BEEN DETECTED"
                padded_msg = msg.center(box_width)
                click.secho(f"  ┌{'─' * box_width}┐", fg="red", bold=True)
                click.secho(f"  │{padded_msg}│", fg="red", bold=True)
                click.secho(f"  └{'─' * box_width}┘", fg="red", bold=True)
            click.echo()

        return overall_valid

    def run_details(self, ctx: Context) -> dict[str, Any]:
        """Generates a summary dictionary of all checks depending on the context mode.

        Args:
            ctx: The application context containing the configuration.

        Returns:
            dict[str, Any]: Dictionary containing the status of each validation check.
        """
        details: dict[str, Any] = {}

        # YAML Config
        details["config"] = self.__check_config_yaml(ctx)

        # Logging path
        details["logging_path"] = self.__check_logging_path(ctx)

        # Logging folder
        details["logging_folder"] = self.__check_logging_folder(ctx)

        # Employees JSON
        details["employees"] = self.__check_employees_json(ctx)

        # Excel JSON
        details["excel"] = self.__check_excel_json(ctx)

        # Notification emails
        details["email"] = self.__check_emails(ctx)

        # Mode-dependent checks
        is_audit = ctx.mode == AssetsGuardianMode.AUDIT
        is_check = ctx.mode in (AssetsGuardianMode.CHECK, AssetsGuardianMode.UNRECOGNIZED)

        if is_audit or is_check:
            details["rules_config"] = self.__check_rules_config_yaml(ctx)
            details["pdf"] = self.__check_pdf_json(ctx)

        # Output paths (excel, pdf)
        details["output_paths"] = self.__check_output_paths(ctx)

        # Cache directory
        details["cache_dir"] = self.__check_cache_dir(ctx)

        # Instances connectivity checks
        instances_status = {}
        for source_name, instances in ctx.app_config.integrations.items():
            for instance_id, params in instances.items():
                if params is None:
                    params = {}
                if "instance_id" not in params:
                    params["instance_id"] = instance_id

                key = f"{source_name}:{instance_id}"
                try:
                    client_provider = ClientProviderRegistry.instantiates_clientprovider(
                        source_name, params
                    )
                    status = client_provider.health_check()
                    instances_status[key] = status
                except Exception:
                    logger.exception(
                        "Connectivity error on instance %s:%s",
                        source_name,
                        instance_id,
                    )
                    instances_status[key] = False
        details["instances"] = instances_status

        return details

    def __check_config_yaml(self, ctx: Context) -> bool:
        """Validates the config.yml file against its reference template.

        Args:
            ctx: The application context.

        Returns:
            bool: True if the configuration is valid, False otherwise.
        """
        try:
            config_path = Path(ctx.app_config.paths.config_path.clean_path)
            template_path = config_path.parent / f"template.{config_path.name}"
            if not template_path.exists():
                logger.error("Config template file not found: %s", template_path)
                return False
            config_parameters = load_yaml_config(str(config_path))
            config_template = load_yaml_config(str(template_path))
            validate_config(config_parameters, config_template)
        except Exception:
            logger.exception("Verification of config.yml failed")
            return False
        else:
            return True

    def __check_logging_path(self, ctx: Context) -> bool:
        """Validates that the configured logging path is local.

        Remote logging destinations are not supported: a live rotating file handler
        cannot write to a SharePoint location.

        Args:
            ctx: The application context.

        Returns:
            bool: True if the logging path is local, False otherwise.
        """
        try:
            if ctx.app_config.logging.path.is_remote:
                logger.error("Logging path must be local; remote paths are not supported.")
                return False
        except Exception:
            logger.exception("Verification of the logging path failed")
            return False
        else:
            return True

    def __check_logging_folder(self, ctx: Context) -> bool:
        """Validates that the logging folder exists (or can be created) and is readable/writable.

        Args:
            ctx: The application context.

        Returns:
            bool: True if the logging folder exists (or was successfully created) and has
                read/write permissions, False otherwise.
        """
        path = Path(ctx.app_config.logging.path.clean_path)
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception:
                logger.exception("Directory does not exist and cannot be created: %s", path)
                return False

        folder_valid = True
        if not os.access(path, os.R_OK):
            logger.error("Directory is not readable: %s", path)
            folder_valid = False
        if not os.access(path, os.W_OK):
            logger.error("Directory is not writable: %s", path)
            folder_valid = False

        return folder_valid

    def __check_output_paths(self, ctx: Context) -> bool:
        """Validates the excel and pdf output locations (paths/excel, paths/pdf).

        For a local location, checks that the parent directory exists (or can be
        created) and is writable. For a remote location, checks that a microsoft365
        integration is configured, since remote outputs are resolved via SharePoint.

        Args:
            ctx: The application context.

        Returns:
            bool: True if both output locations are valid, False otherwise.
        """
        outputs_valid = True
        for label, location in (
            ("excel", ctx.app_config.paths.excel),
            ("pdf", ctx.app_config.paths.pdf),
        ):
            if location.is_remote:
                if "microsoft365" not in ctx.app_config.integrations:
                    logger.error(
                        "Output path '%s' is remote but no microsoft365 integration is configured.",
                        label,
                    )
                    outputs_valid = False
                continue

            parent = Path(location.clean_path).parent
            if not parent.exists():
                try:
                    parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    logger.exception("Directory does not exist and cannot be created: %s", parent)
                    outputs_valid = False
                    continue

            if not os.access(parent, os.R_OK):
                logger.error("Directory is not readable: %s", parent)
                outputs_valid = False
            if not os.access(parent, os.W_OK):
                logger.error("Directory is not writable: %s", parent)
                outputs_valid = False

        return outputs_valid

    def __check_cache_dir(self, ctx: Context) -> bool:
        """Validates that the cache directory exists (or can be created) and is readable/writable.

        Args:
            ctx: The application context.

        Returns:
            bool: True if the cache directory exists (or was successfully created) and has
                read/write permissions, False otherwise.
        """
        path = Path(ctx.app_config.cache.cache_dir)
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception:
                logger.exception("Directory does not exist and cannot be created: %s", path)
                return False

        cache_dir_valid = True
        if not os.access(path, os.R_OK):
            logger.error("Directory is not readable: %s", path)
            cache_dir_valid = False
        if not os.access(path, os.W_OK):
            logger.error("Directory is not writable: %s", path)
            cache_dir_valid = False

        return cache_dir_valid

    def __check_rules_config_yaml(self, ctx: Context) -> bool:
        """Validates the rules_config.yml file.

        Args:
            ctx: The application context.

        Returns:
            bool: True if audit rules configuration is valid, False otherwise.
        """
        try:
            if ctx.app_config.paths.rules.is_local:
                path = ctx.app_config.paths.rules.clean_path
                load_yaml_config(path)
            if ctx.app_config.paths.rules.is_remote:
                resolver = ResolvePathMicrosoft365.from_context(ctx, ctx.app_config.paths.rules)
                if resolver is None:
                    return False
                downloader = DownloadMicrosoft365(resolver.graph, resolver, resolver.target_path)
                Path(ctx.app_config.cache.cache_dir).mkdir(parents=True, exist_ok=True)
                cached_path = str(Path(ctx.app_config.cache.cache_dir) / "rules_config.yml")
                if not downloader.pull_report(cached_path):
                    return False
                load_yaml_config(cached_path)
        except Exception:
            logger.exception("Verification of rules_config.yml failed")
            return False
        else:
            return True

    def __check_employees_json(self, ctx: Context) -> bool:
        """Validates the employees.json file.

        Args:
            ctx: The application context.

        Returns:
            bool: True if the employees data is valid, False otherwise.
        """
        try:
            if ctx.app_config.paths.employees.is_local:
                path = ctx.app_config.paths.employees.clean_path
                load_json(path)
            if ctx.app_config.paths.employees.is_remote:
                resolver = ResolvePathMicrosoft365.from_context(ctx, ctx.app_config.paths.employees)
                if resolver is None:
                    return False
                downloader = DownloadMicrosoft365(resolver.graph, resolver, resolver.target_path)
                Path(ctx.app_config.cache.cache_dir).mkdir(parents=True, exist_ok=True)
                cached_path = str(Path(ctx.app_config.cache.cache_dir) / "employees.json")
                if not downloader.pull_report(cached_path):
                    return False
                load_json(cached_path)
        except Exception:
            logger.exception("Verification of employees.json failed")
            return False
        else:
            return True

    def __check_excel_json(self, ctx: Context) -> bool:
        """Validates the excel_config.json file.

        Args:
            ctx: The application context.

        Returns:
            bool: True if the Excel rules configuration is valid, False otherwise.
        """
        try:
            location = ctx.app_config.paths.excel_config
            if location.is_remote:
                logger.error(
                    "excel_config.json must be a local file; remote paths are not supported."
                )
                return False
            load_json(location.clean_path)
        except Exception:
            logger.exception("Verification of excel_config.json failed")
            return False
        else:
            return True

    def __check_pdf_json(self, ctx: Context) -> bool:
        """Validates the pdf_config.json file.

        Args:
            ctx: The application context.

        Returns:
            bool: True if the PDF rules configuration is valid, False otherwise.
        """
        try:
            location = ctx.app_config.paths.pdf_config
            if location.is_remote:
                logger.error(
                    "pdf_config.json must be a local file; remote paths are not supported."
                )
                return False
            load_json(location.clean_path)
        except Exception:
            logger.exception("Verification of pdf_config.json failed")
            return False
        else:
            return True

    def __check_emails(self, ctx: Context) -> bool:
        """Validates that notification_email is a list of valid email addresses.

        Args:
            ctx: The application context.

        Returns:
            bool: True if notification_emails is valid, False otherwise.
        """
        try:
            notification_emails = ctx.app_config.notification_emails
            is_valid = False
            if isinstance(notification_emails, list):
                is_valid = True
                if notification_emails:
                    for email in notification_emails:
                        if isinstance(email, str) and EMAIL_PATTERN.fullmatch(email):
                            is_valid = True
                        else:
                            logger.error("Invalid email address in notification_email: %s", email)
                            is_valid = False
                            break
                else:
                    self.email_warning = True
                    logger.warning("notification_email is empty: no notification emails configured")
            else:
                logger.error(
                    "notification_email must be a list, got %s", type(notification_emails).__name__
                )
        except Exception:
            logger.exception("Verification of notification_email failed")
            return False
        else:
            return is_valid
