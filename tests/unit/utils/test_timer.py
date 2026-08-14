"""Tests for timer utilities: start_timer and end_timer."""

from unittest.mock import patch

from assets_guardian.utils.timer import end_timer, start_timer

MODULE = "assets_guardian.utils.timer"


def test_start_timer_returns_perf_counter_value() -> None:
    with patch(f"{MODULE}.time.perf_counter", return_value=123.45):
        result = start_timer()

    assert result == 123.45


def test_end_timer_logs_seconds_when_under_a_minute(caplog: object) -> None:
    with (
        patch(f"{MODULE}.time.perf_counter", return_value=15.5),
        caplog.at_level("INFO", logger="assets_guardian.utils.timer"),  # type: ignore[attr-defined]
    ):
        end_timer(0.0)

    assert "Completed in 15.5s." in caplog.text  # type: ignore[attr-defined]


def test_end_timer_logs_minutes_and_seconds_when_a_minute_or_more(caplog: object) -> None:
    with (
        patch(f"{MODULE}.time.perf_counter", return_value=190.0),
        caplog.at_level("INFO", logger="assets_guardian.utils.timer"),  # type: ignore[attr-defined]
    ):
        end_timer(10.0)

    assert "Completed in 3m 0.0s." in caplog.text  # type: ignore[attr-defined]
