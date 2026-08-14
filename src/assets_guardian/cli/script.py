import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType

from assets_guardian.core.domain.models.context import Context

logger = logging.getLogger(__name__)

# User scripts directory, resolved against the current working directory
# (same convention as the logs/ directory).
DIR_SCRIPTS = Path("scripts")


def run_script_command(ctx: Context, name: str) -> None:
    """Executes a user-provided Python script from the scripts/ directory.

    This function orchestrates the following technical flow:
    1. Resolving and validating the script file path (scripts/<name>.py).
    2. Loading the file as an in-memory Python module.
    3. Calling its mandatory run(ctx) entry point with the application context.

    Args:
        ctx: The application context containing the configuration and parameters.
        name: File name of the script inside scripts/, with or without the .py suffix.

    Raises:
        ValueError: If the name is empty or is not a plain file name.
        FileNotFoundError: If the script file does not exist in the scripts/ directory.
        ImportError: If the file cannot be loaded as a Python module.
        TypeError: If the script does not expose a callable run function.
    """
    logger.info("Launching user script '%s'...", name)

    script_path = _resolve_script_path(name)
    module = _load_script_module(script_path)

    # Enforcing the power-user contract: every script exposes a run(ctx) entry point.
    entry_point = getattr(module, "run", None)
    if not callable(entry_point):
        logger.error("Script '%s' has no callable 'run' entry point.", script_path.name)
        raise TypeError(f"Script '{script_path.name}' must expose a callable run(ctx) function.")

    # Exceptions raised by the script itself propagate to the caller on purpose:
    # power users get the full traceback, exactly like any other Assets Guardian failure.
    entry_point(ctx)
    logger.debug("Script '%s' executed successfully.", script_path.name)


def _resolve_script_path(name: str) -> Path:
    """Builds and validates the path of a user script inside the scripts/ directory.

    Args:
        name: File name of the script, with or without the .py suffix.

    Returns:
        The path of the existing script file.

    Raises:
        ValueError: If the name is empty or is not a plain file name.
        FileNotFoundError: If the script file does not exist.
    """
    filename = name if name.endswith(".py") else f"{name}.py"

    # Scripts live at the root of scripts/: sub-paths and traversal are rejected.
    if not name or Path(filename).name != filename:
        raise ValueError(f"Invalid script name '{name}': expected a plain file name.")

    script_path = DIR_SCRIPTS / filename
    if not script_path.is_file():
        logger.error("Script '%s' not found in the '%s/' directory.", filename, DIR_SCRIPTS)
        raise FileNotFoundError(f"Script '{filename}' not found in the '{DIR_SCRIPTS}/' directory.")

    return script_path


def _load_script_module(script_path: Path) -> ModuleType:
    """Loads a script file as an in-memory Python module.

    Args:
        script_path: Path of the script file to load.

    Returns:
        The loaded and executed module.

    Raises:
        ImportError: If the file cannot be loaded as a Python module.
    """
    module_name = f"assets_guardian_script_{script_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load the script '{script_path}' as a Python module.")

    module = importlib.util.module_from_spec(spec)
    # Registered in sys.modules before execution so the script behaves like a
    # regular imported module (dataclasses, pickling, introspection).
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module
