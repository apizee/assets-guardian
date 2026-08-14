import logging
from datetime import UTC, datetime
from unittest.mock import patch

from assets_guardian.utils.dates import add_date_to_filename, format_datetime, parse_datetime


def test_parse_datetime_iso8601():
    date_str = "2023-10-27T10:00:00Z"
    expected = datetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)
    assert parse_datetime(date_str) == expected


def test_parse_datetime_gitlab():
    date_str = "2023-10-27T10:00:00.000Z"
    expected = datetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)
    assert parse_datetime(date_str) == expected


def test_parse_datetime_simple_date():
    date_str = "2023-10-27"
    expected = datetime(2023, 10, 27, tzinfo=UTC)
    assert parse_datetime(date_str) == expected


def test_parse_datetime_timestamp():
    ts = 1698393600
    expected = datetime.fromtimestamp(1698393600, tz=UTC)
    assert parse_datetime(ts) == expected
    assert parse_datetime(str(ts)) == expected


def test_parse_datetime_invalid():
    assert parse_datetime("invalid-date") is None
    assert parse_datetime(None) is None
    assert parse_datetime("never") is None
    assert parse_datetime("") is None


def test_parse_datetime_already_datetime():
    # Aware datetime
    dt_aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert parse_datetime(dt_aware) == dt_aware

    # Naive datetime
    dt_naive = datetime(2024, 1, 1, 12, 0, 0)  # noqa: DTZ001
    assert parse_datetime(dt_naive) == dt_aware


def test_parse_datetime_unsupported_type():
    assert parse_datetime([2024, 1, 1]) is None


def test_try_timestamp_error():
    # Triggering OverflowError or OSError in __try_timestamp
    # inf triggers OverflowError in fromtimestamp usually
    assert parse_datetime(float("inf")) is None


def test_parse_datetime_logging(caplog):
    with caplog.at_level(logging.WARNING):
        parse_datetime("completely-invalid")
        assert "Unable to parse datetime value" in caplog.text


def test_parse_datetime_from_strptime():
    # Test fallback loop with non-ISO format
    date_str = "2023/10/27"
    expected = datetime(2023, 10, 27, tzinfo=UTC)
    assert parse_datetime(date_str) == expected

    date_str = "27/10/2023"
    assert parse_datetime(date_str) == expected


def test_parse_datetime_never_string_inside_parse_str():
    """The private __parse_str shortcut for the literal string 'never' returns None."""
    # "never" (lowercase) is handled early in parse_datetime, but also in __parse_str
    # Reaching __parse_str with "never" requires a string that passes the outer checks
    assert parse_datetime("  never  ") is None


# ---------------------------------------------------------------------------
# format_datetime
# ---------------------------------------------------------------------------


def test_format_datetime_with_aware_datetime():
    """format_datetime formats a timezone-aware datetime as dd/mm/yyyy HH:MM:SS."""
    dt = datetime(2024, 3, 15, 8, 30, 0, tzinfo=UTC)
    assert format_datetime(dt) == "15/03/2024 08:30:00"


def test_format_datetime_none_returns_never():
    """format_datetime returns 'Never' when the value is None."""
    assert format_datetime(None) == "Never"


def test_format_datetime_empty_string_returns_never():
    """format_datetime returns 'Never' when the value is an empty string."""
    assert format_datetime("") == "Never"


def test_format_datetime_never_string_returns_never():
    """format_datetime returns 'Never' when the string value is 'never' (case-insensitive)."""
    assert format_datetime("never") == "Never"
    assert format_datetime("NEVER") == "Never"


def test_format_datetime_iso_string_parses_and_formats():
    """format_datetime parses an ISO 8601 string and returns the formatted date."""
    result = format_datetime("2024-06-01T12:00:00Z")
    assert result == "01/06/2024 12:00:00"


def test_format_datetime_unparseable_string_returns_raw():
    """format_datetime returns the raw string when the value cannot be parsed as a date."""
    raw = "not-a-date"
    assert format_datetime(raw) == raw


def test_format_datetime_non_datetime_non_string_returns_str():
    """format_datetime converts non-datetime, non-string values to str via fallback."""
    result = format_datetime(42)  # type: ignore[arg-type]
    assert result == "42"


def test_add_date_to_filename_no_placeholder_returns_unchanged():
    """add_date_to_filename returns the path unchanged when the filename has no 'DATE'."""
    result = add_date_to_filename("outputs/audit_report.pdf")

    assert result == "outputs/audit_report.pdf"


def test_add_date_to_filename_replaces_date_placeholder():
    """add_date_to_filename replaces 'DATE' with today's date in the given format."""
    fixed_now = datetime(2026, 7, 22, tzinfo=UTC)

    with patch("assets_guardian.utils.dates.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now

        result = add_date_to_filename("outputs/audit_report_DATE.pdf")

    assert result == "outputs/audit_report_2026_07_22.pdf"
    mock_datetime.now.assert_called_once_with(UTC)
