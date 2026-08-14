import json
import os
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import yaml

from assets_guardian import ROOT_PROJECT


def load_yaml_config(config_file_path: str) -> dict[str, Any]:
    """Loads a YAML configuration file.

    Args:
        config_file_path: Path to the YAML configuration file.

    Returns:
        dict[str, Any]: A dictionary containing the configuration data.

    Raises:
        FileNotFoundError: If the configuration file is not found.
        ValueError: If the file is empty.
        TypeError: If the file does not contain a valid YAML dictionary.
    """
    path = Path(config_file_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    # Load the .env file
    dotenv_path = ROOT_PROJECT.parent.parent / ".env"

    if dotenv_path.exists():
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

    with path.open(encoding="utf-8") as file:
        content = os.path.expandvars(file.read())
        data = yaml.safe_load(content)

    if data is None:
        raise ValueError(f"Configuration file is empty: {path}")

    if not isinstance(data, dict):
        raise TypeError(f"Configuration file must contain a YAML dictionary. Got: {type(data)}")

    return data


def load_json(file_path: str) -> Any:
    """Loads a JSON file.

    Args:
        file_path: Path to the JSON file.

    Returns:
        Any: The loaded JSON data.

    Raises:
        FileNotFoundError: If the file is not found.
        ValueError: If the file is empty or not a valid JSON.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")

    with path.open(encoding="utf-8") as file:
        try:
            data = json.load(file)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in file {path}: {e}") from e

    if data is None:
        raise ValueError(f"JSON file is empty: {path}")

    return data


def browse_dict(data: dict[str, Any], key: str) -> Any:
    """Browses a dictionary using nested keys (e.g., 'a:b:c').

    Args:
        data: Dictionary to search.
        key: Configuration key with ':' delimiter.

    Returns:
        Any: The value found or None if the key does not exist.
    """
    current: Any = data
    for subkey in key.split(":"):
        if isinstance(current, dict) and subkey in current:
            current = current[subkey]
        else:
            return None
    return current


def get_env_key_name(key: str) -> str:
    """Generates the environment variable name corresponding to the key.

    Args:
        key: Configuration key (e.g., 'logging:level').

    Returns:
        str: Environment-formatted variable name (e.g., 'LOGGING_LEVEL').
    """
    return key.upper().replace(":", "_").replace("-", "_")


def get_config_value(
    key: str,
    data: dict[str, Any],
    default: Any = None,
    env_name: str | None = None,
    env_override: bool = True,
) -> Any:
    """Retrieves a configuration value (Env > YAML > Default).

    Args:
        key: Configuration key (e.g., 'logging:level').
        data: YAML data dictionary.
        default: Default value if not found.
        env_name: Specific environment variable name (optional).
        env_override: If True, prioritizes environment variables.

    Returns:
        Any: The configuration value found.

    Raises:
        KeyError: If the key is missing and no default is provided.
    """

    # Check environment variables
    if env_override:
        val = os.getenv(env_name or get_env_key_name(key))
        if val is not None:
            return val

    # Check dictionary
    current = browse_dict(data, key)

    # Search for a result
    if current is not None:
        return str(current)

    # Return default value if still not found
    if default is not None:
        return default

    raise KeyError(f"""Missing required configuration key: {key!r}
                   (or ENV: {get_env_key_name(key)!r})""")


def load_profiles(employees_file_path: str | None) -> list[str]:
    """Extracts the unique list of profiles from the configured file."""

    if not employees_file_path:
        return ["R&D", "Finance", "Marketing", "Security", "Admin"]

    path = Path(employees_file_path)
    if not path.exists():
        return ["R&D", "Finance", "Marketing", "Security", "Admin"]

    try:
        with path.open(encoding="utf-8") as file:
            employees = json.load(file)
        profiles = set()  # set automatically handles duplicates
        for emp in employees:
            emp_profiles = emp.get("profiles", "")
            if emp_profiles:
                # Split by comma and clean whitespace
                for p in emp_profiles.split(","):
                    profiles.add(p.strip())

        return sorted(profiles)

    except Exception:
        return ["R&D", "Finance", "Marketing", "Security", "Admin"]


def load_employees_profiles(employees_file_path: str | None) -> dict[str, list[str]]:
    """Extracts user profiles (Email -> list[Profile]) from the configured JSON file."""
    if not employees_file_path:
        return {}

    path = Path(employees_file_path)
    if not path.exists():
        return {}

    try:
        with path.open(encoding="utf-8") as file:
            employees = json.load(file)

        profiles: dict[str, list[str]] = {}
        for emp in employees:
            user_id = to_str_list(emp.get("email")) or to_str_list(emp.get("username"))
            emp_profiles = emp.get("profiles", "")

            if user_id and emp_profiles:
                # Split by comma and clean whitespace
                parsed_profiles = [p.strip() for p in emp_profiles.split(",")]
                for identifiant in user_id:
                    profiles[identifiant] = parsed_profiles
        return profiles  # noqa: TRY300
    except Exception:
        return {}


def get_project_version() -> str:
    """Returns the project version."""

    try:
        return version("assets-guardian")
    except PackageNotFoundError:
        pyproject_path = ROOT_PROJECT.parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            with pyproject_path.open("rb") as file:
                return str(tomllib.load(file).get("project", {}).get("version", "0.0.0"))
        return "0.0.0"


def to_str_list(value: Any) -> list[str]:
    """Normalizes a value into a list of strings."""
    if isinstance(value, list):
        return [str(x) for x in value]
    if not value:
        return []
    return [str(value)]
