"""
Tests for Cape Town event date calculations and fetch functions.

Run with:  pytest test_events.py -v
"""

import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

import city_events as events


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


class TestMinstrelCarnivalDate:
    def test_2026(self):
        assert events.minstrel_carnival_date(2026) == date(2026, 1, 2)

    def test_2027(self):
        assert events.minstrel_carnival_date(2027) == date(2027, 1, 2)

    def test_always_january_2(self):
        for year in range(2025, 2032):
            d = events.minstrel_carnival_date(year)
            assert d.month == 1 and d.day == 2


class TestSonaDate:
    def test_2026(self):
        assert events.sona_date(2026) == date(2026, 2, 12)   # matches actual SONA 2026

    def test_2027(self):
        assert events.sona_date(2027) == date(2027, 2, 11)   # 2nd Thursday of Feb 2027

    def test_always_thursday(self):
        for year in range(2025, 2032):
            assert events.sona_date(year).weekday() == 3

    def test_always_february(self):
        for year in range(2025, 2032):
            assert events.sona_date(year).month == 2

    def test_always_second_week(self):
        for year in range(2025, 2032):
            assert 8 <= events.sona_date(year).day <= 14


class TestNewYearVADate:
    def test_2026(self):
        assert events.new_year_v_and_a_date(2026) == date(2026, 12, 31)

    def test_2027(self):
        assert events.new_year_v_and_a_date(2027) == date(2027, 12, 31)

    def test_always_december_31(self):
        for year in range(2025, 2032):
            d = events.new_year_v_and_a_date(year)
            assert d.month == 12 and d.day == 31


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


class TestSlaveRouteDate:
    def test_2026(self):
        assert events.slave_route_date(2026) == date(2026, 10, 18)  # 3rd Sunday

    def test_2027(self):
        assert events.slave_route_date(2027) == date(2027, 10, 17)

    def test_always_sunday(self):
        for year in range(2025, 2032):
            assert events.slave_route_date(year).weekday() == 6

    def test_always_october(self):
        for year in range(2025, 2032):
            assert events.slave_route_date(year).month == 10

    def test_always_third_week(self):
        for year in range(2025, 2032):
            assert 15 <= events.slave_route_date(year).day <= 21


class TestJazzFestivalDates:
    def test_2026(self):
        assert events.jazz_festival_dates(2026) == (date(2026, 3, 27), date(2026, 3, 28))

    def test_start_always_friday(self):
        for year in range(2025, 2032):
            assert events.jazz_festival_dates(year)[0].weekday() == 4

    def test_starts_in_march(self):
        # The festival opens on the last Friday of March; the Saturday can spill
        # into 1 April in years where that Friday is the 31st (e.g. 2028).
        for year in range(2025, 2032):
            assert events.jazz_festival_dates(year)[0].month == 3

    def test_end_is_day_after_start(self):
        for year in range(2025, 2032):
            start, end = events.jazz_festival_dates(year)
            assert end == start + timedelta(days=1)


class TestAfricaEnergyIndabaDates:
    def test_2026(self):
        assert events.africa_energy_indaba_dates(2026) == (date(2026, 3, 3), date(2026, 3, 5))

    def test_start_always_first_tuesday(self):
        for year in range(2025, 2032):
            start = events.africa_energy_indaba_dates(year)[0]
            assert start.weekday() == 1 and start.day <= 7

    def test_span_is_tue_to_thu(self):
        for year in range(2025, 2032):
            start, end = events.africa_energy_indaba_dates(year)
            assert end == start + timedelta(days=2)


class TestEnlitAfricaDates:
    def test_2026(self):
        assert events.enlit_africa_dates(2026) == (date(2026, 5, 19), date(2026, 5, 21))

    def test_start_always_third_tuesday(self):
        for year in range(2025, 2032):
            start = events.enlit_africa_dates(year)[0]
            assert start.weekday() == 1 and 15 <= start.day <= 21

    def test_always_may(self):
        for year in range(2025, 2032):
            start, end = events.enlit_africa_dates(year)
            assert start.month == 5 and end.month == 5


class TestFameWeekDates:
    def test_2026(self):
        assert events.fame_week_dates(2026) == (date(2026, 10, 28), date(2026, 11, 1))

    def test_start_always_last_wednesday_of_october(self):
        for year in range(2025, 2032):
            start = events.fame_week_dates(year)[0]
            assert start.weekday() == 2 and start.month == 10
            assert (start + timedelta(weeks=1)).month != 10  # no later Wed in Oct

    def test_span_is_five_days(self):
        for year in range(2025, 2032):
            start, end = events.fame_week_dates(year)
            assert end == start + timedelta(days=4)


# ── Fetch function structure (network mocked out) ─────────────────────────────

CALCULATED_FETCHERS = [
    ("fetch_cycle_tour",       "Cape Town Cycle Tour"),
    ("fetch_two_oceans",       "Two Oceans Marathon"),
    ("fetch_gun_run",          "The Gun Run"),
    ("fetch_cape_town_carnival","Cape Town Carnival"),
    ("fetch_cape_town_pride",  "Cape Town Pride Parade"),
    ("fetch_minstrel_carnival","Minstrel Carnival (Kaapse Klopse)"),
    ("fetch_new_year_v_and_a", "V&A Waterfront New Year's Eve"),
    ("fetch_sona",             "State of the Nation Address (SONA)"),
    ("fetch_slave_route",      "Slave Route Challenge"),
    ("fetch_jazz_festival",    "Cape Town International Jazz Festival"),
    ("fetch_africa_energy_indaba", "Africa Energy Indaba"),
    ("fetch_enlit_africa",     "Enlit Africa"),
    ("fetch_fame_week",        "FAME Week Africa"),
]

# Scrape-only events: no dependable calendar rule, so offline they return a
# name-only dict (and are left off the calendar until a date can be read).
SCRAPE_ONLY_FETCHERS = [
    ("fetch_ct_marathon",      "Sanlam Cape Town Marathon"),
    ("fetch_cape_epic",        "Absa Cape Epic"),
    ("fetch_big_walk",         "Cape Town Big Walk"),
    ("fetch_africa_oil_week",  "Africa Oil Week"),
    ("fetch_comic_con",        "Comic Con Cape Town"),
]

ALL_FETCHERS = CALCULATED_FETCHERS + SCRAPE_ONLY_FETCHERS


@pytest.mark.parametrize("fn_name,expected_name", ALL_FETCHERS)
def test_fetch_returns_dict_with_correct_name(fn_name, expected_name):
    with patch("city_events.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    assert isinstance(result, dict)
    assert result["name"] == expected_name


@pytest.mark.parametrize("fn_name,_", CALCULATED_FETCHERS)
def test_calculated_fetchers_always_return_dates(fn_name, _):
    """Events with calendar-rule fallbacks must return dates even with no network."""
    with patch("city_events.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    assert result.get("start_date"), f"{fn_name} returned no start_date"
    assert result.get("end_date"),   f"{fn_name} returned no end_date"


@pytest.mark.parametrize("fn_name,_", CALCULATED_FETCHERS)
def test_calculated_fetchers_return_valid_iso_dates(fn_name, _):
    with patch("city_events.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    date.fromisoformat(result["start_date"])
    date.fromisoformat(result["end_date"])


@pytest.mark.parametrize("fn_name,_", CALCULATED_FETCHERS)
def test_calculated_fetchers_return_unfinished_editions(fn_name, _):
    """The occurrence returned must not already be over.

    The assertion is on the *end* date, not the start: an event that is currently
    running has to stay on the calendar (the merge step only preserves events that
    have finished, so rolling over early would delete it mid-event).
    """
    with patch("city_events.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    end = date.fromisoformat(result["end_date"])
    assert end >= date.today(), f"{fn_name} returned a finished edition ending {end}"


@pytest.mark.parametrize("fn_name,_", CALCULATED_FETCHERS)
def test_end_date_not_before_start_date(fn_name, _):
    with patch("city_events.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    start = date.fromisoformat(result["start_date"])
    end   = date.fromisoformat(result["end_date"])
    assert end >= start


@pytest.mark.parametrize("fn_name,_", SCRAPE_ONLY_FETCHERS)
def test_scrape_only_fetchers_have_no_offline_date(fn_name, _):
    """Scrape-only events must not invent a date when the network is unavailable."""
    with patch("city_events.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    assert "start_date" not in result, f"{fn_name} fabricated a date offline"


# ── Scrape robustness (mock official pages, no live network) ───────────────────
# Every event that scrapes must extract a *future* date from a representative page,
# proving its regex/JSON-LD parsing works. Dates are built relative to today so the
# tests never go stale.

NEXT_YEAR = date.today().year + 1

SCRAPE_SAMPLES = [
    # (fn_name, page_html, expected_start, expected_end)
    ("fetch_ct_marathon",
     f"<p>Race weekend: 23 - 24 May {NEXT_YEAR}</p>", f"{NEXT_YEAR}-05-23", f"{NEXT_YEAR}-05-24"),
    ("fetch_cape_epic",
     f"<h1>March 21 - 28, {NEXT_YEAR}</h1>", f"{NEXT_YEAR}-03-21", f"{NEXT_YEAR}-03-28"),
    ("fetch_slave_route",
     f"<p>The race takes place on 18 October {NEXT_YEAR}.</p>", f"{NEXT_YEAR}-10-18", f"{NEXT_YEAR}-10-18"),
    ("fetch_big_walk",
     f"<p>Big Walk day: 15 March {NEXT_YEAR}</p>", f"{NEXT_YEAR}-03-15", f"{NEXT_YEAR}-03-15"),
    ("fetch_jazz_festival",
     f"<h1>27 - 28 March {NEXT_YEAR}</h1>", f"{NEXT_YEAR}-03-27", f"{NEXT_YEAR}-03-28"),
    ("fetch_africa_oil_week",
     f"<p>Conference: 14 - 17 September {NEXT_YEAR}</p>", f"{NEXT_YEAR}-09-14", f"{NEXT_YEAR}-09-17"),
    ("fetch_africa_energy_indaba",
     f"<p>3 - 5 March {NEXT_YEAR}</p>", f"{NEXT_YEAR}-03-03", f"{NEXT_YEAR}-03-05"),
    ("fetch_enlit_africa",
     f"<p>19 - 21 May {NEXT_YEAR}</p>", f"{NEXT_YEAR}-05-19", f"{NEXT_YEAR}-05-21"),
    ("fetch_comic_con",
     f"<p>See you on 30 April {NEXT_YEAR}</p>", f"{NEXT_YEAR}-04-30", f"{NEXT_YEAR}-04-30"),
    ("fetch_fame_week",
     f"<p>28 October – 1 November {NEXT_YEAR}</p>", f"{NEXT_YEAR}-10-28", f"{NEXT_YEAR}-11-01"),
]


@pytest.mark.parametrize("fn_name,html,exp_start,exp_end", SCRAPE_SAMPLES)
def test_fetcher_scrapes_official_date(fn_name, html, exp_start, exp_end):
    with patch("city_events.safe_get", return_value=html):
        result = getattr(events, fn_name)()
    assert result["start_date"] == exp_start
    assert result["end_date"] == exp_end


def test_scrape_prefers_jsonld_over_stray_text():
    """schema.org Event JSON-LD is trusted ahead of any loose date on the page."""
    html = (
        f'<script type="application/ld+json">'
        f'{{"@type":"Event","startDate":"{NEXT_YEAR}-09-15","endDate":"{NEXT_YEAR}-09-18"}}'
        f'</script><p>Newsletter sent 1 January {NEXT_YEAR}</p>'
    )
    with patch("city_events.safe_get", return_value=html):
        result = events.fetch_africa_oil_week()
    assert result["start_date"] == f"{NEXT_YEAR}-09-15"
    assert result["end_date"] == f"{NEXT_YEAR}-09-18"


def test_scrape_ignores_stale_date_and_uses_calendar_fallback():
    """A past/stale date must be rejected; a calculated fetcher then uses its rule."""
    with patch("city_events.safe_get", return_value="<p>Last held on 5 January 2000</p>"):
        result = events.fetch_jazz_festival()
    start = date.fromisoformat(result["start_date"])
    assert start >= date.today()
    assert start.month == 3  # fell back to the last-Friday-of-March anchor


def test_scrape_only_ignores_stale_date_and_stays_off_calendar():
    """A scrape-only event with only a stale date returns name-only (no fabrication)."""
    with patch("city_events.safe_get", return_value="<p>Archive: 5 January 2000</p>"):
        result = events.fetch_africa_oil_week()
    assert "start_date" not in result


# ── Provenance / health reporting ─────────────────────────────────────────────
# Every record says where its date came from, so a scraper that has quietly
# stopped working (and is coasting on its computed fallback) is detectable.

@pytest.mark.parametrize("fn_name,_", CALCULATED_FETCHERS)
def test_calculated_fetchers_report_computed_offline(fn_name, _):
    with patch("city_events.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    assert result["source"] == events.SOURCE_COMPUTED


@pytest.mark.parametrize("fn_name,_", SCRAPE_ONLY_FETCHERS)
def test_scrape_only_fetchers_report_none_offline(fn_name, _):
    with patch("city_events.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    assert result["source"] == events.SOURCE_NONE


@pytest.mark.parametrize("fn_name,html,exp_start,exp_end", SCRAPE_SAMPLES)
def test_scraped_dates_report_a_scraped_source(fn_name, html, exp_start, exp_end):
    with patch("city_events.safe_get", return_value=html):
        result = getattr(events, fn_name)()
    assert result["source"] in events.SCRAPED_SOURCES


def test_jsonld_hit_is_labelled_jsonld():
    html = (
        f'<script type="application/ld+json">'
        f'{{"@type":"Event","startDate":"{NEXT_YEAR}-09-15","endDate":"{NEXT_YEAR}-09-18"}}'
        f'</script>'
    )
    with patch("city_events.safe_get", return_value=html):
        assert events.fetch_africa_oil_week()["source"] == events.SOURCE_JSONLD


def test_mining_indaba_title_fallback_is_labelled_title():
    """No JSON-LD, but the <title> carries the range — recorded as a title scrape."""
    html = f"<html><title>Mining Indaba | 8-11 February {NEXT_YEAR}</title><body></body></html>"
    with patch("city_events.safe_get", return_value=html):
        result = events.fetch_mining_indaba()
    assert result["source"] == events.SOURCE_TITLE
    assert result["start_date"] == f"{NEXT_YEAR}-02-08"


def test_crashing_extractor_is_reported_not_dropped():
    """A fetcher that raises still produces a record, so health sees the failure."""
    boom = Mock(side_effect=RuntimeError("boom"))
    boom.__name__ = "fetch_cycle_tour"
    with patch.object(events, "EXTRACTORS", [boom]):
        results = events.fetch_all_events()
    crashed = [r for r in results if r["fetcher"] == "fetch_cycle_tour"]
    assert len(crashed) == 1
    assert crashed[0]["source"] == events.SOURCE_NONE
    assert "start_date" not in crashed[0]


def test_every_record_carries_a_source_and_fetcher():
    with patch("city_events.safe_get", return_value=None):
        results = events.fetch_all_events()
    assert results
    for record in results:
        assert record.get("source"), record
        assert record.get("fetcher"), record


# ── Date-rule rollover ────────────────────────────────────────────────────────

def test_next_computed_keeps_an_event_that_is_currently_running():
    """A multi-day event must not roll over to next year while it is in progress."""
    today = date.today()
    rule = lambda year: (date(year, 1, 1), date(year, 12, 31))  # spans all of `year`
    result = events.next_computed("Year Long", "https://example.com/", rule)
    assert result["start_date"] == str(date(today.year, 1, 1))
    assert result["source"] == events.SOURCE_COMPUTED


def test_next_computed_rolls_over_once_the_event_is_over():
    today = date.today()
    yesterday = today - timedelta(days=1)
    rule = lambda year: date(year, yesterday.month, yesterday.day)
    result = events.next_computed("Single Day", "https://example.com/", rule)
    assert date.fromisoformat(result["start_date"]) >= today


def test_next_computed_returns_no_date_outside_its_horizon():
    """No edition inside the horizon must not fabricate one."""
    result = events.next_computed(
        "Never", "https://example.com/", lambda year: date(year - 50, 1, 1)
    )
    assert "start_date" not in result
    assert result["source"] == events.SOURCE_NONE


@contextmanager
def frozen_today(day):
    """Pin city_events' notion of 'today', so rollover tests are deterministic."""
    pinned = type("PinnedDate", (date,), {"today": classmethod(lambda cls: day)})
    with patch.object(events, "date", pinned):
        yield


def test_fetch_site_rejects_an_edition_that_has_already_happened():
    """A page still advertising this year's finished race must not be published.

    is_recent_date() alone accepts the current year, so without the end-date guard
    the Cycle Tour would publish a March date that has already passed instead of
    falling back to next year's rule.
    """
    this_year = date.today().year  # keeps is_recent_date() happy whenever this runs
    september = date(this_year, 9, 17)  # safely after the race
    html = f"<p>Cycle Tour 8 March {this_year}</p>"
    with frozen_today(september), patch("city_events.safe_get", return_value=html):
        result = events.fetch_cycle_tour()
    assert result["source"] == events.SOURCE_COMPUTED
    assert date.fromisoformat(result["end_date"]) >= september


# ── DHL Stadium API pagination (mock network) ─────────────────────────────────
# The stadium API paginates (default 25/page); fetching only page 1 silently drops
# later events (e.g. a full season, or a multi-day booking on page 2).

import generate_dhl_ics as gen


def _fake_response(payload):
    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return payload
    return _R()


def test_stadium_api_follows_all_pages():
    page1 = {"data": [{"id": 1}],
             "meta": {"pagination": {"page": 1, "pageSize": 1, "pageCount": 2, "total": 2}}}
    page2 = {"data": [{"id": 2}],
             "meta": {"pagination": {"page": 2, "pageSize": 1, "pageCount": 2, "total": 2}}}
    seen = []

    def fake_get(url, timeout=None):
        seen.append(url)
        return _fake_response(page2 if "pagination[page]=2" in url else page1)

    with patch("generate_dhl_ics.requests.get", side_effect=fake_get):
        resp = gen.fetch_stadium_api("2025-01-01T00:00:00.000Z", page_size=1)

    assert [d["id"] for d in resp["data"]] == [1, 2]          # both pages merged
    assert any("pagination[page]=2" in u for u in seen)        # page 2 was requested


def test_stadium_api_raises_on_error():
    """A network/API failure must stop the build, not quietly return nothing.

    Returning an empty result here is what let a single failed request publish a
    calendar with every upcoming fixture deleted.
    """
    with patch("generate_dhl_ics.requests.get", side_effect=RuntimeError("network down")):
        with pytest.raises(gen.StadiumApiError):
            gen.fetch_stadium_api("2025-01-01T00:00:00.000Z")


# ── Event model ───────────────────────────────────────────────────────────────

SAST = gen.SAST


def all_day(name, start, days=1, **kw):
    return gen.CalEvent(name, start, start + timedelta(days=days), **kw)


def timed(name, start, hours=2, **kw):
    return gen.CalEvent(name, start, start + timedelta(hours=hours), **kw)


def test_uid_scheme_matches_the_already_published_calendar():
    """UIDs must not change: a new UID is a duplicate in every subscriber's client.

    The expected value is taken from the published dhl_stadium.ics.
    """
    first_thursday = datetime(2027, 3, 4, 16, 0, tzinfo=SAST)
    assert gen.make_uid("First Thursdays", first_thursday) == (
        "67e7f6493c10737b@greenpoint-stadium-scraper"
    )
    assert gen.make_uid("Africa Energy Indaba", date(2027, 3, 2)) == (
        "7a92f8c43ce9ae63@greenpoint-stadium-scraper"
    )


def test_uid_is_keyed_on_the_same_day_however_the_event_is_expressed():
    """Dedupe can turn a timed event into an all-day one, so the two must agree.

    Keying timed events on their UTC date makes them disagree for anything starting
    before 02:00 SAST, and the same event then carries different UIDs depending on
    whether both sources were in range that run.
    """
    midnight = datetime(2026, 9, 12, 0, 0, tzinfo=SAST)  # 2026-09-11 in UTC
    assert gen.make_uid("X", midnight) == gen.make_uid("X", date(2026, 9, 12))


def test_a_midnight_event_is_not_published_twice_when_it_gets_merged():
    stadium = gen.CalEvent("OUTsurance Gun Run", datetime(2026, 9, 12, 0, 0, tzinfo=SAST),
                           datetime(2026, 9, 12, 12, 0, tzinfo=SAST),
                           category=gen.CATEGORY_STADIUM)
    history = gen.stamp_events(
        [all_day("The Gun Run", date(2026, 9, 12), category=gen.CATEGORY_CITY)], []
    )
    merged = gen.merge_events(gen.dedupe_events([stadium]), history)
    assert [event.name for event in merged] == ["The Gun Run"]


def test_every_published_event_uid_matches_the_scheme():
    """The published calendar must satisfy uid == make_uid(name, start).

    merge_events() preserves past events and the API look-back re-fetches recent
    ones, so an event in the file whose UID the scheme no longer reproduces does
    not collide with its own fresh copy — both get published and stay duplicated.
    """
    published = gen.load_existing_events(gen.ICS_PATH)
    assert published, "the published calendar should not be empty"
    stale = [e.name for e in published if e.uid != gen.make_uid(e.name, e.start)]
    assert not stale, f"UIDs no longer reproducible from name + start: {stale}"


def test_a_preserved_event_with_a_stale_uid_is_not_duplicated():
    """Belt and braces: even a hand-edited file must not produce two of one event."""
    yesterday = date.today() - timedelta(days=2)
    stored = gen.stamp_events([all_day("Race", yesterday)], [])
    tampered = [replace(stored[0], uid="hand-edited@example.com")]
    fresh = [all_day("Race", yesterday)]
    assert len(gen.merge_events(fresh, tampered)) == 1


def test_all_day_event_is_past_the_day_after_it_ends():
    """An all-day event's exclusive end is midnight, so date maths is off by a day.

    If is_past() says "not yet past" on the day after the event, the merge step
    will neither preserve it as history nor re-fetch it, and it is lost.
    """
    event = all_day("Race", date(2026, 10, 18))  # runs on the 18th, DTEND the 19th
    during = datetime(2026, 10, 18, 12, 0, tzinfo=SAST)
    after = datetime(2026, 10, 19, 0, 1, tzinfo=SAST)
    assert not gen.is_past(event, during)
    assert gen.is_past(event, after)


def test_description_link_round_trips_without_doubling():
    event = all_day("X", date(2027, 1, 1), description="Blurb.", url="https://e.test/x")
    rendered = gen.render_description(event)
    assert rendered.endswith("More info: https://e.test/x")
    blurb, label = gen.split_description(rendered, event.url)
    assert (blurb, label) == ("Blurb.", "More info")


def test_description_with_only_a_link_round_trips_to_an_empty_blurb():
    event = all_day("X", date(2027, 1, 1), url="https://e.test/x", link_label="Tickets")
    blurb, label = gen.split_description(gen.render_description(event), event.url)
    assert (blurb, label) == ("", "Tickets")


def test_a_label_without_a_link_is_discarded():
    """Otherwise it survives in memory but not through the file, and every rebuild
    would see the event as 'changed' and bump its SEQUENCE."""
    event = all_day("X", date(2027, 1, 1), link_label="Tickets")
    assert event.link_label == gen.DEFAULT_LINK_LABEL


# ── Text normalisation (stable rebuilds) ─────────────────────────────────────
# Anything a rebuild cannot reproduce exactly bumps SEQUENCE and DTSTAMP every
# run: clients re-notify about events that have not moved and CI commits a
# changed file every time. Text is normalised on the way in so an event always
# equals its own published copy.

DRIFTY_TEXT = [
    ("windows line endings", "Line one.\r\nLine two."),
    ("bare carriage return", "Line one.\rLine two."),
    ("surrounding padding", "   Line one.   "),
    ("long enough to fold", "word " * 40),
    ("tabs and unicode", "Caf\u00e9 \u2014 35 000 riders\tR50"),
    ("ical special characters", "Gates open; parking closed, per notice\\route"),
]


@pytest.mark.parametrize("label,text", DRIFTY_TEXT, ids=[label for label, _ in DRIFTY_TEXT])
@pytest.mark.parametrize("field", ["description", "name", "location"])
def test_text_survives_a_round_trip_unchanged(label, text, field):
    kwargs = {"description": "d", "url": "https://e.test/", field: text}
    if field == "name":
        event = gen.CalEvent(start=date(2027, 1, 1), end=date(2027, 1, 2), **kwargs)
    else:
        event = gen.CalEvent("X", date(2027, 1, 1), date(2027, 1, 2), **kwargs)
    stamped = gen.stamp_events([event], [])
    parsed = gen.parse_calendar(gen.build_calendar(stamped).to_ical())
    assert gen.fingerprint(parsed[0]) == gen.fingerprint(stamped[0])


@pytest.mark.parametrize("label", [
    "Tickets: book now",          # the stadium's link text is free-form
    "T" * 70,                     # longer than a label is usually expected to be
    "T" * 300,                    # longer than the parser accepts at all
    "Buy\ntickets",               # a newline would break the link line
])
def test_link_labels_survive_a_round_trip(label):
    event = gen.CalEvent("X", date(2027, 1, 1), date(2027, 1, 2),
                         description="Blurb.", url="https://e.test/", link_label=label)
    stamped = gen.stamp_events([event], [])
    parsed = gen.parse_calendar(gen.build_calendar(stamped).to_ical())
    assert gen.fingerprint(parsed[0]) == gen.fingerprint(stamped[0])


def test_a_blurb_ending_in_someone_elses_link_is_left_alone():
    """Only the link line we appended may be stripped.

    An event with no URL of its own whose blurb happens to end in a link would
    otherwise lose that line permanently on the next republish.
    """
    blurb = "Road closures apply.\n\nCity notice: https://other.test/page"
    assert gen.split_description(blurb, "") == (blurb, gen.DEFAULT_LINK_LABEL)


def test_a_link_line_for_a_different_url_is_left_alone():
    blurb = "Road closures apply.\n\nCity notice: https://other.test/page"
    assert gen.split_description(blurb, "https://ours.test/")[0] == blurb


# ── Calendar round-trip ───────────────────────────────────────────────────────

SAMPLE_EVENTS = [
    all_day("All day", date(2027, 3, 14), description="d", url="https://a.test/",
            location="CBD", category=gen.CATEGORY_CITY),
    timed("Timed", datetime(2027, 3, 14, 16, 0, tzinfo=SAST), description="d",
          url="https://b.test/", link_label="Tickets", category=gen.CATEGORY_STADIUM),
    all_day("No link", date(2027, 4, 1), category=gen.CATEGORY_CITY),
    timed("No description", datetime(2027, 4, 2, 9, 0, tzinfo=SAST),
          category=gen.CATEGORY_STADIUM),
]


def test_calendar_round_trip_preserves_every_field():
    stamped = gen.stamp_events(SAMPLE_EVENTS, [])
    parsed = gen.parse_calendar(gen.build_calendar(stamped).to_ical())
    assert len(parsed) == len(stamped)
    by_uid = {event.uid: event for event in parsed}
    for original in stamped:
        assert gen.fingerprint(by_uid[original.uid]) == gen.fingerprint(original)


def test_calendar_carries_the_metadata_clients_display():
    raw = gen.build_calendar(gen.stamp_events(SAMPLE_EVENTS, [])).to_ical().decode()
    for prop in ("X-WR-CALNAME", "X-WR-CALDESC", "X-WR-TIMEZONE", "METHOD:PUBLISH",
                 "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H",
                 "BEGIN:VTIMEZONE", "TZID:Africa/Johannesburg"):
        assert prop in raw, f"missing {prop}"
    assert raw.count("DTSTAMP:") == len(SAMPLE_EVENTS)  # required by RFC 5545


def test_timed_events_are_published_in_sast_not_utc():
    raw = gen.build_calendar(gen.stamp_events(SAMPLE_EVENTS, [])).to_ical().decode()
    assert "DTSTART;TZID=Africa/Johannesburg:20270314T160000" in raw
    assert "DTSTART;VALUE=DATE:20270314" in raw


def test_rebuilding_unchanged_events_leaves_the_file_identical():
    """A no-op rebuild must not churn DTSTAMP/SEQUENCE, or CI commits noise and
    clients re-notify about events that have not moved."""
    first = gen.stamp_events(SAMPLE_EVENTS, [])
    raw = gen.build_calendar(first).to_ical()
    second = gen.stamp_events(gen.parse_calendar(raw), gen.parse_calendar(raw))
    assert gen.build_calendar(second).to_ical() == raw


def test_a_changed_event_gets_a_new_dtstamp_and_a_bumped_sequence():
    published = gen.stamp_events([SAMPLE_EVENTS[0]], [])
    moved = replace(published[0], location="Sea Point", dtstamp=None, sequence=0)
    restamped = gen.stamp_events([moved], published)
    assert restamped[0].sequence == published[0].sequence + 1
    assert restamped[0].dtstamp != published[0].dtstamp


# ── Merge (history preservation) ──────────────────────────────────────────────

def test_merge_keeps_past_events_and_takes_the_future_from_the_fresh_fetch():
    yesterday = date.today() - timedelta(days=2)
    tomorrow = date.today() + timedelta(days=2)
    history = gen.stamp_events([all_day("Gone by now", yesterday)], [])
    stale_future = gen.stamp_events([all_day("Cancelled", tomorrow)], [])
    fresh = [all_day("Still on", tomorrow)]

    merged = gen.merge_events(fresh, history + stale_future)
    names = {event.name for event in merged}
    assert "Gone by now" in names     # history survives
    assert "Still on" in names        # fresh future published
    assert "Cancelled" not in names   # a withdrawn future event disappears


# ── Deduplication ─────────────────────────────────────────────────────────────

def test_the_same_race_from_two_sources_becomes_one_event():
    """The stadium lists the Gun Run expo under its sponsor name two days before
    the city scraper's race date; subscribers should see one entry, not two."""
    stadium = timed("OUTsurance Gun Run", datetime(2027, 9, 10, 8, 0, tzinfo=SAST),
                    url="https://tickets.test/gr", link_label="Tickets",
                    description="Sponsor copy", category=gen.CATEGORY_STADIUM)
    city = all_day("The Gun Run", date(2027, 9, 12), url="https://gunrun.test/",
                   description="Road closures on the Atlantic seaboard.",
                   category=gen.CATEGORY_CITY)

    merged = gen.dedupe_events([stadium, city])
    assert len(merged) == 1
    event = merged[0]
    assert event.name == "The Gun Run"                       # canonical name
    assert event.start == date(2027, 9, 10)                  # spans both
    assert event.end == date(2027, 9, 13)
    assert event.description == "Road closures on the Atlantic seaboard."
    assert event.url == "https://gunrun.test/"               # curated link wins


def test_consecutive_days_of_one_tournament_collapse_into_one_entry():
    days = [timed("HSBC SVNS Cape Town", datetime(2026, 12, day, 7, 0, tzinfo=SAST))
            for day in (5, 6)]
    merged = gen.dedupe_events(days)
    assert len(merged) == 1
    assert merged[0].start == days[0].start
    assert merged[0].end == days[1].end


def test_a_merged_span_covers_the_last_day_its_members_reach():
    """A timed member occupies the day it ends on; the all-day union must include it.

    Using its end date directly as the exclusive end publishes an event that
    finishes a day early.
    """
    expo = timed("Sanlam Cape Town Marathon Expo", datetime(2027, 5, 22, 9, 0, tzinfo=SAST),
                 hours=79, category=gen.CATEGORY_STADIUM)  # runs to 17:00 on the 25th
    race = all_day("Sanlam Cape Town Marathon", date(2027, 5, 24),
                   category=gen.CATEGORY_CITY)
    merged = gen.dedupe_events([expo, race])
    assert len(merged) == 1
    assert merged[0].start == date(2027, 5, 22)
    assert merged[0].end == date(2027, 5, 26)  # exclusive: covers through the 25th


@pytest.mark.parametrize("event,expected", [
    (all_day("One day", date(2027, 5, 24)), date(2027, 5, 24)),
    (all_day("Three days", date(2027, 5, 24), days=3), date(2027, 5, 26)),
    (timed("Evening", datetime(2027, 5, 24, 19, 0, tzinfo=SAST)), date(2027, 5, 24)),
    (gen.CalEvent("To midnight", datetime(2027, 5, 24, 19, 0, tzinfo=SAST),
                  datetime(2027, 5, 25, 0, 0, tzinfo=SAST)), date(2027, 5, 24)),
])
def test_last_covered_day(event, expected):
    assert gen.last_covered_day(event) == expected


def test_separate_editions_of_the_same_event_are_not_merged():
    """Two First Thursdays a month apart are different events, not duplicates."""
    months = [timed("First Thursdays", datetime(2027, month, 4, 16, 0, tzinfo=SAST))
              for month in (3, 4)]
    assert len(gen.dedupe_events(months)) == 2


def test_different_fixtures_are_left_alone():
    fixtures = [
        timed("DHL Stormers vs Sharks", datetime(2026, 10, 10, 19, 0, tzinfo=SAST)),
        timed("DHL Stormers vs Bristol Bears", datetime(2026, 10, 17, 19, 0, tzinfo=SAST)),
    ]
    assert len(gen.dedupe_events(fixtures)) == 2


# ── Canonical naming ──────────────────────────────────────────────────────────

def test_a_lone_record_still_gets_the_canonical_name():
    """Whether both sources are in range varies run to run, and a name that flips
    is a UID that flips — which puts the same race on the calendar twice."""
    stadium = timed("OUTsurance Gun Run", datetime(2026, 9, 12, 6, 0, tzinfo=SAST),
                    category=gen.CATEGORY_STADIUM)
    assert gen.dedupe_events([stadium])[0].name == "The Gun Run"


def test_a_renamed_record_does_not_duplicate_preserved_history():
    stadium = timed("OUTsurance Gun Run", datetime(2026, 9, 12, 6, 0, tzinfo=SAST),
                    category=gen.CATEGORY_STADIUM)
    history = gen.stamp_events(
        [all_day("The Gun Run", date(2026, 9, 12), category=gen.CATEGORY_CITY)], []
    )
    merged = gen.merge_events(gen.dedupe_events([stadium]), history)
    assert [event.name for event in merged] == ["The Gun Run"]


def test_history_published_under_an_old_name_is_not_duplicated_by_its_fresh_copy():
    """The UID follows the name, so preserved history has to be renamed too.

    Otherwise an event first published under its sponsor name and later re-served
    by the API inside the look-back window appears twice, under both names.
    """
    yesterday = date.today() - timedelta(days=2)
    history = gen.stamp_events(
        [all_day("OUTsurance Gun Run", yesterday, category=gen.CATEGORY_STADIUM)], []
    )
    fresh = gen.dedupe_events(
        [all_day("OUTsurance Gun Run", yesterday, category=gen.CATEGORY_STADIUM)]
    )
    merged = gen.merge_events(fresh, history)
    assert [event.name for event in merged] == ["The Gun Run"]


def test_every_published_event_already_uses_its_canonical_name():
    for event in gen.load_existing_events(gen.ICS_PATH):
        assert gen.canonicalise(event).name == event.name, event.name


def test_an_unaliased_name_is_left_alone():
    fixture = timed("DHL Stormers vs Sharks", datetime(2026, 10, 10, 19, 0, tzinfo=SAST))
    assert gen.dedupe_events([fixture])[0].name == "DHL Stormers vs Sharks"


# ── Malformed input ───────────────────────────────────────────────────────────

def test_a_corrupt_existing_calendar_stops_the_build(tmp_path):
    """Treating it as empty would discard all preserved history and leave the
    shrink guard with nothing to compare against."""
    broken = tmp_path / "broken.ics"
    broken.write_text("BEGIN:VCALENDAR\nthis is not an ics file")
    with pytest.raises(gen.CalendarBuildError, match="could not parse"):
        gen.load_existing_events(str(broken))


def test_a_missing_calendar_is_simply_the_first_run(tmp_path):
    assert gen.load_existing_events(str(tmp_path / "absent.ics")) == []


def test_a_range_crossing_new_year_gets_the_following_year_for_its_end():
    hit = events.generic_date_hunt("Festival runs 31 December - 1 January 2027")
    assert hit == {"start_date": "2027-12-31", "end_date": "2028-01-01"}


def test_an_inverted_range_is_never_published_as_an_invalid_event():
    """DTEND before DTSTART is not a valid event; fall back to the start day."""
    record = {"name": "Broken", "url": "", "start_date": "2027-12-31",
              "end_date": "2027-01-01"}
    published = gen.get_city_events([record])
    assert len(published) == 1
    assert published[0].start == date(2027, 12, 31)
    assert published[0].end == date(2028, 1, 1)


def test_a_naive_api_timestamp_is_read_as_utc_not_local_time():
    """Otherwise the same payload yields different times locally and in CI."""
    assert gen._parse_api_datetime("2026-10-10T17:00:00") == \
        gen._parse_api_datetime("2026-10-10T17:00:00.000Z")


# ── Fail-closed guards ────────────────────────────────────────────────────────

def _published(count, category=gen.CATEGORY_STADIUM):
    base = date.today() + timedelta(days=30)
    return [all_day(f"Event {i}", base + timedelta(days=i), category=category)
            for i in range(count)]


def test_guard_blocks_a_build_with_no_stadium_events():
    city = _published(3, gen.CATEGORY_CITY)
    with pytest.raises(gen.CalendarBuildError, match="stadium fetch produced no events"):
        gen.check_regression([], city, city, [])


def test_guard_blocks_a_build_with_no_city_events():
    stadium = _published(3)
    with pytest.raises(gen.CalendarBuildError, match="city scrapers produced no dated"):
        gen.check_regression(stadium, [], stadium, [])


def test_guard_still_fires_when_only_first_thursdays_survive(tmp_path):
    """First Thursdays come from an unconditional rule, so they are always there.

    Counting them as city events makes the "no city events" guard unreachable: a
    total collapse of all nineteen real scrapers would publish silently.
    """
    with patch.object(events, "EXTRACTORS", []):   # every real scraper dead
        records = events.fetch_all_events()
    assert records, "First Thursdays should still be produced"
    scraped = gen.get_city_events(
        r for r in records if r.get("fetcher") != events.FIRST_THURSDAYS_FETCHER
    )
    stadium = _published(3)
    with pytest.raises(gen.CalendarBuildError, match="city scrapers produced no dated"):
        gen.check_regression(stadium, scraped, stadium, [])


def test_guard_blocks_a_collapse_in_upcoming_events():
    """The exact failure this exists for: the API blips and half the calendar goes."""
    existing = _published(20)
    stadium, city = _published(2), _published(2, gen.CATEGORY_CITY)
    with pytest.raises(gen.CalendarBuildError, match="upcoming events fell from 20 to 4"):
        gen.check_regression(stadium, city, stadium + city, existing)


def test_guard_allows_a_normal_build():
    existing = _published(20)
    stadium, city = _published(15), _published(6, gen.CATEGORY_CITY)
    gen.check_regression(stadium, city, stadium + city, existing)  # must not raise


def test_guard_can_be_overridden_deliberately():
    existing = _published(20)
    stadium, city = _published(1), _published(1, gen.CATEGORY_CITY)
    gen.check_regression(stadium, city, stadium + city, existing, allow_shrink=True)


def test_guard_ignores_past_events_when_comparing():
    """A calendar that is mostly history must not look like a collapse."""
    history = [all_day("Old", date.today() - timedelta(days=d)) for d in range(30, 60)]
    stadium, city = _published(3), _published(3, gen.CATEGORY_CITY)
    gen.check_regression(stadium, city, stadium + city, history)


# ── Staleness detection ───────────────────────────────────────────────────────

def test_stadium_horizon_warns_when_the_feed_stops_reaching_forward():
    """A frozen endpoint still answers; what gives it away is a shrinking horizon."""
    now = datetime(2026, 9, 17, 12, 0, tzinfo=SAST)
    near = [all_day("Last one", date(2026, 9, 25), category=gen.CATEGORY_STADIUM)]
    assert gen.check_stadium_horizon(near, now)


def test_stadium_horizon_is_quiet_for_a_healthy_feed():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=SAST)
    far = [all_day("Next season", date(2027, 4, 1), category=gen.CATEGORY_STADIUM)]
    assert gen.check_stadium_horizon(far, now) is None


# ── Health report ─────────────────────────────────────────────────────────────

def _health(source, last_live, key="fetch_jazz_festival"):
    return {"sources": {key: {"source": source, "last_live": last_live}}}


def test_health_flags_a_scraper_that_fell_back_to_its_calendar_rule():
    degradations = gen.find_degradations(_health("computed", "2027-01-05"))
    assert len(degradations) == 1
    assert "has not read a live date since 2027-01-05" in degradations[0]


def test_health_flags_a_scraper_that_lost_its_date_entirely():
    degradations = gen.find_degradations(_health("none", "2027-01-05", "fetch_big_walk"))
    assert len(degradations) == 1 and "fetch_big_walk" in degradations[0]


def test_health_is_quiet_when_a_scraper_stays_healthy():
    assert gen.find_degradations(_health("jsonld", "2027-02-01")) == []


def test_health_ignores_a_source_that_never_read_a_live_date():
    """Only a *regression* is news; an event with no scrapable date never had one."""
    assert gen.find_degradations(_health("computed", None, "fetch_gun_run")) == []


def test_a_scraper_that_stays_broken_is_reported_on_every_run():
    """The workflow commits the report it just wrote, so comparing each run against
    the previous one would alarm once and then treat broken as the new normal."""
    live = [{"fetcher": "fetch_jazz_festival", "name": "Jazz", "source": "jsonld",
             "start_date": "2027-03-26", "end_date": "2027-03-27"}]
    broken = [{**live[0], "source": "computed"}]

    first = gen.build_health(live, [], [], {})
    assert first["degradations"] == []

    second = gen.build_health(broken, [], [], first)
    third = gen.build_health(broken, [], [], second)   # compares against a degraded report
    assert second["degradations"], "the break must be reported"
    assert third["degradations"] == second["degradations"], "and keep being reported"


def test_a_recovered_scraper_goes_quiet_again():
    live = [{"fetcher": "fetch_jazz_festival", "name": "Jazz", "source": "jsonld",
             "start_date": "2027-03-26", "end_date": "2027-03-27"}]
    broken = [{**live[0], "source": "computed"}]
    degraded = gen.build_health(broken, [], [], gen.build_health(live, [], [], {}))
    assert gen.build_health(live, [], [], degraded)["degradations"] == []


def test_health_check_exit_status(tmp_path):
    clean = tmp_path / "clean.json"
    clean.write_text(json.dumps({"degradations": []}))
    assert gen.check_health_file(str(clean)) == 0

    dirty = tmp_path / "dirty.json"
    dirty.write_text(json.dumps({"degradations": ["fetch_x: broke"]}))
    assert gen.check_health_file(str(dirty)) == 1


# ── End-to-end build ──────────────────────────────────────────────────────────

def _api_payload(entries):
    return {"data": [{"attributes": {"event": [entry]}} for entry in entries]}


STADIUM_PAYLOAD = _api_payload([
    {"title": "DHL Stormers vs Sharks ", "description": "Match day.",
     "externallink": "https://tickets.test/1", "externallinktext": "Tickets",
     "daterange": [{"start": "2027-10-10T17:00:00.000Z", "end": "2027-10-10T19:00:00.000Z"}]},
    {"title": "Stadium Concert", "description": "", "externallink": "",
     "daterange": [{"start": "2027-11-20T18:00:00.000Z", "end": None}]},
])


def _build(tmp_path, payload=STADIUM_PAYLOAD, **kwargs):
    ics = tmp_path / "out.ics"
    health = tmp_path / "health.json"
    events = tmp_path / "events.json"
    with patch.object(gen, "fetch_stadium_api", return_value=payload), \
            patch("city_events.safe_get", return_value=None):
        report = gen.generate(str(ics), str(health), str(events), **kwargs)
    return ics, health, report


def test_end_to_end_build_writes_a_calendar_and_a_health_report(tmp_path):
    ics, health, report = _build(tmp_path)
    raw = ics.read_bytes()
    events = gen.parse_calendar(raw)
    assert len(events) == report["calendar"]["total"]
    assert any(event.category == gen.CATEGORY_STADIUM for event in events)
    assert any(event.category == gen.CATEGORY_CITY for event in events)
    assert json.loads(health.read_text())["sources"]["fetch_cycle_tour"]["source"] == "computed"


def test_end_to_end_build_is_idempotent(tmp_path):
    ics, _, _ = _build(tmp_path)
    first = ics.read_bytes()
    _build(tmp_path)
    assert ics.read_bytes() == first


def test_a_failed_stadium_fetch_leaves_the_published_file_untouched(tmp_path):
    ics, health, _ = _build(tmp_path)
    before = ics.read_bytes()
    with patch.object(gen, "fetch_stadium_api", return_value={"data": []}), \
         patch("city_events.safe_get", return_value=None):
        with pytest.raises(gen.CalendarBuildError):
            gen.generate(str(ics), str(health), str(tmp_path / "events.json"))
    assert ics.read_bytes() == before


def test_main_reports_a_failed_build_with_a_non_zero_exit_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(gen, "fetch_stadium_api", side_effect=gen.StadiumApiError("down")):
        assert gen.main([]) == 1
