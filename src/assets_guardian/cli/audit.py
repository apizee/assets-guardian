import logging
from pathlib import Path

from assets_guardian.core.cache.cache import CacheManager
from assets_guardian.core.domain.engines.audit_engine import AuditEngine
from assets_guardian.core.domain.engines.check_engine import CheckEngine
from assets_guardian.core.domain.engines.pdf_engine import PdfEngine
from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.domain.models.location import Location
from assets_guardian.core.domain.registry.collector_factory import instantiate_collectors
from assets_guardian.core.microsoft365.send_email_microsoft365 import SendEmailMicrosoft365
from assets_guardian.core.microsoft365.upload_microsoft365 import push_to_location
from assets_guardian.utils.dates import add_date_to_filename

logger = logging.getLogger(__name__)


def _local_path_for(ctx: Context, location: Location) -> str:
    """Computes the local path to write to for a Location, whether local or remote.

    Args:
        ctx: The application context.
        location: The configured file location (local or remote).

    Returns:
        str: The local path to write to (the configured path if local, a cache path
            otherwise), with any 'DATE' placeholder replaced by today's date.
    """
    filename = Path(add_date_to_filename(location.clean_path)).name
    if location.is_local:
        return add_date_to_filename(location.clean_path)
    return str(Path(ctx.app_config.cache.cache_dir) / filename)


def _push_report(ctx: Context, location: Location, path: str, label: str) -> None:
    """Pushes a local report file to SharePoint if the Location is remote, logging the outcome.

    Args:
        ctx: The application context.
        location: The configured file location (local or remote).
        path: Path to the local file to push.
        label: Human-readable name of the report, used in log messages.
    """
    if push_to_location(ctx, location, path):
        if location.is_remote:
            logger.info("%s pushed to SharePoint.", label)
    else:
        logger.error("Failed to push the %s to SharePoint.", label)


def run_audit_command(ctx: Context) -> None:
    """Executes the IAM compliance audit process and generates a report.

    This function orchestrates the following technical flow:
    1. Global execution of CheckEngine before proceeding.
    2. Loading and validating active collectors.
    3. Initializing the audit engine (AuditEngine) with its cache manager.
    4. Running the audit (data collection, rule evaluation, and detection).
    5. Generating the PDF report via PdfEngine.
    6. Pushing the PDF report and, if present, the Excel repository to SharePoint when
       configured as remote.
    7. Notifying the author by email that the report is ready.
    8. Final cleanup of the temporary audit cache.

    Args:
        ctx: The application context containing the configuration and parameters.

    Raises:
        RuntimeError: If the environment verification fails (CheckEngine).
    """
    logger.info("Launching source audit...")

    # Global execution of CheckEngine before proceeding
    check_engine = CheckEngine()
    if not check_engine.run(ctx):
        logger.error("Environment check failed. Stopping the audit.")
        raise RuntimeError("Configuration error, see assets-guardian check for more details.")

    # Instantiating and validating active collectors.
    collectors = list(instantiate_collectors(ctx.app_config.integrations).values())

    # Running the audit engine
    audit_engine = AuditEngine(cache=CacheManager(config=ctx.app_config.cache))
    try:
        results = audit_engine.run(collectors, ctx)

        logger.debug("Audit engine executed successfully.")

        # Generating the PDF report
        pdf_engine = PdfEngine()
        pdf_location = ctx.app_config.paths.pdf
        output_path = _local_path_for(ctx, pdf_location)
        pdf_engine.generate(results, ctx, output_path=output_path)

        # Push the PDF report if configured as remote
        _push_report(ctx, pdf_location, output_path, "PDF report")

        # Notify each configured recipient that the audit report is ready
        send_email_microsoft365 = SendEmailMicrosoft365.from_context(ctx)
        if send_email_microsoft365 and ctx.app_config.notification_emails:
            send_email_microsoft365.send_email(
                subject="Assets Guardian - Audit report available",
                text=f"The audit report '{Path(output_path).name}' is available on SharePoint.",
                recipients={"to": ctx.app_config.notification_emails, "cc": []},
            )
        else:
            logger.info("No notification email configured, skipping audit report notification.")

    finally:
        # Cleanup after the audit
        audit_engine.cache.cleanup("audit", env=ctx.app_config.env)
        logger.debug("Audit cache cleanup completed.")
