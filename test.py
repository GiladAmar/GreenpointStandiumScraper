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
- Knysna Cycle Tour

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
from typing import Dict, List, Optional, Pattern

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dateutil.easter import easter as _easter_sunday

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

def two_oceans_start_date(year: int) -> date:
    """Two Oceans Ultra: Easter Saturday."""
    return _easter_sunday(year) - timedelta(days=1)

def two_oceans_end_date(year: int) -> date:
    """Two Oceans Half: Easter Sunday."""
    return _easter_sunday(year)

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

def try_patterns(text: str, patterns: List[Pattern]) -> Optional[Dict[str, str]]:
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

def generic_date_hunt(text: str) -> Optional[Dict[str, str]]:
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

def fetch_site(name: str, url: str, site_patterns: Optional[List[Pattern]] = None) -> Optional[Dict[str, str]]:
    """Fetch a site, extract visible text, and find the event date."""
    html = safe_get(url)
    if not html:
        return {"name": name, "url": url}
    text = html_to_text(html)

    # Try site-specific patterns first
    if site_patterns:
        hit = try_patterns(text, site_patterns)
        if hit:
            return {"name": name, "url": url, **hit}

    # Fallback to generic
    hit = generic_date_hunt(text)
    if hit:
        return {"name": name, "url": url, **hit}

    logging.warning(f"No valid dates found for {name}")
    return {"name": name, "url": url}

def fetch_cycle_tour() -> Optional[Dict[str, str]]:
    name = "Cape Town Cycle Tour"
    url = "https://www.capetowncycletour.com/"
    patterns = [
        re.compile(rf"(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*{SEP_REGEX}\s*(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>Mar(?:ch)?)\s*,?\s*(?P<year>20\d{{2}})", re.IGNORECASE),
        re.compile(r"(?P<d1>\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>Mar(?:ch)?)\s*,?\s*(?P<year>20\d{2})", re.IGNORECASE),
    ]
    result = fetch_site(name, url, patterns)
    if result and result.get("start_date"):
        return result
    # Fallback: 2nd Sunday of March
    today = date.today()
    for year in range(today.year, today.year + 2):
        d = cycle_tour_date(year)
        if d >= today:
            return {"name": name, "url": url, "start_date": str(d), "end_date": str(d)}
    return {"name": name, "url": url}

def fetch_two_oceans() -> Optional[Dict[str, str]]:
    """
    Two Oceans Marathon: Easter Saturday (Ultra) → Easter Sunday (Half).
    The website is not reliably scrapable, so we calculate from Easter.
    """
    name = "Two Oceans Marathon"
    url = "https://www.twooceansmarathon.org.za/"
    today = date.today()
    for year in range(today.year, today.year + 2):
        start = two_oceans_start_date(year)
        end = two_oceans_end_date(year)
        if start >= today:
            return {"name": name, "url": url, "start_date": str(start), "end_date": str(end)}
    return {"name": name, "url": url}

def fetch_ct_marathon() -> Optional[Dict[str, str]]:
    patterns = [
        re.compile(rf"(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*{SEP_REGEX}\s*(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>Oct(?:ober)?)\s*,?\s*(?P<year>20\d{{2}})", re.IGNORECASE),
    ]
    return fetch_site("Sanlam Cape Town Marathon", "https://www.capetownmarathon.com/", patterns)

def fetch_cape_epic() -> Optional[Dict[str, str]]:
    patterns = [
        re.compile(rf"(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*{SEP_REGEX}\s*(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>Mar(?:ch)?)\s*,?\s*(?P<year>20\d{{2}})", re.IGNORECASE),
    ]
    return fetch_site("Absa Cape Epic", "https://www.cape-epic.com/", patterns)

def fetch_gun_run() -> Optional[Dict[str, str]]:
    # 2nd Sunday of September
    # Source: https://thegunrun.co.za/
    name = "The Gun Run"
    url = "https://thegunrun.co.za/"
    today = date.today()
    for year in range(today.year, today.year + 2):
        d = gun_run_date(year)
        if d >= today:
            return {"name": name, "url": url, "start_date": str(d), "end_date": str(d)}
    return {"name": name, "url": url}

def fetch_cape_town_carnival() -> Optional[Dict[str, str]]:
    # Saturday after the Cycle Tour (Cycle Tour Sunday + 6 days)
    # Source: https://capetowncarnival.com/
    name = "Cape Town Carnival"
    url = "https://capetowncarnival.com/"
    today = date.today()
    for year in range(today.year, today.year + 2):
        d = carnival_date(year)
        if d >= today:
            return {"name": name, "url": url, "start_date": str(d), "end_date": str(d)}
    return {"name": name, "url": url}

def fetch_cape_town_pride() -> Optional[Dict[str, str]]:
    # Last Saturday of February each year
    # Source: https://cptpride.org/
    name = "Cape Town Pride Parade"
    url = "https://cptpride.org/"
    today = date.today()
    for year in range(today.year, today.year + 2):
        d = pride_date(year)
        if d >= today:
            return {"name": name, "url": url, "start_date": str(d), "end_date": str(d)}
    return {"name": name, "url": url}

def fetch_knysna_cycle_tour() -> Optional[Dict[str, str]]:
    patterns = [
        re.compile(rf"(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*(?P<mon1>June?)\s*{SEP_REGEX}\s*(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s*(?P<mon2>July?)\s*,?\s*(?P<year>20\d{{2}})", re.IGNORECASE),
    ]
    return fetch_site("Knysna Cycle Tour", "https://knysnacycle.co.za/", patterns)

def get_first_thursdays(year: int) -> List[Dict[str, str]]:
    """Return a list of 'First Thursdays' events for each month in the given year."""
    events = []
    for month in range(1, 13):
        # Find the first day of the month
        dt = datetime(year, month, 1)
        # Find the first Thursday (weekday 3)
        while dt.weekday() != 3:
            dt += timedelta(days=1)
        start_dt = datetime.combine(dt.date(), time(16, 0))
        end_dt = datetime.combine(dt.date(), time(23, 0))
        events.append({
            "name": "First Thursdays",
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
            "url": "https://first-thursdays.co.za/"
        })
    return events

# ------------------------------------------------------------
# Runner
# ------------------------------------------------------------

def fetch_all_events() -> List[Dict[str, str]]:
    extractors = [
        fetch_cycle_tour,
        fetch_two_oceans,
        fetch_ct_marathon,
        fetch_cape_epic,
        fetch_gun_run,
        fetch_cape_town_carnival,
        fetch_cape_town_pride,
        fetch_knysna_cycle_tour,
    ]
    results: List[Dict[str, str]] = []
    for fn in extractors:
        try:
            data = fn()
            if data:
                logging.info(f"{data['name']}: {data.get('start_date')} – {data.get('end_date')}")
                results.append(data)
        except Exception as e:
            logging.error(f"Extractor error in {fn.__name__}: {e}")
    # Add First Thursdays events for this year and next year
    now = datetime.now().year
    results.extend(get_first_thursdays(now))
    results.extend(get_first_thursdays(now + 1))
    return results

def main() -> None:
    events = fetch_all_events()
    out = {"updated": datetime.now(timezone.utc).isoformat(), "events": events}
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    logging.info(f"Saved {len(events)} events to events.json")

if __name__ == "__main__":
    main()