#!/usr/bin/env python3
"""
Cape Town Major Event Date Scraper
----------------------------------

Fetches start/end dates for major recurring Cape Town events that typically
cause traffic disruptions or road closures.

Includes:
- Cape Town Cycle Tour
- Two Oceans Marathon
- Sanlam Cape Town Marathon
- Absa Cape Epic
- The Gun Run
- Cape Town Carnival
- Cape Town Pride Parade
- Minstrel Carnival (Kaapse Klopse)
- V&A Waterfront New Year's Eve
- Investing in African Mining Indaba (CTICC, early February)
- State of the Nation Address (SONA)
- Slave Route Challenge
- Cape Town Big Walk
- Cape Town International Jazz Festival (CTICC)
- Africa Oil Week (CTICC)
- Africa Energy Indaba (CTICC)
- Enlit Africa (CTICC)
- Comic Con Cape Town (CTICC)
- FAME Week Africa (CTICC)

Features:
- Handles '18 - 19 October 2025', '15th of March 2025', 'March 15th, 2025', etc.
- Ignores events from previous years (only keeps this year or next).
- Falls back gracefully to hardcoded dates when scraping fails.
- Outputs events.json with ISO dates.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, time, timezone
from typing import (
    Callable, Dict, List, NotRequired, Optional, Pattern, Tuple, TypedDict, Union,
)

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dateutil.easter import easter as _easter_sunday
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

session = requests.Session()
session.headers.update({"User-Agent": "CapeTownTrafficEventsBot/1.5"})

MONTHS_REGEX = (
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
SEP_REGEX = r"(?:-|–|—|to|until|through|thru)"  # dash or textual range markers

# Provenance markers recorded on every event, so that a scraper silently
# degrading from a live date to a computed guess is visible in the health report
# instead of being masked by the fallback (see CLAUDE.md convention 1).
SOURCE_JSONLD = "jsonld"      # schema.org Event markup on the official page
SOURCE_TITLE = "title"        # the page <title>, which carries the date range
SOURCE_TEXT = "text"          # regex over the page's visible text
SOURCE_COMPUTED = "computed"  # calendar rule; no live date could be read
SOURCE_NONE = "none"          # no date at all — event stays off the calendar

# Dates that came off the live site, as opposed to a rule or nothing at all.
SCRAPED_SOURCES = frozenset({SOURCE_JSONLD, SOURCE_TITLE, SOURCE_TEXT})


class DateHit(TypedDict):
    """The bare date range a scraper pulls off a page, before it becomes a record.

    ``source`` is attached once the caller knows which extractor matched.
    """
    start_date: str
    end_date: str
    source: NotRequired[str]


class EventRecord(TypedDict):
    """One scraped/computed event, the shape ``fetch_all_events()`` yields.

    Only ``name``/``url``/``source`` are always present. ``start_date``/``end_date``
    are absent on a name-only record (no dependable date — deliberately left off the
    calendar). ``fetcher`` and ``description`` are stamped on by ``fetch_all_events``;
    ``error`` appears only when an extractor raised.
    """
    name: str
    url: str
    source: str
    start_date: NotRequired[str]
    end_date: NotRequired[str]
    location: NotRequired[str]
    fetcher: NotRequired[str]
    description: NotRequired[str]
    error: NotRequired[str]


# Short, hard-coded context blurbs keyed by canonical event name. Attached to
# each event so the calendar entry explains what it is and why it affects
# Green Point / seaboard / CBD traffic. Purely descriptive — no scraping needed.
EVENT_DESCRIPTIONS: Dict[str, str] = {
    "Cape Town Cycle Tour":
        "The world's largest timed cycle race (~35 000 riders). Road closures "
        "sweep the CBD, Sea Point, Camps Bay and the Peninsula from early morning.",
    "Two Oceans Marathon":
        "Ultra (56 km) on Easter Saturday and Half (21 km) on Easter Sunday. "
        "Closures through the southern suburbs and the peninsula.",
    "Sanlam Cape Town Marathon":
        "City-centre marathon (IAAF-labelled). Road closures around Green Point, "
        "Sea Point, the CBD and southern suburbs.",
    "Absa Cape Epic":
        "Eight-day mountain-bike stage race across the Western Cape; the start "
        "and finish stages disrupt local traffic.",
    "The Gun Run":
        "Half marathon and 10 km along the Atlantic seaboard. Closures on Green "
        "Point, Sea Point and Mouille Point roads.",
    "Cape Town Carnival":
        "Night-time street parade on the Green Point Fan Walk. Somerset Road and "
        "the surrounding streets close for the evening.",
    "Cape Town Pride Parade":
        "Pride march and festival through Green Point, Sea Point and De Waterkant.",
    "Minstrel Carnival (Kaapse Klopse)":
        "The Cape Town Minstrel Carnival (Kaapse Klopse), a large minstrel festival "
        "held annually on 2 January. The parade moves through the CBD, Bo-Kaap and "
        "Green Point, closing Somerset Road and Green Point Main Road for the day.",
    "V&A Waterfront New Year's Eve":
        "New Year's Eve fireworks and crowds at the V&A Waterfront. Congestion on "
        "Green Point Main Road, Beach Road, Helen Suzman Boulevard and Somerset Road.",
    "Investing in African Mining Indaba":
        "Africa's largest mining investment conference at the CTICC (7 000+ "
        "delegates: ministers, mining houses, financiers). Heavy congestion around "
        "the Foreshore and CBD for the week.",
    "Slave Route Challenge":
        "Heritage road race (21.1 km / 10 km / 5 km) starting at the City Hall on "
        "Darling Street and winding through District Six, the Company's Gardens, "
        "Bo-Kaap, the DHL Stadium and Fort Wynyard. CBD and Green Point road closures "
        "through the morning.",
    "Cape Town Big Walk":
        "Mass-participation charity walk (5–10 km) starting in Green Point and "
        "following the Sea Point Promenade. Atlantic-seaboard road and parking "
        "restrictions through the morning.",
    "Cape Town International Jazz Festival":
        "Africa's largest jazz festival (~35 000 attendees) at the CTICC over a "
        "weekend. Heavy evening congestion and parking pressure around the Foreshore "
        "and CBD.",
    "Africa Oil Week":
        "Major oil-and-gas conference at the CTICC drawing thousands of delegates. "
        "Congestion around the Foreshore and CBD for the week.",
    "Africa Energy Indaba":
        "Energy conference and exhibition at the CTICC (early March). Congestion "
        "around the Foreshore and CBD.",
    "Enlit Africa":
        "Africa's largest power, energy and water conference at the CTICC (May). "
        "Congestion around the Foreshore and CBD.",
    "Comic Con Cape Town":
        "Large pop-culture convention at the CTICC (30 000+ attendees) around the "
        "late-April long weekend. Heavy crowds and parking pressure around the "
        "Foreshore and CBD.",
    "FAME Week Africa":
        "Creative-industries conference and exhibition at the CTICC (late October / "
        "early November). Congestion around the Foreshore and CBD.",
    "First Thursdays":
        "Monthly art-and-culture evening — CBD galleries and venues open late "
        "(16:00–23:00), bringing foot traffic and parking pressure to the city centre.",
    "State of the Nation Address (SONA)":
        "Evening joint sitting of Parliament at the Cape Town City Hall (Grand Parade). "
        "Road closures and a security lockdown around the Darling/Plein/Roeland Street "
        "precinct through the afternoon and evening.",
}

# ------------------------------------------------------------
# Calendar calculation helpers
# ------------------------------------------------------------

def nth_weekday_of_month(year: int, month: int, n: int, weekday: int) -> date:
    """Return the nth occurrence (1-based) of weekday (Mon=0 … Sun=6) in year/month."""
    first = date(year, month, 1)
    days_ahead = weekday - first.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return first + timedelta(days=days_ahead) + timedelta(weeks=n - 1)

def last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of weekday (Mon=0 … Sun=6) in year/month."""
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    days_back = (last.weekday() - weekday) % 7
    return last - timedelta(days=days_back)

def cycle_tour_date(year: int) -> date:
    """Cape Town Cycle Tour: 2nd Sunday of March."""
    return nth_weekday_of_month(year, 3, 2, 6)

def gun_run_date(year: int) -> date:
    """The Gun Run: 2nd Sunday of September."""
    return nth_weekday_of_month(year, 9, 2, 6)

def carnival_date(year: int) -> date:
    """Cape Town Carnival: Saturday after the Cycle Tour (Cycle Tour Sunday + 6 days)."""
    return cycle_tour_date(year) + timedelta(days=6)

def pride_date(year: int) -> date:
    """Cape Town Pride Parade: last Saturday of February."""
    return last_weekday_of_month(year, 2, 5)

def minstrel_carnival_date(year: int) -> date:
    """Cape Town Minstrel Carnival (Kaapse Klopse): 2 January each year.

    The parade moves through the CBD, Bo-Kaap and Green Point, closing
    Somerset Road, Green Point Main Road and surrounds for most of the day.
    """
    return date(year, 1, 2)

def new_year_v_and_a_date(year: int) -> date:
    """V&A Waterfront New Year's Eve celebration: 31 December each year.

    Fireworks and crowds congest Green Point Main Road, Beach Road,
    Helen Suzman Boulevard and Somerset Road through the evening.
    """
    return date(year, 12, 31)

def two_oceans_start_date(year: int) -> date:
    """Two Oceans Ultra: Easter Saturday."""
    return _easter_sunday(year) - timedelta(days=1)

def two_oceans_end_date(year: int) -> date:
    """Two Oceans Half: Easter Sunday."""
    return _easter_sunday(year)

def mining_indaba_dates(year: int) -> tuple[date, date]:
    """Investing in African Mining Indaba: Monday–Thursday of early February.

    Empirically the conference starts on the first Monday of February that
    falls on or after the 3rd (2024: 5–8, 2025: 3–6, 2026: 9–12, 2027: 8–11);
    when the first Monday would land on 1–2 Feb it shifts a week later. It
    draws 7 000+ delegates (ministers, mining houses, financiers) and congests
    the Foreshore/CBD around the CTICC for the week.
    """
    first = date(year, 2, 1)
    monday = first + timedelta(days=(0 - first.weekday()) % 7)  # first Monday
    if monday.day < 3:
        monday += timedelta(days=7)
    return monday, monday + timedelta(days=3)

def sona_date(year: int) -> date:
    """State of the Nation Address: best-guess = 2nd Thursday of February.

    SONA is set by the Presidency and announced each year, but recent editions have
    almost all fallen on the 2nd Thursday of February (2020-2026), the exception being
    2025 (1st Thursday). Election years can add a mid-year post-election SONA. This rule
    is only a placeholder shown in advance; fetch_sona() overrides it with the scraped
    official date once Parliament/gov.za publishes it.
    """
    return nth_weekday_of_month(year, 2, 2, 3)  # 2nd (n=2) Thursday (weekday=3) of Feb

def slave_route_date(year: int) -> date:
    """Slave Route Challenge: best-guess = 3rd Sunday of October.

    Recent editions run in mid-October (2026: Sun 18 Oct); the race has moved dates
    historically (it was previously staged in March), so this is only an anchor that
    fetch_slave_route() overrides with the scraped official date.
    """
    return nth_weekday_of_month(year, 10, 3, 6)  # 3rd Sunday of October

def jazz_festival_dates(year: int) -> tuple[date, date]:
    """Cape Town International Jazz Festival: Fri–Sat of the last weekend of March.

    2026 ran Fri–Sat 27–28 March. The programme has occasionally slipped into early
    April, so this is an anchor that fetch_jazz_festival() overrides when scraped.
    """
    fri = last_weekday_of_month(year, 3, 4)  # last Friday of March
    return fri, fri + timedelta(days=1)       # Fri–Sat

def africa_energy_indaba_dates(year: int) -> tuple[date, date]:
    """Africa Energy Indaba: Tue–Thu of the first week of March (2026: 3–5 March)."""
    tue = nth_weekday_of_month(year, 3, 1, 1)  # first Tuesday of March
    return tue, tue + timedelta(days=2)         # Tue–Thu

def enlit_africa_dates(year: int) -> tuple[date, date]:
    """Enlit Africa: Tue–Thu of the third week of May (2026: 19–21 May)."""
    tue = nth_weekday_of_month(year, 5, 3, 1)  # 3rd Tuesday of May
    return tue, tue + timedelta(days=2)         # Tue–Thu

def fame_week_dates(year: int) -> tuple[date, date]:
    """FAME Week Africa: last Wednesday of October into early November.

    2026 runs Wed–Sun 28 Oct – 1 Nov; anchored on the last Wednesday of October.
    """
    wed = last_weekday_of_month(year, 10, 2)   # last Wednesday of October
    return wed, wed + timedelta(days=4)          # Wed–Sun (into early November)

# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------

def is_recent_date(year: int) -> bool:
    """Return True if the year is this year or next."""
    now = datetime.now().year
    return now <= year <= now + 1

def safe_get(url: str) -> Optional[str]:
    """Fetch URL safely with retries and error handling."""
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logging.warning(f"Failed to fetch {url}: {e}")
        return None

def html_to_text(html: str) -> str:
    """Convert HTML to visible text and normalize whitespace."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()
    text = re.sub(r"\s+", " ", text).strip()
    return text

def parse_iso_date(day: str, month: str, year: str) -> str:
    """Return ISO 'YYYY-MM-DD' string from tokens."""
    # Remove ordinal suffixes like 15th
    day = re.sub(r"(st|nd|rd|th)$", "", day.strip(), flags=re.IGNORECASE)
    dt = date_parser.parse(f"{day} {month} {year}", fuzzy=True).date()
    return str(dt)

def try_patterns(text: str, patterns: List[Pattern]) -> Optional[DateHit]:
    """Try regex patterns with named groups and return ISO start/end dates."""
    for pat in patterns:
        m = pat.search(text)
        if not m:
            continue
        gd = {k: (v or "") for k, v in m.groupdict().items()}
        year = gd.get("year")
        if not year:
            continue
        year_int = int(year)

        if not is_recent_date(year_int):
            # Skip outdated years
            continue

        # Cross-month range e.g. '30 Sep – 1 Oct 2025'
        if gd.get("d1") and gd.get("mon1") and gd.get("d2") and gd.get("mon2"):
            start = parse_iso_date(gd["d1"], gd["mon1"], year)
            end = parse_iso_date(gd["d2"], gd["mon2"], year)
            if end < start:
                # A range that crosses New Year carries a single year, e.g.
                # '31 December - 1 January 2027'; the second date is the year after.
                end = parse_iso_date(gd["d2"], gd["mon2"], str(year_int + 1))
            return {"start_date": start, "end_date": end}

        # Single-month range e.g. '18 - 19 October 2025'
        if gd.get("d1") and gd.get("d2") and gd.get("mon"):
            start = parse_iso_date(gd["d1"], gd["mon"], year)
            end = parse_iso_date(gd["d2"], gd["mon"], year)
            return {"start_date": start, "end_date": end}

        # Single date e.g. '15th of March 2025'
        if gd.get("d1") and gd.get("mon"):
            day = parse_iso_date(gd["d1"], gd["mon"], year)
            return {"start_date": day, "end_date": day}
    return None

def jsonld_event_dates(html: str) -> Optional[DateHit]:
    """Extract ISO start/end dates from a schema.org Event JSON-LD block.

    Prefers structured markup over scraped body text: sites that publish
    schema.org Event data (e.g. miningindaba.com) keep it accurate and
    machine-readable, and it regenerates automatically for each new edition.
    """
    for block in re.findall(
        r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", html, re.S | re.I
    ):
        try:
            data = json.loads(block)
        except Exception:
            continue
        for node in (data if isinstance(data, list) else [data]):
            if not isinstance(node, dict) or node.get("@type") != "Event":
                continue
            start = node.get("startDate")
            if not start:
                continue
            end = node.get("endDate") or start
            return {"start_date": str(start)[:10], "end_date": str(end)[:10]}
    return None

def generic_date_hunt(text: str) -> Optional[DateHit]:
    """Generic fallback for unknown formats, supporting '15th of March 2025'."""
    patterns: List[Pattern] = [
        # Cross-month range: '30 Sep – 1 Oct 2025'
        re.compile(
            rf"(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*(?P<mon1>{MONTHS_REGEX})\s*{SEP_REGEX}\s*"
            rf"(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s*(?P<mon2>{MONTHS_REGEX})\s*,?\s*(?P<year>20\d{{2}})",
            re.IGNORECASE,
        ),
        # Single-month range: '18 - 19 October 2025'
        re.compile(
            rf"(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*{SEP_REGEX}\s*(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>{MONTHS_REGEX})"
            r"\s*,?\s*(?P<year>20\d{2})",
            re.IGNORECASE,
        ),
        # Month-first range: 'October 18–19, 2025'
        re.compile(
            rf"(?P<mon>{MONTHS_REGEX})\s+(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*{SEP_REGEX}\s*(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*(?P<year>20\d{{2}})",
            re.IGNORECASE,
        ),
        # Single day: '15th of March 2025' or 'March 15th, 2025'
        re.compile(
            rf"(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>{MONTHS_REGEX})\s*,?\s*(?P<year>20\d{{2}})",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?P<mon>{MONTHS_REGEX})\s+(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*(?P<year>20\d{{2}})",
            re.IGNORECASE,
        ),
    ]
    return try_patterns(text, patterns)

# ------------------------------------------------------------
# Site-specific extractors
# ------------------------------------------------------------

def _event(
    name: str,
    url: str,
    source: str,
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
    location: Optional[str] = None,
) -> EventRecord:
    """Build one event record in the shape ``fetch_all_events()`` returns.

    ``source`` records where the date came from (see the ``SOURCE_*`` constants).
    It is what lets the health report notice a scraper that has quietly degraded
    to its computed fallback. Omitting ``start`` produces a name-only record,
    which the calendar builder deliberately leaves off the calendar.
    """
    record: EventRecord = {"name": name, "url": url, "source": source}
    if location:
        record["location"] = location
    if start is not None:
        record["start_date"] = str(start)
        record["end_date"] = str(end if end is not None else start)
    return record


def _is_upcoming(hit: DateHit) -> bool:
    """True when a scraped range is a recent edition that has not finished yet.

    Guards against two different mistakes: a stale block advertising a previous
    edition (caught by the recent-year check) and an edition of the current year
    that has already been and gone (caught by the end-date check).
    """
    try:
        return (
            is_recent_date(int(hit["start_date"][:4]))
            and date.fromisoformat(hit["end_date"]) >= date.today()
        )
    except (KeyError, TypeError, ValueError):
        return False


# A rule maps a year to that year's date, or to a (start, end) pair.
DateRule = Callable[[int], Union[date, Tuple[date, date]]]


def next_computed(
    name: str,
    url: str,
    rule: DateRule,
    *,
    location: Optional[str] = None,
    horizon_years: int = 2,
) -> EventRecord:
    """Return the next edition of an event whose date comes from a calendar rule.

    The first edition that has not *finished* wins, so a multi-day event stays on
    the calendar while it is running and only rolls over to next year's dates once
    it is over. (Rolling over on the start date instead would delete a conference
    from the calendar halfway through it, since the merge step only preserves
    events that are already past.) Falls back to a name-only record if no edition
    lands inside the horizon.
    """
    today = date.today()
    for year in range(today.year, today.year + horizon_years):
        computed = rule(year)
        start, end = computed if isinstance(computed, tuple) else (computed, computed)
        if end >= today:
            return _event(
                name, url, SOURCE_COMPUTED, start=start, end=end, location=location
            )
    return _event(name, url, SOURCE_NONE, location=location)


def scrape_event_date(*urls: str) -> Optional[DateHit]:
    """Scrape official page(s) for a single upcoming event date.

    Tries each URL in turn, preferring machine-readable schema.org Event JSON-LD
    and falling back to a generic text date hunt. Only accepts a date that is in a
    recent year (this year or next) and has not already passed — this guards against
    picking up a stale prior edition or an unrelated date elsewhere on the page.
    Returns ``{'start_date', 'end_date', 'source'}`` or ``None`` when nothing valid
    is found.
    """
    for url in urls:
        html = safe_get(url)
        if not html:
            continue
        for source, hit in (
            (SOURCE_JSONLD, jsonld_event_dates(html)),
            (SOURCE_TEXT, generic_date_hunt(html_to_text(html))),
        ):
            if hit and _is_upcoming(hit):
                return {**hit, "source": source}
    return None


def fetch_site(
    name: str, url: str, site_patterns: Optional[List[Pattern]] = None
) -> EventRecord:
    """Fetch a site, extract visible text, and find the event date.

    Site-specific patterns are tried first (they are narrower and less likely to
    match an unrelated date), then the generic hunt. Anything already finished is
    rejected so a caller's calendar-rule fallback takes over instead.
    """
    html = safe_get(url)
    if not html:
        return _event(name, url, SOURCE_NONE)
    text = html_to_text(html)

    candidates = []
    if site_patterns:
        candidates.append(try_patterns(text, site_patterns))
    candidates.append(generic_date_hunt(text))
    for hit in candidates:
        if hit and _is_upcoming(hit):
            return {**_event(name, url, SOURCE_TEXT), **hit}

    logging.warning(f"No valid dates found for {name}")
    return _event(name, url, SOURCE_NONE)


def _scrape_then_rule(
    name: str,
    url: str,
    rule: Optional[DateRule] = None,
    *,
    location: Optional[str] = None,
) -> EventRecord:
    """Scrape the official page, else fall back to ``rule`` (or to no date).

    Passing ``rule=None`` marks a scrape-only event: one with no dependable
    recurrence, which is left off the calendar rather than given an invented date.
    """
    hit = scrape_event_date(url)
    if hit:
        return {**_event(name, url, hit["source"], location=location), **hit}
    if rule is None:
        return _event(name, url, SOURCE_NONE, location=location)
    return next_computed(name, url, rule, location=location)


def fetch_cycle_tour() -> EventRecord:
    """Cape Town Cycle Tour — 2nd Sunday of March; closures across the peninsula."""
    name = "Cape Town Cycle Tour"
    url = "https://www.capetowncycletour.com/"
    patterns = [
        re.compile(rf"(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*{SEP_REGEX}\s*(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>Mar(?:ch)?)\s*,?\s*(?P<year>20\d{{2}})", re.IGNORECASE),
        re.compile(r"(?P<d1>\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>Mar(?:ch)?)\s*,?\s*(?P<year>20\d{2})", re.IGNORECASE),
    ]
    result = fetch_site(name, url, patterns)
    if result.get("start_date"):
        return result
    return next_computed(name, url, cycle_tour_date)


def fetch_two_oceans() -> EventRecord:
    """Two Oceans Marathon: Easter Saturday (Ultra) → Easter Sunday (Half).

    The website is not reliably scrapable, so we calculate from Easter.
    """
    return next_computed(
        "Two Oceans Marathon",
        "https://www.twooceansmarathon.org.za/",
        lambda year: (two_oceans_start_date(year), two_oceans_end_date(year)),
    )


def fetch_ct_marathon() -> EventRecord:
    """Sanlam Cape Town Marathon — links Green Point, the CBD, Sea Point and the
    southern suburbs.

    The race has drifted off its old October slot (2026 ran on 23–24 May), so we no
    longer assume a month: scrape the date robustly (JSON-LD, else any-month text
    hunt), guarded to a recent, still-future edition. There is no reliable calendar
    rule to fall back on, so if the scrape fails the event is left off until it can
    be read again.
    """
    return _scrape_then_rule(
        "Sanlam Cape Town Marathon",
        "https://www.capetownmarathon.com/",
        location="Green Point / Sea Point / CBD / southern suburbs",
    )


def fetch_cape_epic() -> EventRecord:
    """Absa Cape Epic — eight-day MTB stage race; Cape Town start/finish traffic.

    The old cape-epic.com domain now redirects to epic-series.com; we point straight
    at the canonical page and scrape robustly (recent + future guard). There is no
    dependable calendar rule, so it stays off the calendar if the scrape fails.
    """
    return _scrape_then_rule(
        "Absa Cape Epic",
        "https://www.epic-series.com/capeepic",
        location="Western Cape (Cape Town start/finish stages)",
    )


def fetch_gun_run() -> EventRecord:
    """The Gun Run — half marathon and 10 km, 2nd Sunday of September.

    thegunrun.co.za is dead; the race is now the OUTsurance Gun Run.
    """
    return next_computed(
        "The Gun Run", "https://www.outsurance.co.za/gunrun/", gun_run_date
    )


def fetch_cape_town_carnival() -> EventRecord:
    """Cape Town Carnival — Saturday after the Cycle Tour, on the Fan Walk."""
    return next_computed(
        "Cape Town Carnival", "https://capetowncarnival.com/", carnival_date
    )


def fetch_cape_town_pride() -> EventRecord:
    """Cape Town Pride Parade — last Saturday of February."""
    return next_computed("Cape Town Pride Parade", "https://cptpride.org/", pride_date)


def fetch_minstrel_carnival() -> EventRecord:
    """Minstrel Carnival (Kaapse Klopse) — 2 January, CBD / Bo-Kaap / Green Point."""
    return next_computed(
        "Minstrel Carnival (Kaapse Klopse)",
        "https://en.wikipedia.org/wiki/Kaapse_Klopse",
        minstrel_carnival_date,
    )


def fetch_new_year_v_and_a() -> EventRecord:
    """V&A Waterfront New Year's Eve — 31 December fireworks and crowds."""
    return next_computed(
        "V&A Waterfront New Year's Eve",
        "https://www.waterfront.co.za/new-years-eve-celebration",
        new_year_v_and_a_date,
    )


def fetch_mining_indaba() -> EventRecord:
    """Investing in African Mining Indaba — early Feb at the CTICC.

    Draws 7 000+ delegates and congests the Foreshore/CBD for the week.
    Scraped most- to least-reliable:
      1. schema.org Event JSON-LD (machine-readable ISO startDate/endDate).
      2. The <title>, which always carries the range e.g. '8-11 Feb 2027'.
      3. Computed fallback: first Monday of Feb on/after the 3rd, Mon–Thu.
    """
    name = "Investing in African Mining Indaba"
    url = "https://miningindaba.com/"
    html = safe_get(url)
    if html:
        hit = jsonld_event_dates(html)
        # Guard against a stale block for a previous edition.
        if hit and _is_upcoming(hit):
            return {**_event(name, url, SOURCE_JSONLD), **hit}
        # Fallback: parse the <title> range (kept accurate for SEO).
        m = re.search(r"<title>[^<]*</title>", html, re.IGNORECASE)
        if m:
            hit = generic_date_hunt(m.group(0))
            if hit and _is_upcoming(hit):
                return {**_event(name, url, SOURCE_TITLE), **hit}
    # Final fallback: computed recurrence when the site is unreachable.
    logging.warning("Mining Indaba: falling back to computed dates")
    return next_computed(name, url, mining_indaba_dates)


def fetch_sona() -> EventRecord:
    """State of the Nation Address — evening joint sitting at Cape Town City Hall.

    Central-CBD lockdown (Grand Parade / Parliament precinct). The date is announced
    each year; scraped most- to least-reliable, then a computed 2nd-Thursday-of-Feb
    fallback:
      1. parliament.gov.za SONA landing page (stable URL, plain-text date).
      2. gov.za/SONA{year} (predictable per-year URL, plain-text date).
      3. Computed sona_date(year), only accepted when it is still in the future.
    """
    name = "State of the Nation Address (SONA)"
    url = "https://www.parliament.gov.za/state-of-the-nation-address"
    location = "Cape Town City Hall, Darling Street, Cape Town"
    today = date.today()

    # 1 & 2: scrape official pages; accept only a *future* date in a recent year.
    candidates = [url] + [f"https://www.gov.za/SONA{y}" for y in (today.year, today.year + 1)]
    for src in candidates:
        html = safe_get(src)
        if not html:
            continue
        hit = generic_date_hunt(html_to_text(html))
        if hit and _is_upcoming(hit):
            # SONA is a single evening: ignore any end date the page may carry.
            return {
                **_event(name, url, SOURCE_TEXT, location=location),
                "start_date": hit["start_date"],
                "end_date": hit["start_date"],
            }

    # 3: computed fallback — next upcoming 2nd Thursday of February.
    return next_computed(name, url, sona_date, location=location)


def fetch_slave_route() -> EventRecord:
    """Slave Route Challenge — heritage road race from the City Hall through the CBD.

    Scrape the official date (JSON-LD / text), else the 3rd-Sunday-of-October anchor.
    """
    return _scrape_then_rule(
        "Slave Route Challenge",
        "https://www.slaveroute.co.za/",
        slave_route_date,
        location="Cape Town CBD (City Hall, District Six, Bo-Kaap, DHL Stadium)",
    )


def fetch_big_walk() -> EventRecord:
    """Cape Town Big Walk — mass charity walk along the Sea Point Promenade.

    Recent editions have shifted and been postponed, so there is no dependable rule:
    scrape-only, left off the calendar until an official date can be read.
    """
    return _scrape_then_rule(
        "Cape Town Big Walk",
        "https://capetownbigwalk.com/",
        location="Green Point / Sea Point Promenade (Atlantic Seaboard)",
    )


def fetch_jazz_festival() -> EventRecord:
    """Cape Town International Jazz Festival — CTICC, last weekend of March.

    Scrape the official date (JSON-LD / text), else the last-Friday-of-March anchor.
    """
    return _scrape_then_rule(
        "Cape Town International Jazz Festival",
        "https://www.capetownjazzfest.com/",
        jazz_festival_dates,
        location="CTICC, Cape Town CBD",
    )


def fetch_africa_oil_week() -> EventRecord:
    """Africa Oil Week — major oil-and-gas conference at the CTICC.

    The month jumps between September and October year to year, so there is no reliable
    rule: scrape-only, left off the calendar until an official date can be read.

    NOTE: as of the last audit the official domain (africaoilweek.com) refuses
    connections, so this reliably returns name-only and the event does not appear.
    Revisit the URL if the event resurfaces (see also African Energy Week, aecweek.com,
    a separate CTICC energy event).
    """
    return _scrape_then_rule(
        "Africa Oil Week",
        "https://africaoilweek.com/",
        location="CTICC / Cape Town CBD",
    )


def fetch_africa_energy_indaba() -> EventRecord:
    """Africa Energy Indaba — CTICC energy conference, first week of March.

    Scrape the official date (JSON-LD / text), else the first-Tuesday-of-March anchor.
    """
    return _scrape_then_rule(
        "Africa Energy Indaba",
        "https://www.africaenergyindaba.com/",
        africa_energy_indaba_dates,
        location="CTICC, Cape Town CBD",
    )


def fetch_enlit_africa() -> EventRecord:
    """Enlit Africa — CTICC power/energy conference, third week of May.

    Scrape the official date (JSON-LD / text), else the 3rd-Tuesday-of-May anchor.
    """
    return _scrape_then_rule(
        "Enlit Africa",
        "https://wearevuka.com/energy/enlit-africa/",  # enlit-africa.com redirects here
        enlit_africa_dates,
        location="CTICC, Cape Town CBD",
    )


def fetch_comic_con() -> EventRecord:
    """Comic Con Cape Town — large pop-culture convention at the CTICC.

    Held around the late-April long weekend but not every year (the next edition is
    2027), so there is no dependable rule: scrape-only, left off until an official date
    can be read.

    The official site is comicconafrica.co.za; use the Cape Town page specifically —
    the site root defaults to the Johannesburg edition (a different, Sept date).
    """
    return _scrape_then_rule(
        "Comic Con Cape Town",
        "https://comicconafrica.co.za/ccct-home-page/",
        location="CTICC, Cape Town CBD",
    )


def fetch_fame_week() -> EventRecord:
    """FAME Week Africa — CTICC creative-industries conference, late Oct / early Nov.

    Scrape the official date (JSON-LD / text), else the last-Wednesday-of-October anchor.
    """
    return _scrape_then_rule(
        "FAME Week Africa",
        "https://www.fameweekafrica.com/",  # bare domain has an expired cert; www works
        fame_week_dates,
        location="CTICC, Cape Town CBD",
    )


# Named so callers can tell these apart from the scraped events: they come from an
# unconditional rule and are always present, however the real scrapers fare.
FIRST_THURSDAYS_FETCHER = "get_first_thursdays"


def get_first_thursdays(year: int) -> List[EventRecord]:
    """Return a 'First Thursdays' event (16:00–23:00 SAST) for each month of a year.

    These are timed rather than all-day events, so the dates are ISO *datetime*
    strings; the calendar builder keys off the 'T' to tell the two apart.
    """
    events: List[EventRecord] = []
    for month in range(1, 13):
        # Find the first day of the month
        dt = datetime(year, month, 1)
        # Find the first Thursday (weekday 3)
        while dt.weekday() != 3:
            dt += timedelta(days=1)
        start_dt = datetime.combine(dt.date(), time(16, 0), tzinfo=SAST)
        end_dt = datetime.combine(dt.date(), time(23, 0), tzinfo=SAST)
        events.append({
            "name": "First Thursdays",
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
            "url": "https://first-thursdays.co.za/",
            "source": SOURCE_COMPUTED,
        })
    return events

# ------------------------------------------------------------
# Runner
# ------------------------------------------------------------

EXTRACTORS: List[Callable[[], EventRecord]] = [
    fetch_cycle_tour,
    fetch_two_oceans,
    fetch_ct_marathon,
    fetch_cape_epic,
    fetch_gun_run,
    fetch_cape_town_carnival,
    fetch_cape_town_pride,
    fetch_minstrel_carnival,
    fetch_new_year_v_and_a,
    fetch_mining_indaba,
    fetch_sona,
    fetch_slave_route,
    fetch_big_walk,
    fetch_jazz_festival,
    fetch_africa_oil_week,
    fetch_africa_energy_indaba,
    fetch_enlit_africa,
    fetch_comic_con,
    fetch_fame_week,
]


def fetch_all_events() -> List[EventRecord]:
    """Run every extractor and return one record per event.

    Each record carries ``name``, ``url``, ``source`` (provenance) and ``fetcher``
    (the function that produced it, used as a stable key in the health report),
    plus ``start_date``/``end_date`` when a date could be established and
    ``location``/``description`` where known. A record without ``start_date`` is
    deliberate — the calendar builder leaves it off rather than invent a date.

    An extractor that raises still yields a record, so a crashing scraper shows up
    in the health report as a degraded source instead of silently vanishing.
    """
    results: List[EventRecord] = []
    for fn in EXTRACTORS:
        try:
            data = fn()
        except Exception as e:
            logging.error(f"Extractor error in {fn.__name__}: {e}")
            data = {"name": fn.__name__, "url": "", "source": SOURCE_NONE, "error": str(e)}
        if not data:
            continue
        logging.info(
            f"{data['name']} [{data.get('source')}]: "
            f"{data.get('start_date')} – {data.get('end_date')}"
        )
        data["fetcher"] = fn.__name__
        results.append(data)

    # Add First Thursdays events for this year and next year.
    now = datetime.now().year
    for year in (now, now + 1):
        for item in get_first_thursdays(year):
            item["fetcher"] = FIRST_THURSDAYS_FETCHER
            results.append(item)

    # Attach a context blurb to every event (empty string if we have none).
    for item in results:
        item.setdefault("description", EVENT_DESCRIPTIONS.get(item.get("name", ""), ""))
    return results


EVENTS_PATH = "events.json"


def dump_events(events: List[EventRecord], path: str = EVENTS_PATH) -> None:
    """Write the scraped records to JSON.

    Shared with the calendar builder so that the published events.json comes from
    the same scrape as the published calendar, rather than a second run of every
    fetcher that could disagree with it.
    """
    out = {"updated": datetime.now(timezone.utc).isoformat(), "events": events}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")
    logging.info(f"Saved {len(events)} events to {path}")


def main() -> None:
    dump_events(fetch_all_events())

if __name__ == "__main__":
    main()