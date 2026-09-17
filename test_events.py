"""
Tests for Cape Town event date calculations and fetch functions.

Run with:  pytest test_events.py -v
"""

import pytest
from datetime import date, timedelta
from unittest.mock import patch

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
def test_calculated_fetchers_return_future_dates(fn_name, _):
    """The next upcoming occurrence should be in the future."""
    with patch("city_events.safe_get", return_value=None):
        result = getattr(events, fn_name)()
    start = date.fromisoformat(result["start_date"])
    assert start >= date.today(), f"{fn_name} returned past date {start}"


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


def test_stadium_api_returns_partial_on_error():
    """A network/API failure must not crash the build — return what we have."""
    with patch("generate_dhl_ics.requests.get", side_effect=RuntimeError("network down")):
        resp = gen.fetch_stadium_api("2025-01-01T00:00:00.000Z")
    assert resp == {"data": []}
