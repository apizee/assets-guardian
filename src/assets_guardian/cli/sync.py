import logging
from pathlib import Path

from assets_guardian.core.cache.cache import CacheManager
from assets_guardian.core.domain.engines.check_engine import CheckEngine
from assets_guardian.core.domain.engines.excel_engine import ExcelEngine
from assets_guardian.core.domain.engines.sync_engine import SyncEngine
from assets_guardian.core.domain.models.context import AssetsGuardianMode, Context
from assets_guardian.core.domain.registry.collector_factory import instantiate_collectors
from assets_guardian.core.microsoft365.upload_microsoft365 import push_to_location
from assets_guardian.utils.dates import add_date_to_filename

logger = logging.getLogger(__name__)


def run_sync_command(ctx: Context) -> None:
    """Executes the permissions synchronization command.

    This function orchestrates the following technical flow:
    1. Global execution of CheckEngine before proceeding.
    2. Loading active collectors.
    3. Initializing the synchronization engine and its cache.
    4. Running the synchronization (collection).
    5. Generating the Excel repository and pushing it to SharePoint if configured as remote.
    6. Final cleanup of the temporary synchronization cache.

    Args:
        ctx: The application context containing the configuration and parameters.

    Raises:
        RuntimeError: If the environment verification fails (CheckEngine).
    """

    logger.info("Launching excel synchronization...")

    # Global execution of CheckEngine before proceeding
    check_engine = CheckEngine()
    if not check_engine.run(ctx):
        logger.error("Environment check failed. Stopping the synchronization.")
        raise RuntimeError("Configuration error, see assets-guardian check for more details.")

    # Instantiating and validating active collectors.
    collectors = list(instantiate_collectors(ctx.app_config.integrations).values())

    # Running the synchronization engine
    sync_engine = SyncEngine(cache=CacheManager(config=ctx.app_config.cache))
    excel_engine = ExcelEngine()

    try:
        results = sync_engine.run(collectors)
        logger.debug("Synchronization engine executed successfully.")

        excel_location = ctx.app_config.paths.excel
        filename = Path(add_date_to_filename(excel_location.clean_path)).name

        if excel_location.is_local:
            output_path = add_date_to_filename(excel_location.clean_path)
        else:
            output_path = str(Path(ctx.app_config.cache.cache_dir) / filename)
        # Generating the Excel file
        excel_engine.generate(results, ctx, output_path=output_path)
        logger.debug("Excel repository generation completed successfully.")
        if push_to_location(ctx, excel_location, output_path):
            if excel_location.is_remote:
                logger.info("Excel repository pushed to SharePoint.")
        else:
            logger.error("Failed to push the Excel repository to SharePoint")
    finally:
        # Temporary cache cleanup
        sync_engine.cache.cleanup(AssetsGuardianMode.SYNC, env=ctx.app_config.env)
        logger.debug("Synchronization cache cleanup completed.")
