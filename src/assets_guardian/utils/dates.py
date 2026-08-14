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
    """Replaces the 'DATE' placeholder in the filename with today's date, if present.

    Args:
        path: Original file path (e.g. 'outputs/audit_report_DATE.pdf').
        date_format: strftime format used for the date.

    Returns:
        str: The path with 'DATE' replaced by today's date (e.g.
            'outputs/audit_report_2026_07_08.pdf'), or unchanged if the filename
            has no 'DATE' placeholder (e.g. 'outputs/audit_report.pdf').
    """
    p = Path(path)
    if "DATE" not in p.name:
        return str(p)

    today = datetime.now(UTC).strftime(date_format)
    return str(p.with_name(p.name.replace("DATE", today)))
