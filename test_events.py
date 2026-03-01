"""
Tests for Cape Town event date calculations and fetch functions.

Run with:  pytest test_events.py -v
"""

import pytest
from datetime import date, timedelta
from unittest.mock import patch

import test as events


# ── nth_weekday_of_month ──────────────────────────────────────────────────────

class TestNthWeekdayOfMonth:
    def test_second_sunday_march_2025(self):
        assert events.nth_weekday_of_month(2025, 3, 2, 6) == date(2025, 3, 9)

    def test_second_sunday_march_2026(self):
        assert events.nth_weekday_of_month(2026, 3, 2, 6) == date(2026, 3, 8)

    def test_second_sunday_september_2025(self):
        assert events.nth_weekday_of_month(2025, 9, 2, 6) == date(2025, 9, 14)

    def test_second_sunday_september_2026(self):
        assert events.nth_weekday_of_month(2026, 9, 2, 6) == date(2026, 9, 13)

    def test_first_occurrence_when_month_starts_on_target_day(self):
        # Jan 1 2026 is a Thursday (weekday=3)
        assert events.nth_weekday_of_month(2026, 1, 1, 3) == date(2026, 1, 1)

    def test_result_weekday_matches_requested(self):
        for weekday in range(7):
            d = events.nth_weekday_of_month(2026, 6, 2, weekday)
            assert d.weekday() == weekday

    def test_nth_is_within_correct_week_band(self):
        # 2nd Sunday must fall on days 8–14
        for year in range(2025, 2030):
            d = events.nth_weekday_of_month(year, 3, 2, 6)
            assert 8 <= d.day <= 14, f"{year}: {d} is outside 2nd-week range"


# ── last_weekday_of_month ─────────────────────────────────────────────────────

class TestLastWeekdayOfMonth:
    def test_last_saturday_february_2025(self):
        assert events.last_weekday_of_month(2025, 2, 5) == date(2025, 2, 22)

    def test_last_saturday_february_2026(self):
        assert events.last_weekday_of_month(2026, 2, 5) == date(2026, 2, 28)

    def test_last_saturday_february_2027(self):
        assert events.last_weekday_of_month(2027, 2, 5) == date(2027, 2, 27)

    def test_result_weekday_matches_requested(self):
        for weekday in range(7):
            d = events.last_weekday_of_month(2026, 3, weekday)
            assert d.weekday() == weekday

    def test_no_later_occurrence_in_same_month(self):
        for year in range(2025, 2030):
            d = events.last_weekday_of_month(year, 2, 5)
            assert (d + timedelta(weeks=1)).month != 2, f"Found a later Saturday in Feb {year}"

    def test_works_for_december(self):
        d = events.last_weekday_of_month(2026, 12, 4)  # last Friday of Dec
        assert d.month == 12
        assert d.year == 2026
        assert d.weekday() == 4


# ── Event date calculation functions ─────────────────────────────────────────

class TestCycleTourDate:
    def test_2025(self):
        assert events.cycle_tour_date(2025) == date(2025, 3, 9)

    def test_2026(self):
        assert events.cycle_tour_date(2026) == date(2026, 3, 8)

    def test_always_sunday(self):
        for year in range(2025, 2032):
            assert events.cycle_tour_date(year).weekday() == 6

    def test_always_march(self):
        for year in range(2025, 2032):
            assert events.cycle_tour_date(year).month == 3

    def test_always_second_week(self):
        for year in range(2025, 2032):
            assert 8 <= events.cycle_tour_date(year).day <= 14


class TestGunRunDate:
    def test_2025(self):
        assert events.gun_run_date(2025) == date(2025, 9, 14)

    def test_2026(self):
        assert events.gun_run_date(2026) == date(2026, 9, 13)

    def test_always_sunday(self):
        for year in range(2025, 2032):
            assert events.gun_run_date(year).weekday() == 6

    def test_always_september(self):
        for year in range(2025, 2032):
            assert events.gun_run_date(year).month == 9

    def test_always_second_week(self):
        for year in range(2025, 2032):
            assert 8 <= events.gun_run_date(year).day <= 14


class TestCarnivalDate:
    def test_2025(self):
        assert events.carnival_date(2025) == date(2025, 3, 15)

    def test_2026(self):
        assert events.carnival_date(2026) == date(2026, 3, 14)

    def test_always_saturday(self):
        for year in range(2025, 2032):
            assert events.carnival_date(year).weekday() == 5

    def test_always_day_after_cycle_tour_saturday(self):
        # Carnival is 6 days after the Cycle Tour (Sunday → following Saturday)
        for year in range(2025, 2032):
            assert events.carnival_date(year) == events.cycle_tour_date(year) + timedelta(days=6)

    def test_always_march(self):
        for year in range(2025, 2032):
            assert events.carnival_date(year).month == 3


class TestPrideDate:
    def test_2025(self):
        assert events.pride_date(2025) == date(2025, 2, 22)

    def test_2026(self):
        assert events.pride_date(2026) == date(2026, 2, 28)

    def test_2027(self):
        assert events.pride_date(2027) == date(2027, 2, 27)

    def test_always_saturday(self):
        for year in range(2025, 2032):
            assert events.pride_date(year).weekday() == 5

    def test_always_february(self):
        for year in range(2025, 2032):
            assert events.pride_date(year).month == 2

    def test_no_later_saturday_in_february(self):
        for year in range(2025, 2032):
            d = events.pride_date(year)
            assert (d + timedelta(weeks=1)).month != 2


class TestTwoOceansDates:
    def test_2025_start_is_easter_saturday(self):
        # Easter Sunday 2025 = April 20
        assert events.two_oceans_start_date(2025) == date(2025, 4, 19)

    def test_2025_end_is_easter_sunday(self):
        assert events.two_oceans_end_date(2025) == date(2025, 4, 20)

    def test_2026_start_is_easter_saturday(self):
        # Easter Sunday 2026 = April 5
        assert events.two_oceans_start_date(2026) == date(2026, 4, 4)

    def test_start_is_always_saturday(self):
        for year in range(2025, 2032):
            assert events.two_oceans_start_date(year).weekday() == 5

    def test_end_is_always_sunday(self):
        for year in range(2025, 2032):
            assert events.two_oceans_end_date(year).weekday() == 6

    def test_end_is_day_after_start(self):
        for year in range(2025, 2032):
            assert events.two_oceans_end_date(year) == events.two_oceans_start_date(year) + timedelta(days=1)


# ── Fetch function structure (network mocked out) ─────────────────────────────

CALCULATED_FETCHERS = [
    ("fetch_cycle_tour",       "Cape Town Cycle Tour"),
    ("fetch_two_oceans",       "Two Oceans Marathon"),
    ("fetch_gun_run",          "The Gun Run"),
    ("fetch_cape_town_carnival","Cape Town Carnival"),
    ("fetch_cape_town_pride",  "Cape Town Pride Parade"),
]

ALL_FETCHERS = CALCULATED_FETCHERS + [
    ("fetch_ct_marathon",      "Sanlam Cape Town Marathon"),
    ("fetch_cape_epic",        "Absa Cape Epic"),
    ("fetch_knysna_cycle_tour","Knysna Cycle Tour"),
]


@pytest.mark.parametrize("fn_name,expected_name", ALL_FETCHERS)
def test_fetch_returns_dict_with_correct_name(fn_name, expected_name):
    with patch("test.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    assert isinstance(result, dict)
    assert result["name"] == expected_name


@pytest.mark.parametrize("fn_name,_", CALCULATED_FETCHERS)
def test_calculated_fetchers_always_return_dates(fn_name, _):
    """Events with calendar-rule fallbacks must return dates even with no network."""
    with patch("test.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    assert result.get("start_date"), f"{fn_name} returned no start_date"
    assert result.get("end_date"),   f"{fn_name} returned no end_date"


@pytest.mark.parametrize("fn_name,_", CALCULATED_FETCHERS)
def test_calculated_fetchers_return_valid_iso_dates(fn_name, _):
    with patch("test.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    date.fromisoformat(result["start_date"])
    date.fromisoformat(result["end_date"])


@pytest.mark.parametrize("fn_name,_", CALCULATED_FETCHERS)
def test_calculated_fetchers_return_future_dates(fn_name, _):
    """The next upcoming occurrence should be in the future."""
    with patch("test.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    start = date.fromisoformat(result["start_date"])
    assert start >= date.today(), f"{fn_name} returned past date {start}"


@pytest.mark.parametrize("fn_name,_", CALCULATED_FETCHERS)
def test_end_date_not_before_start_date(fn_name, _):
    with patch("test.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    start = date.fromisoformat(result["start_date"])
    end   = date.fromisoformat(result["end_date"])
    assert end >= start
