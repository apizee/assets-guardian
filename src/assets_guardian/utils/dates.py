import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DATETIME_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%f",  # 2023-10-27T10:00:00.000000 ISO 8601
    "%Y-%m-%dT%H:%M:%S",  # 2023-10-27T10:00:00 ISO 8601 without milliseconds
    "%Y-%m-%d %H:%M:%S",  # 2023-10-27 10:00:00
    "%Y-%m-%d",  # 2023-10-27 ISO 8601 without time
    "%Y/%m/%d",  # 2023/10/27
    "%d/%m/%Y %H:%M:%S",  # 27/10/2023 10:00:00
    "%d/%m/%Y",  # 27/10/2023
]


def __try_strptime(val: str, formt: str) -> datetime | None:
    """Tries to parse a string into a datetime using a given format.

    Args:
        val: The string to parse.
        formt: The format to use for parsing.

    Returns:
        datetime | None: The parsed datetime if the format matches, None otherwise.
    """

    try:
        return datetime.strptime(val, formt).replace(tzinfo=UTC)
    except ValueError:
        return None


def __try_timestamp(val: float) -> datetime | None:
    """Tries to convert a timestamp to a datetime object.

    Args:
        val: The timestamp to convert.

    Returns:
        datetime | None: The parsed datetime if successful, None otherwise.
    """

    try:
        return datetime.fromtimestamp(val, tz=UTC)
    except (ValueError, OverflowError, OSError):
        return None


def __parse_str(val: str) -> datetime | None:
    """Tries to parse a string into a datetime.

    Args:
        val: The string to parse.

    Returns:
        datetime | None: The parsed datetime if successful, None otherwise.
    """

    normalized = val.replace("Z", "+00:00")

    try:
        date = datetime.fromisoformat(normalized)
        if date.tzinfo is None:
            return date.replace(tzinfo=UTC)
        return date.astimezone(UTC)
    except ValueError:
        pass  # Fall back to the next parsing attempts

    for formt in DATETIME_FORMATS:
        parsed = __try_strptime(val, formt)
        if parsed is not None:
            return parsed

    try:
        ts = float(val)
    except ValueError:
        return None

    return __try_timestamp(ts)


def parse_datetime(value: str | int | float | datetime | None) -> datetime | None:
    """Parses a value into a datetime.

    Args:
        value: The value to parse.

    Returns:
        datetime | None: The parsed datetime if successful, None otherwise.
    """

    if value is None or value == "":
        return None

    if isinstance(value, str) and value.strip().lower() == "never":
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    if isinstance(value, (int, float)):
        return __try_timestamp(value)

    if isinstance(value, str):
        result = __parse_str(value.strip())
        if result is None:
            logger.warning("Unable to parse datetime value: %s", value)
        return result

    return None


def format_datetime(value: datetime | str | None) -> str:
    """Formats a date into a string for display.

    Returns 'Never' if the date is None or invalid.
    If a string is passed, tries to parse it first.

    Args:
        value: The date to format (datetime, str, or None).

    Returns:
        str: The formatted date or 'Never'.
    """
    if value is None or value == "":
        return "Never"

    if isinstance(value, str):
        # Keep 'Never' if it is already that value
        if value.lower() == "never":
            return "Never"
        # Otherwise try to parse it
        parsed = parse_datetime(value)
        if parsed is None:
            return value  # Return the raw string if we cannot parse it
        value = parsed

    if not isinstance(value, datetime):
        return str(value)

    return value.strftime("%d/%m/%Y %H:%M:%S")


def add_date_to_filename(path: str | Path, date_format: str = "%Y_%m_%d") -> str:
    """Replaces date placeholders in the filename with current UTC date and time values.

    Supported placeholders in the filename (case-insensitive for curly-brace tokens):
        - 'DATE' (legacy): replaced by today's date formatted with `date_format` ('%Y_%m_%d')
        - '{date}': replaced by today's date formatted with `date_format`.
        - '{year}': 4-digit year (e.g. '2026').
        - '{month}': 2-digit month (01-12).
        - '{day}': 2-digit day of month (01-31).
        - '{hour}': 2-digit hour in 24h format (00-23).
        - '{minute}': 2-digit minute (00-59).
        - '{second}': 2-digit second (00-59).
        - '{time}': time formatted as '%H_%M_%S'.

    All curly-brace placeholders are case-insensitive (e.g. '{YEAR}_{MONTH}' or '{year}_{month}').
    Non-recognized placeholders (e.g. '{unknown}') and parent directories are left unchanged.

    Args:
        path: Original file path (e.g. 'outputs/audit_report_DATE.pdf' or
            'outputs/report_{year}_{month}.xlsx').
        date_format: strftime format used for the 'DATE' and '{date}' placeholders.

    Returns:
        str: The path with placeholders replaced, or unchanged if no known
            placeholder is present in the filename.
    """
    p = Path(path)
    filename = p.name

    if not ("DATE" in filename or "{" in filename):
        return str(p)

    now = datetime.now(UTC)

    replacements = {
        "DATE": now.strftime(date_format),
        "{date}": now.strftime(date_format),
        "{year}": now.strftime("%Y"),
        "{month}": now.strftime("%m"),
        "{day}": now.strftime("%d"),
        "{hour}": now.strftime("%H"),
        "{minute}": now.strftime("%M"),
        "{second}": now.strftime("%S"),
        "{time}": now.strftime("%H_%M_%S"),
    }

    new_filename = filename
    for placeholder, replacement_value in replacements.items():
        if placeholder in new_filename:
            new_filename = new_filename.replace(placeholder, replacement_value)
        upper_placeholder = placeholder.upper()
        if upper_placeholder in new_filename:
            new_filename = new_filename.replace(upper_placeholder, replacement_value)

    if new_filename == filename:
        return str(p)

    return str(p.with_name(new_filename))
