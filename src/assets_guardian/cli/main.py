"""Assets Guardian CLI entry point."""

import logging

import click

import assets_guardian.utils.timer as timer
from assets_guardian.core.config.app_config import AppConfig
from assets_guardian.core.config.loader import get_project_version, load_yaml_config
from assets_guardian.core.domain.models.context import AssetsGuardianMode, Context
from assets_guardian.core.domain.registry.discovery import discover_all
from assets_guardian.core.logging.logger import init_logging

from .audit import run_audit_command
from .check import run_check_command
from .script import run_script_command
from .sync import run_sync_command

BANNER = r"""                    ***++++*++
             *********+* ++++======  ==          ___                   __
             ********        ===  ===           /   |  _____________  / /______
            ###*               ==== ==         / /| | / ___/ ___/ _ \/ __/ ___/
            ####             ==== ===-        / ___ |(__  |__  )  __/ /_(__  )
            ####           -==++  ====       /_/  |_/____/____/\___/\__/____/  ___
             ### +**+===  ==++   .===              / ____/_  ______ __________/ (_)___ _____
             ## ##  ***====++    ====             / / __/ / / / __ `/ ___/ __  / / __ `/ __ \
             ####=    **==++     ====            / /_/ / /_/ / /_/ / /  / /_/ / / /_/ / / / /
              ####     +***     =+==             \____/\__,_/\__,_/_/   \__,_/_/\__,_/_/ /_/
               -###+    *     * +++
                ###**        **+++                            A modular IAM governance tool
                  ##***#  ####*+
                   *#########*+
                      #####*
"""


class AssetsGuardianGroup(click.Group):
    """Custom Click Group to prepend a beautiful ASCII banner to the help output."""

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        formatter.write(BANNER + "\n")
        super().format_help(ctx, formatter)


@click.group(cls=AssetsGuardianGroup)
@click.version_option(version=get_project_version(), prog_name="assets-guardian")
@click.option("--config", default="config/config.yml", help="Path to the configuration file.")
@click.option("--dry-run", is_flag=True, help="Simulation mode without side effects.")
@click.option("-v", "--verbose", is_flag=True, help="DEBUG logs in the console.")
@click.option("-q", "--quiet", is_flag=True, help="ERROR logs only.")
@click.option("--no-interaction", is_flag=True, help="Non-interactive mode.")
@click.pass_context
def cli(
    ctx: click.Context,
    config: str,
    dry_run: bool,
    verbose: bool,
    quiet: bool,
    no_interaction: bool,
) -> None:
    """Assets Guardian, IAM governance tool."""
    # The dictionary or context object will be initialized at the end of the cli method.

    # Loads the raw YAML configuration from the path passed as CLI parameter.
    config_parameters = load_yaml_config(config)
    app_config = AppConfig.create_from_dict(config_parameters, config_path=config)

    # Determines the console logging level by applying the CLI options
    # (verbose/quiet) which take priority over the default configuration.
    if verbose:
        app_config.logging.console_level = logging.DEBUG
    elif quiet:
        app_config.logging.console_level = logging.CRITICAL

    # Initializes the logging system (log files and console output).
    init_logging(logging_config=app_config.logging)

    # Since loggers are now operational, all events can be traced from here.
    ctx.obj = Context(
        app_config=app_config,
        dry_run=dry_run,
        verbose=verbose,
        quiet=quiet,
        no_interaction=no_interaction,
        mode=AssetsGuardianMode(ctx.invoked_subcommand or AssetsGuardianMode.UNRECOGNIZED),
    )

    # Dynamically discovers and registers all installed plugins and their rules.
    discover_all(ctx.obj)


@cli.command()
@click.pass_context
def sync(ctx: click.Context) -> None:
    """Synchronizes the permissions Excel repository.

    This command connects to the configured data sources to extract current permissions
    information, then updates the reference Excel file while preserving manual changes
    and specific tabs.
    """
    start = timer.start_timer()
    run_sync_command(ctx.obj)
    timer.end_timer(start)


@cli.command()
@click.pass_context
def audit(ctx: click.Context) -> None:
    """Executes a comprehensive IAM compliance audit.

    This command retrieves data from the Excel file and updated data to evaluate all
    configured compliance, comparison, and security matrix rules. It produces an audit report
    detailing security gaps and vulnerabilities.
    """
    start = timer.start_timer()
    run_audit_command(ctx.obj)
    timer.end_timer(start)


@cli.command()
@click.pass_context
def check(ctx: click.Context) -> None:
    """Verifies connectivity and status of external sources (Health Check).

    This command tests the connection and authentication with all configured APIs
    and databases to ensure their proper operational function.
    """
    start = timer.start_timer()
    run_check_command(ctx.obj)
    timer.end_timer(start)


@cli.command()
@click.argument("name")
@click.pass_context
def script(ctx: click.Context, name: str) -> None:
    """Executes a custom Python script from the local scripts/ directory.

    This advanced command loads scripts/NAME.py (the .py suffix is optional) and calls
    its mandatory run(ctx) function with the full application context: configuration,
    logging system, and registered source clients. Scripts are arbitrary Python executed
    without guardrails; this power-user feature is aimed at tinkerers, not day-to-day use.
    """
    run_script_command(ctx.obj, name)


if __name__ == "__main__":
    cli()
