#!/usr/bin/env python3
"""
Scrapes major recurring Cape Town events that often cause road closures
and extracts their start/end dates.

Events included:
- Cape Town Cycle Tour
- Two Oceans Marathon
- Sanlam Cape Town Marathon
- Absa Cape Epic
- Gun Run
- Cape Town Carnival
- Knysna Cycle Tour
"""

import re
import json
import logging
from datetime import datetime
from typing import Dict, Optional, List
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

session = requests.Session()
session.headers.update({"User-Agent": "CapeTownTrafficEventsBot/1.1"})

# ---------------------------------------------------------------------
def safe_get(url: str) -> Optional[str]:
    """Fetch a URL safely with basic retry and timeout."""
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logging.warning(f"Failed to fetch {url}: {e}")
        return None


def parse_date_range(text: str) -> Optional[Dict[str, str]]:
    """Parse phrases like '13–14 April 2025' or '16 March 2025' into ISO dates."""
    text = text.replace("–", "-").replace("to", "-")
    m = re.search(r"(\d{1,2})\s*[-–]?\s*(\d{0,2})?\s*([A-Za-z]+)\s*(20\d{2})", text)
    if not m:
        return None
    day1, day2, month, year = m.groups()
    day2 = day2 or day1
    try:
        start = date_parser.parse(f"{day1} {month} {year}", fuzzy=True).date()
        end = date_parser.parse(f"{day2} {month} {year}", fuzzy=True).date()
        return {"start_date": str(start), "end_date": str(end)}
    except Exception:
        return None

# ---------------------------------------------------------------------
# Individual event extractors
# ---------------------------------------------------------------------

def fetch_cycle_tour() -> Optional[Dict]:
    url = "https://www.capetowncycletour.com/"
    html = safe_get(url)
    if not html:
        return None
    date_info = parse_date_range(html)
    return {"name": "Cape Town Cycle Tour", "url": url, **(date_info or {})}


def fetch_two_oceans() -> Optional[Dict]:
    url = "https://www.twooceansmarathon.org.za/"
    html = safe_get(url)
    if not html:
        return None
    date_info = parse_date_range(html)
    return {"name": "Two Oceans Marathon", "url": url, **(date_info or {})}


def fetch_ct_marathon() -> Optional[Dict]:
    url = "https://capetownmarathon.com/" # TODO 18 - 19 October 2025
    html = safe_get(url)
    if not html:
        return None
    date_info = parse_date_range(html)
    return {"name": "Sanlam Cape Town Marathon", "url": url, **(date_info or {})}


def fetch_cape_epic() -> Optional[Dict]:
    url = "https://www.cape-epic.com/" # TODO 15–22 Mar, 2026
    html = safe_get(url)
    if not html:
        return None
    date_info = parse_date_range(html)
    return {"name": "Absa Cape Epic", "url": url, **(date_info or {})}

# TODO https://www.outsurance.co.za/gunrun/10km-race/, https://www.outsurance.co.za/gunrun/21km-half-marathon/

def fetch_gun_run() -> Optional[Dict]:
    url = "https://thegunrun.co.za/"
    html = safe_get(url)
    if not html:
        return None
    date_info = parse_date_range(html)
    return {"name": "The Gun Run", "url": url, **(date_info or {})}



def fetch_cape_town_carnival() -> Optional[Dict]:
    url = "https://capetowncarnival.com/"
    html = safe_get(url)
    if not html:
        return None
    date_info = parse_date_range(html)
    return {"name": "Cape Town Carnival", "url": url, **(date_info or {})}


def fetch_knysna_cycle_tour() -> Optional[Dict]:
    url = "https://knysnacycle.co.za/"
    html = safe_get(url)
    if not html:
        return None
    date_info = parse_date_range(html)
    return {"name": "Knysna Cycle Tour", "url": url, **(date_info or {})}

# ---------------------------------------------------------------------
def fetch_all_events() -> List[Dict]:
    extractors = [
        fetch_cycle_tour,
        fetch_two_oceans,
        fetch_ct_marathon,
        fetch_cape_epic,
        fetch_gun_run,
        fetch_cape_town_carnival,
        fetch_knysna_cycle_tour,
    ]
    results: List[Dict] = []
    for fn in extractors:
        try:
            data = fn()
            if data:
                logging.info(f"{data['name']}: {data.get('start_date')} – {data.get('end_date')}")
                results.append(data)
        except Exception as e:
            logging.error(f"Error in {fn.__name__}: {e}")
    return results


def main() -> None:
    events = fetch_all_events()
    out = {
        "updated": datetime.utcnow().isoformat(),
        "events": events,
    }
    with open("events.json", "w") as f:
        json.dump(out, f, indent=2)
    logging.info(f"Saved {len(events)} events to events.json")


if __name__ == "__main__":
    main()