"""Example Assets Guardian user script.

Run it with: assets-guardian script example

Every script dropped at the root of the scripts/ directory must expose a run(ctx)
function. The received Context gives full access to the loaded configuration, the
initialized logging system, and the plugin registries (client providers, collectors).
"""

import logging

from assets_guardian.core.domain.models.context import Context
from assets_guardian.core.domain.registry.client_registry import ClientProviderRegistry

logger = logging.getLogger(__name__)


def run(ctx: Context) -> None:
    """Demonstrates what an Assets Guardian user script can access.

    Args:
        ctx: The application context containing the configuration and parameters.
    """
    logger.info(
        "Running in '%s' environment (dry_run=%s, mode=%s).",
        ctx.app_config.env,
        ctx.dry_run,
        ctx.mode,
    )

    # Plugin client providers are already discovered and registered when a script runs:
    # instantiate one per configured integration instance and check its connectivity.
    for source_name, instances in ctx.app_config.integrations.items():
        for instance_id, instance_params in instances.items():
            params = dict(instance_params or {})
            params.setdefault("instance_id", instance_id)
            try:
                provider = ClientProviderRegistry.instantiates_clientprovider(source_name, params)
            except KeyError:
                logger.warning("No client provider registered for source '%s'.", source_name)
                continue
            logger.info(
                "Source %s:%s is %s.",
                source_name,
                instance_id,
                "healthy" if provider.health_check() else "unreachable",
            )
