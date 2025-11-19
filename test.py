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
- Knysna Cycle Tour

Features:
- Handles '18 - 19 October 2025', '15th of March 2025', 'March 15th, 2025', etc.
- Ignores events from previous years (only keeps this year or next).
- Falls back gracefully to generic patterns.
- Outputs events.json with ISO dates.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Pattern

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

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
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
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
        return None
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
    patterns = [
        re.compile(rf"(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*{SEP_REGEX}\s*(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>Mar(?:ch)?)\s*,?\s*(?P<year>20\d{{2}})", re.IGNORECASE),
        re.compile(r"(?P<d1>\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>Mar(?:ch)?)\s*,?\s*(?P<year>20\d{2})", re.IGNORECASE),
    ]
    return fetch_site("Cape Town Cycle Tour", "https://www.capetowncycletour.com/", patterns)

def fetch_two_oceans() -> Optional[Dict[str, str]]:
    patterns = [
        re.compile(rf"(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*{SEP_REGEX}\s*(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>Apr(?:il)?)\s*,?\s*(?P<year>20\d{{2}})", re.IGNORECASE),
    ]
    return fetch_site("Two Oceans Marathon", "https://www.twooceansmarathon.org.za/", patterns)

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
    patterns = [
        re.compile(rf"(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*{SEP_REGEX}\s*(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>Sep(?:t(?:ember)?)?)\s*,?\s*(?P<year>20\d{{2}})", re.IGNORECASE),
    ]
    return fetch_site("The Gun Run", "https://thegunrun.co.za/", patterns) #TODO there are several of these in the year

def fetch_cape_town_carnival() -> Optional[Dict[str, str]]:
    patterns = [
        re.compile(r"(?P<d1>\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?(?P<mon>Mar(?:ch)?)\s*,?\s*(?P<year>20\d{2})", re.IGNORECASE),
    ]
    return fetch_site("Cape Town Carnival", "https://capetowncarnival.com/2025-carnival/", patterns) #TODO fix this hardcoded year

def fetch_knysna_cycle_tour() -> Optional[Dict[str, str]]:
    patterns = [
        re.compile(rf"(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s*(?P<mon1>Jun(?:e)?)\s*{SEP_REGEX}\s*(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s*(?P<mon2>Jul(?:y)?)\s*,?\s*(?P<year>20\d{{2}})", re.IGNORECASE),
    ]
    return fetch_site("Knysna Cycle Tour", "https://knysnacycle.co.za/", patterns)

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
    return results

def main() -> None:
    events = fetch_all_events()
    out = {"updated": datetime.utcnow().isoformat(), "events": events}
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    logging.info(f"Saved {len(events)} events to events.json")

if __name__ == "__main__":
    main()