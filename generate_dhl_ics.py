import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from test import fetch_all_events
from typing import Any, List

import requests
from dateutil import parser as date_parser
from ics import Calendar, Event

SAST = ZoneInfo("Africa/Johannesburg")
ICS_PATH = "dhl_stadium.ics"

# Query the stadium API from a rolling look-back window rather than a fixed date.
# Past events are preserved via merge_events() (see below), so the API only needs
# to supply recent + upcoming events; a small look-back keeps just-passed events
# fresh even if a scheduled run was missed.
API_FLOOR = (datetime.now(timezone.utc) - timedelta(days=60)).strftime(
    "%Y-%m-%dT%H:%M:%S.000Z"
)


def fetch_stadium_api(floor: str, page_size: int = 100) -> dict:
    """Fetch every page of the stadium events API and merge them into one response.

    The API (Strapi) paginates and defaults to a page size of 25, so a single
    request silently drops any events beyond the first page — e.g. a full season
    of fixtures, or a multi-day booking like 'We Are Africa'. We follow
    ``meta.pagination.pageCount`` and concatenate every page's ``data``.

    On any network/parse error we log and return whatever was gathered (possibly
    empty) instead of crashing the whole build — merge_events() then preserves the
    previously published calendar rather than wiping it.
    """
    # The stadium site moved to api.dhlstadium.co.za; the old
    # content-dhlstadium.azurewebsites.net endpoint is frozen (last event Aug 2026)
    # and misses newer fixtures. Same Strapi shape, so get_api_events() is unchanged.
    base = (
        "https://api.dhlstadium.co.za/api/events?"
        f"filters[event][daterange][start][$gte]={floor}"
        "&populate[0]=event.image&populate[1]=event.daterange&populate[2]=thumbnail"
    )
    all_data: list = []
    page = 1
    try:
        while True:
            r = requests.get(
                f"{base}&pagination[page]={page}&pagination[pageSize]={page_size}",
                timeout=30,
            )
            r.raise_for_status()
            payload = r.json()
            all_data.extend(payload.get("data", []))
            pagination = payload.get("meta", {}).get("pagination", {}) or {}
            if page >= (pagination.get("pageCount") or 1):
                break
            page += 1
    except Exception as e:
        print(f"Warning: stadium API fetch failed on page {page}: {e}")
    return {"data": all_data}


def apply_link(event: Event, link: str, description: str = "", label: str = "More info") -> None:
    """Attach a source link to an event two ways for maximum client support.

    - Sets the iCal ``URL`` property, which calendar clients render as a
      clickable link.
    - Appends the same link to the description text, so clients that ignore
      ``URL`` still show it inline.
    """
    description = (description or "").strip()
    link = (link or "").strip()
    if not link:
        event.description = description
        return
    event.url = link
    link_line = f"{label}: {link}"
    event.description = f"{description}\n\n{link_line}".strip() if description else link_line


def add_first_thursdays(years: List[int]) -> List[Event]:
    """
    Generate 'First Thursdays' events for each month in the given years.
    Args:
        years (List[int]): List of years to generate events for.
    Returns:
        List[Event]: List of Event objects for First Thursdays.
    """
    events: List[Event] = []
    for year in years:
        for month in range(1, 13):
            dt = datetime(year, month, 1)
            while dt.weekday() != 3:
                dt += timedelta(days=1)
            start_dt = dt.replace(hour=16, minute=0, second=0, tzinfo=SAST)
            end_dt = dt.replace(hour=23, minute=0, second=0, tzinfo=SAST)
            event = Event()
            event.name = "First Thursdays"
            event.begin = start_dt
            event.end = end_dt
            apply_link(
                event,
                "https://first-thursdays.co.za/",
                "Monthly art-and-culture evening — CBD galleries and venues open "
                "late (16:00–23:00), bringing foot traffic and parking pressure to "
                "the city centre.",
            )
            events.append(event)
    return events


def get_api_events(resp: Any) -> List[Event]:
    """
    Extract events from API response and return as a list of Event objects.
    Args:
        resp (Any): API response JSON.
    Returns:
        List[Event]: List of Event objects from API.
    """
    events: List[Event] = []
    for item in resp.get("data", []):
        for ev in item["attributes"]["event"]:
            dateranges = ev.get("daterange", [])
            if not isinstance(dateranges, list):
                continue
            for dr in dateranges:
                if not isinstance(dr, dict):
                    continue
                event = Event()
                start = dr.get("start")
                end = dr.get("end")
                if start:
                    event.begin = start
                if not end or end <= start:
                    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    start_sast = start_dt.astimezone(SAST)
                    event.end = start_sast.replace(hour=23, minute=59, second=59)
                else:
                    event.end = end
                event.name = ev.get("title", "No title")
                # Prefer the event's external link (usually ticket sales); label
                # it with the site's own link text when supplied.
                link = ev.get("externallink") or ""
                label = (ev.get("externallinktext") or "Tickets").strip() or "Tickets"
                apply_link(event, link, ev.get("description", ""), label)
                events.append(event)
    return events


def add_cape_town_events() -> List[Event]:
    """
    Fetch Cape Town major events via test.py scrapers and return as Event objects.

    Events include the major Cape Town races, parades and CTICC conferences that
    drive road closures and congestion around Green Point, the Atlantic seaboard and
    the CBD (see test.EVENT_DESCRIPTIONS for the full, current list).

    Each event carries a short context blurb (from test.EVENT_DESCRIPTIONS)
    describing what it is and how it affects Green Point / seaboard / CBD traffic.

    Returns:
        List[Event]: List of Event objects for Cape Town major events.
    """
    events: List[Event] = []
    try:
        data = fetch_all_events()
        for item in data:
            if not item.get("start_date"):
                continue
            # Skip events with datetime strings (e.g. First Thursdays — added separately)
            if "T" in item["start_date"]:
                continue
            try:
                event = Event()
                event.name = item["name"]
                apply_link(event, item.get("url", ""), item.get("description", ""))
                start = datetime.strptime(item["start_date"], "%Y-%m-%d")
                end = datetime.strptime(
                    item.get("end_date", item["start_date"]), "%Y-%m-%d"
                )
                event.begin = start
                event.end = end + timedelta(days=1)  # exclusive end per iCal VALUE=DATE convention
                event.make_all_day()
                if item.get("location"):
                    event.location = item["location"]
                events.append(event)
            except Exception as e:
                print(f"Warning: Skipping event '{item.get('name')}': {e}")
    except Exception as e:
        print(f"Warning: Failed to fetch Cape Town events: {e}")
    return events


def _coerce_dt(value: Any) -> datetime:
    """Best-effort convert an ics/string/datetime value to a datetime."""
    if hasattr(value, "datetime"):  # ics/Arrow object
        return value.datetime
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date_parser.parse(value)
        except Exception:
            return datetime.max
    return datetime.max


def get_event_start_dt(event: Event) -> datetime:
    """Return the event's start datetime as a datetime object."""
    return _coerce_dt(event.begin)


def get_event_end_dt(event: Event) -> datetime:
    """Return the event's end datetime as a datetime object."""
    return _coerce_dt(event.end)


def make_uid(event: Event) -> str:
    """Deterministic UID from the event's name + start date.

    Stable across runs so calendar clients update events in place instead of
    treating each regeneration as a brand-new set of events. Two events that
    share a name (e.g. recurring fixtures, First Thursdays) stay distinct
    because the start date is part of the key.
    """
    start = get_event_start_dt(event)
    key = f"{event.name}|{start.date().isoformat()}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return f"{digest}@greenpoint-stadium-scraper"


def is_past(event: Event) -> bool:
    """True once the event has finished (end date before today)."""
    return get_event_end_dt(event).date() < date.today()


def load_existing_events(path: str) -> List[Event]:
    """Load events from a previously published .ics, if present."""
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return list(Calendar(f.read()).events)
    except Exception as e:
        print(f"Warning: could not parse existing {path}: {e}")
        return []


def merge_events(fresh: List[Event], existing: List[Event]) -> List[Event]:
    """Combine freshly fetched events with the previously published calendar.

    Freeze rule:
      - Past events (already finished) are preserved from the existing file so
        history survives even after the stadium API stops returning them.
      - Future events come only from the fresh fetch, so reschedules and
        cancellations are honoured (no ghost entries for moved fixtures).
    A fresh copy always wins on UID collision, keeping details up to date.
    """
    merged: dict[str, Event] = {}
    # Seed with historical (past) events from the previously published file.
    for ev in existing:
        if is_past(ev):
            ev.uid = make_uid(ev)
            merged[ev.uid] = ev
    # Overlay all fresh events; fresh wins on collision, and adds future events.
    for ev in fresh:
        ev.uid = make_uid(ev)
        merged[ev.uid] = ev
    return list(merged.values())


def main() -> None:
    """Build the calendar from all sources and write it to ICS_PATH."""
    resp = fetch_stadium_api(API_FLOOR)
    now = datetime.now().year
    fresh_events: List[Event] = (
        get_api_events(resp)
        + add_first_thursdays([now, now + 1])
        + add_cape_town_events()
    )
    all_events: List[Event] = merge_events(fresh_events, load_existing_events(ICS_PATH))
    # Sort events by start datetime robustly
    all_events.sort(key=get_event_start_dt)
    cal: Calendar = Calendar()
    for event in all_events:
        cal.events.add(event)
    with open(ICS_PATH, "w") as f:
        f.write(cal.serialize())


if __name__ == "__main__":
    main()
