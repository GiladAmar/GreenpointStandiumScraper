#!/usr/bin/env python3
"""Build ``dhl_stadium.ics`` from the DHL Stadium API and the city-event scrapers.

The published calendar is something people subscribe to, so the build is
deliberately fail-closed: if a source goes missing or shrinks unexpectedly, the
run aborts and leaves the previously published file in place rather than
committing a calendar with half its events deleted. Run with ``--allow-shrink``
to publish anyway once you have confirmed the drop is genuine.

Outputs:
  dhl_stadium.ics  the calendar itself
  health.json      per-source provenance, so a scraper that has quietly
                   degraded to its computed fallback is visible to CI
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Pattern, Tuple, Union
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar, Event, Timezone, vDuration

from city_events import (
    EVENTS_PATH,
    FIRST_THURSDAYS_FETCHER,
    SCRAPED_SOURCES,
    dump_events,
    fetch_all_events,
)

SAST = ZoneInfo("Africa/Johannesburg")
ICS_PATH = "dhl_stadium.ics"
HEALTH_PATH = "health.json"

CALENDAR_NAME = "Cape Town Traffic Events"
CALENDAR_DESCRIPTION = (
    "DHL Stadium fixtures plus the races, parades and CTICC conferences that close "
    "roads around Green Point, Sea Point, the Atlantic seaboard and the CBD."
)
PRODID = "-//GreenpointStadiumScraper//Cape Town Traffic Events//EN"
# Clients are told to re-read the feed twice a day; the file itself is rebuilt on
# the 1st and 15th, so this only bounds how stale a subscriber can be.
REFRESH_INTERVAL = timedelta(hours=12)

STADIUM_API = "https://api.dhlstadium.co.za/api/events"
# How far back the API query reaches. Past events are preserved from the existing
# file, so the API only has to supply recent + upcoming ones; a small look-back
# keeps just-passed events fresh even if a scheduled run was missed.
API_LOOKBACK = timedelta(days=60)

# Where an event came from. Stored in CATEGORIES so it survives a round-trip
# through the published file, which is what lets the regression guard below
# compare like with like across runs.
CATEGORY_STADIUM = "DHL Stadium"
CATEGORY_CITY = "City Event"
KNOWN_CATEGORIES = (CATEGORY_STADIUM, CATEGORY_CITY)

# Which source wins when the same event arrives from more than one place.
CATEGORY_PRIORITY = {CATEGORY_STADIUM: 2, CATEGORY_CITY: 1}

# Guard thresholds. A build that would drop more than this share of the upcoming
# events is treated as a broken source rather than a real cancellation.
MIN_RETAINED_FRACTION = 0.5
# The stadium publishes months ahead; a feed whose newest event is nearly upon us
# has almost certainly frozen or moved host (it has done both before).
MIN_STADIUM_HORIZON = timedelta(days=30)

# Events from different sources that are really the same disruption. The value is
# the name the merged event is published under (and so the key its UID derives
# from), which is why it must stay stable once chosen.
CANONICAL_NAMES: List[Tuple[Pattern, str]] = [
    (re.compile(r"\bgun run\b", re.IGNORECASE), "The Gun Run"),
    (re.compile(r"\bcycle tour\b", re.IGNORECASE), "Cape Town Cycle Tour"),
    (re.compile(r"\btwo oceans\b", re.IGNORECASE), "Two Oceans Marathon"),
    (re.compile(r"\bcape town marathon\b", re.IGNORECASE), "Sanlam Cape Town Marathon"),
]
# Two records for the same event can sit a few days apart (the expo at the stadium
# on the Friday, the race itself on the Sunday). Anything further apart is treated
# as a separate edition.
DUPLICATE_WINDOW = timedelta(days=7)

# A description ends with "<label>: <url>", appended so clients that ignore the
# URL property still show the link. Parsed back off on read so it is not doubled.
# The label is matched non-greedily so one containing ": " (the stadium's own link
# text is free-form) still leaves the URL in the url group.
MAX_LINK_LABEL = 200
LINK_LINE = re.compile(r"(?:\A|\n)[ \t]*(?P<label>[^\n]{1,%d}?): (?P<url>\S+)[ \t]*\Z" % MAX_LINK_LABEL)
DEFAULT_LINK_LABEL = "More info"


def normalise_text(value: str) -> str:
    """Put text into the form a round-trip through the published file returns.

    Writing an ICS rewrites line endings and reading strips surrounding
    whitespace, so a description that has not been through this normalisation
    compares unequal to its own published copy — which would bump its SEQUENCE
    and DTSTAMP on every single rebuild, defeating the stable-rebuild guarantee
    and committing a changed file from every CI run.
    """
    return re.sub(r"\r\n?", "\n", value or "").strip()


def normalise_label(value: str) -> str:
    """Normalise a link label, which has to survive as a single line.

    A label is written into the description as "<label>: <url>", so a newline in
    it would be read back as a different label (or lose the line entirely), and
    one longer than the parser allows would not be recognised at all.
    """
    label = re.sub(r"\s+", " ", value or "").strip()
    return label if 0 < len(label) <= MAX_LINK_LABEL else DEFAULT_LINK_LABEL


class StadiumApiError(RuntimeError):
    """The stadium API could not be read. The build must not continue."""


class CalendarBuildError(RuntimeError):
    """The calendar this run would publish is not safe to publish."""


# ------------------------------------------------------------
# Event model
# ------------------------------------------------------------

@dataclass
class CalEvent:
    """One calendar entry, independent of the iCal library.

    ``start``/``end`` are either both ``date`` (an all-day event, with ``end``
    exclusive per the iCal ``VALUE=DATE`` convention) or both timezone-aware
    ``datetime``. ``description`` holds the blurb *without* the trailing link
    line; the link is rendered in at write time from ``url``/``link_label``.
    """

    name: str
    start: Union[date, datetime]
    end: Union[date, datetime]
    description: str = ""
    url: str = ""
    link_label: str = DEFAULT_LINK_LABEL
    location: str = ""
    category: str = CATEGORY_CITY
    # Assigned at write time, carried over from the previous file when unchanged.
    uid: str = ""
    sequence: int = 0
    dtstamp: Optional[datetime] = None

    def __post_init__(self) -> None:
        # Normalise on the way in, so an event always equals its own published
        # copy and a rebuild that changes nothing really does change nothing.
        self.name = normalise_text(self.name)
        self.description = normalise_text(self.description)
        self.location = normalise_text(self.location)
        # A label with no link to hang off is meaningless, and letting one linger
        # makes an event's fingerprint differ from the same event read back out of
        # the published file (where an absent URL leaves nothing to recover the
        # label from), which would bump its SEQUENCE on every single rebuild.
        self.link_label = normalise_label(self.link_label) if self.url else DEFAULT_LINK_LABEL

    @property
    def all_day(self) -> bool:
        return not isinstance(self.start, datetime)

    @property
    def start_instant(self) -> datetime:
        return _as_instant(self.start)

    @property
    def end_instant(self) -> datetime:
        return _as_instant(self.end)


def _as_instant(value: Union[date, datetime]) -> datetime:
    """Convert a date or datetime to an absolute instant in SAST.

    All-day dates are anchored to midnight SAST; naive datetimes (which the
    sources should not produce, but might) are read as SAST rather than UTC.
    """
    if isinstance(value, datetime):
        return value.astimezone(SAST) if value.tzinfo else value.replace(tzinfo=SAST)
    return datetime(value.year, value.month, value.day, tzinfo=SAST)


def _uid_date(value: Union[date, datetime]) -> date:
    """The date a UID is keyed on.

    Timed events key on their UTC date, which is what the original UID scheme
    used; changing that would hand every existing subscriber a duplicate of every
    event, so it stays as it is.
    """
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=SAST)
        return aware.astimezone(timezone.utc).date()
    return value


def make_uid(name: str, start: Union[date, datetime]) -> str:
    """Deterministic UID from the event's name and start date.

    Stable across runs so calendar clients update events in place instead of
    treating each regeneration as a brand-new set of events. Two events that
    share a name (recurring fixtures, First Thursdays) stay distinct because the
    start date is part of the key.
    """
    key = f"{name}|{_uid_date(start).isoformat()}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return f"{digest}@greenpoint-stadium-scraper"


def fingerprint(event: CalEvent) -> str:
    """Hash of everything a subscriber would see, used to detect real changes.

    Events whose fingerprint is unchanged keep their previous DTSTAMP and
    SEQUENCE, so a rebuild that changes nothing produces an identical file and
    clients are not told to re-notify about events that did not move.
    """
    parts = [
        event.name,
        event.start.isoformat(),
        event.end.isoformat(),
        event.description,
        event.url,
        event.link_label,
        event.location,
        event.category,
    ]
    return hashlib.sha1(json.dumps(parts).encode("utf-8")).hexdigest()


def is_past(event: CalEvent, now: Optional[datetime] = None) -> bool:
    """True once the event has finished.

    Compared on instants rather than dates: an all-day event's exclusive end is
    midnight on the following day, so a date comparison would call it "not yet
    past" for a whole day after it ended — long enough for a rebuild to drop it
    from both the fresh fetch and the preserved history.
    """
    return event.end_instant <= (now or datetime.now(SAST))


# ------------------------------------------------------------
# Descriptions and links
# ------------------------------------------------------------

def render_description(event: CalEvent) -> str:
    """Blurb plus a trailing ``<label>: <url>`` line, for clients ignoring URL."""
    blurb = (event.description or "").strip()
    url = (event.url or "").strip()
    if not url:
        return blurb
    link_line = f"{event.link_label}: {url}"
    return f"{blurb}\n\n{link_line}" if blurb else link_line


def split_description(text: str, url: str) -> Tuple[str, str]:
    """Inverse of render_description: return ``(blurb, link_label)``.

    Without this a read-modify-write cycle would append a second copy of the link
    line every time the file is regenerated.
    """
    text = normalise_text(text)
    match = LINK_LINE.search(text)
    # Only strip a line this event's own URL property accounts for. A blurb that
    # merely ends in some other link is the author's text, not our doing, and
    # removing it would delete it permanently on the next republish.
    if not match or not url or match.group("url") != url:
        return text, DEFAULT_LINK_LABEL
    return text[: match.start()].strip(), match.group("label")


# ------------------------------------------------------------
# DHL Stadium API
# ------------------------------------------------------------

def api_floor(now: Optional[datetime] = None) -> str:
    """The ``$gte`` start filter sent to the stadium API."""
    moment = (now or datetime.now(timezone.utc)) - API_LOOKBACK
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def fetch_stadium_api(floor: str, page_size: int = 100) -> dict:
    """Fetch every page of the stadium events API and merge them into one response.

    The API (Strapi) paginates and defaults to a page size of 25, so a single
    request silently drops any events beyond the first page — e.g. a full season
    of fixtures, or a multi-day booking like 'We Are Africa'. We follow
    ``meta.pagination.pageCount`` and concatenate every page's ``data``.

    Raises ``StadiumApiError`` on any network or parse failure. Swallowing the
    error and returning an empty result would publish a calendar with every
    upcoming fixture deleted, which is worse than not publishing at all.
    """
    # The stadium site moved to api.dhlstadium.co.za; the old
    # content-dhlstadium.azurewebsites.net endpoint is frozen (last event Aug 2026)
    # and misses newer fixtures. Same Strapi shape, so get_api_events() is unchanged.
    base = (
        f"{STADIUM_API}?"
        f"filters[event][daterange][start][$gte]={floor}"
        "&populate[0]=event.image&populate[1]=event.daterange&populate[2]=thumbnail"
    )
    all_data: List[dict] = []
    page = 1
    while True:
        try:
            response = requests.get(
                f"{base}&pagination[page]={page}&pagination[pageSize]={page_size}",
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise StadiumApiError(f"stadium API fetch failed on page {page}: {exc}") from exc
        all_data.extend(payload.get("data", []))
        pagination = payload.get("meta", {}).get("pagination", {}) or {}
        if page >= (pagination.get("pageCount") or 1):
            break
        page += 1
    return {"data": all_data}


def _parse_api_datetime(value: str) -> datetime:
    """Parse an ISO timestamp from the API into a SAST-aware datetime.

    The API emits UTC with a trailing Z. A value that arrives without any offset
    is read as UTC too, not as the runner's local timezone — otherwise the same
    payload would produce different times on a developer's machine and in CI.
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(SAST)


def get_api_events(resp: Any) -> List[CalEvent]:
    """Convert a stadium API response into calendar events.

    Malformed entries are skipped rather than raising: one bad record should not
    cost the calendar a whole season of fixtures. A response that yields nothing
    at all is caught by the guards in ``check_regression``.
    """
    events: List[CalEvent] = []
    for item in resp.get("data", []):
        attributes = item.get("attributes") or {}
        for entry in attributes.get("event") or []:
            if not isinstance(entry, dict):
                continue
            for daterange in entry.get("daterange") or []:
                if not isinstance(daterange, dict) or not daterange.get("start"):
                    continue
                try:
                    start = _parse_api_datetime(daterange["start"])
                    end_raw = daterange.get("end")
                    end = _parse_api_datetime(end_raw) if end_raw else None
                except (AttributeError, TypeError, ValueError) as exc:
                    print(f"Warning: skipping malformed stadium daterange {daterange}: {exc}")
                    continue
                if end is None or end <= start:
                    # No usable end: run the event to the end of its start day.
                    end = start.replace(hour=23, minute=59, second=59, microsecond=0)
                # The site's own link text is usually "Tickets"; keep it when given.
                label = (entry.get("externallinktext") or "").strip() or "Tickets"
                events.append(
                    CalEvent(
                        name=(entry.get("title") or "No title").strip(),
                        start=start,
                        end=end,
                        description=(entry.get("description") or "").strip(),
                        url=(entry.get("externallink") or "").strip(),
                        link_label=label,
                        category=CATEGORY_STADIUM,
                    )
                )
    return events


# ------------------------------------------------------------
# City events
# ------------------------------------------------------------

def get_city_events(records: Iterable[Dict[str, str]]) -> List[CalEvent]:
    """Convert city-event scraper records into calendar events.

    Records with no date are skipped by design: a scrape-only event with no
    readable date is left off the calendar rather than given an invented one.
    Records whose dates carry a time (First Thursdays) become timed events; the
    rest become all-day events with the exclusive end iCal expects.
    """
    events: List[CalEvent] = []
    for record in records:
        if not record.get("start_date"):
            continue
        try:
            start_raw = record["start_date"]
            end_raw = record.get("end_date") or start_raw
            if "T" in start_raw:
                start: Union[date, datetime] = datetime.fromisoformat(start_raw)
                end: Union[date, datetime] = datetime.fromisoformat(end_raw)
            else:
                start = date.fromisoformat(start_raw)
                end = date.fromisoformat(end_raw) + timedelta(days=1)  # exclusive
            if end <= start:
                # A misparsed range (e.g. one that crosses New Year and carries a
                # single year) would otherwise publish DTEND before DTSTART. Fall
                # back to the start day alone rather than an invalid event.
                print(f"Warning: '{record['name']}' ends before it starts; "
                      f"publishing {start_raw} only")
                end = start + timedelta(days=1) if not isinstance(start, datetime) else start
            events.append(
                CalEvent(
                    name=record["name"],
                    start=start,
                    end=end,
                    description=(record.get("description") or "").strip(),
                    url=(record.get("url") or "").strip(),
                    location=(record.get("location") or "").strip(),
                    category=CATEGORY_CITY,
                )
            )
        except Exception as exc:
            print(f"Warning: skipping event '{record.get('name')}': {exc}")
    return events


# ------------------------------------------------------------
# Deduplication
# ------------------------------------------------------------

def canonical_key(name: str) -> Tuple[str, Optional[str]]:
    """Return ``(grouping key, canonical display name or None)`` for an event name.

    Names that match no alias group only with an identically-named event, which is
    what collapses the stadium's own two one-day entries for a weekend tournament.
    """
    for pattern, canonical in CANONICAL_NAMES:
        if pattern.search(name):
            return canonical, canonical
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip(), None


def last_covered_day(event: CalEvent) -> date:
    """The last calendar day the event actually occupies.

    All-day ends are exclusive, so the last day is the one before; a timed event
    occupies the day it ends on, unless it ends exactly at midnight. Getting this
    wrong shortens a merged event by a day.
    """
    if event.all_day:
        return event.end - timedelta(days=1)
    end = event.end_instant
    if (end.hour, end.minute, end.second, end.microsecond) == (0, 0, 0, 0):
        return end.date() - timedelta(days=1)
    return end.date()


def _combine(group: List[CalEvent], canonical: Optional[str]) -> CalEvent:
    """Collapse events that are the same disruption into one entry.

    The span is the union of the members'. Metadata is taken from the curated
    record first (the one already published under the canonical name, which
    carries the hand-written traffic blurb), then from the highest-priority
    source, so the stadium's marketing copy never displaces a blurb written for
    this calendar.
    """
    if len(group) == 1:
        # Still rename: whether both sources are in range varies run to run, and a
        # name that flips is a UID that flips. Without this the Gun Run appears
        # twice — once as preserved history under its canonical name, once fresh
        # under the sponsor name the stadium uses.
        solo = group[0]
        return replace(solo, name=canonical) if canonical else solo

    ordered = sorted(
        group,
        key=lambda ev: (
            0 if canonical and ev.name == canonical else 1,
            -CATEGORY_PRIORITY.get(ev.category, 0),
            ev.start_instant,
        ),
    )
    primary = ordered[0]

    start_source = min(group, key=lambda ev: ev.start_instant)
    end_source = max(group, key=lambda ev: ev.end_instant)
    if any(ev.all_day for ev in group):
        # Mixed timed/all-day members collapse to all-day: an all-day member has no
        # times to preserve, so the union can only be expressed as whole days.
        start: Union[date, datetime] = start_source.start_instant.date()
        end: Union[date, datetime] = last_covered_day(end_source) + timedelta(days=1)
        if end <= start:
            end = start + timedelta(days=1)
    else:
        start = start_source.start
        end = end_source.end

    def first(attr: str) -> str:
        for event in ordered:
            value = getattr(event, attr)
            if value:
                return value
        return ""

    # Take the link and its label off the same record, so a "Tickets" label never
    # ends up attached to some other event's URL.
    linked = next((event for event in ordered if event.url), None)

    return replace(
        primary,
        name=canonical or primary.name,
        start=start,
        end=end,
        description=first("description"),
        url=linked.url if linked else "",
        link_label=linked.link_label if linked else primary.link_label,
        location=first("location"),
        category=max(
            (ev.category for ev in group), key=lambda c: CATEGORY_PRIORITY.get(c, 0)
        ),
    )


def dedupe_events(events: List[CalEvent]) -> List[CalEvent]:
    """Collapse the same real-world event arriving from more than one source.

    The Gun Run, for instance, reaches the calendar twice: once from the stadium
    API (under its sponsor name, dated to the expo) and once from the city
    scrapers (under its own name, dated to the race). Events sharing a canonical
    name and falling within ``DUPLICATE_WINDOW`` of each other become one entry
    spanning both.
    """
    grouped: Dict[str, List[CalEvent]] = {}
    canonicals: Dict[str, Optional[str]] = {}
    for event in events:
        key, canonical = canonical_key(event.name)
        grouped.setdefault(key, []).append(event)
        canonicals[key] = canonical

    merged: List[CalEvent] = []
    for key, group in grouped.items():
        group.sort(key=lambda ev: ev.start_instant)
        cluster: List[CalEvent] = [group[0]]
        cluster_end = group[0].end_instant
        for event in group[1:]:
            if event.start_instant - cluster_end <= DUPLICATE_WINDOW:
                cluster.append(event)
                cluster_end = max(cluster_end, event.end_instant)
            else:
                merged.append(_combine(cluster, canonicals[key]))
                cluster = [event]
                cluster_end = event.end_instant
        merged.append(_combine(cluster, canonicals[key]))
    return merged


# ------------------------------------------------------------
# Reading and writing the calendar
# ------------------------------------------------------------

def _component_value(component: Event, name: str) -> str:
    value = component.get(name)
    return str(value) if value is not None else ""


def parse_calendar(raw: bytes) -> List[CalEvent]:
    """Parse published ICS bytes back into events."""
    calendar = Calendar.from_ical(raw)
    events: List[CalEvent] = []
    for component in calendar.walk("VEVENT"):
        dtstart = component.get("dtstart")
        if dtstart is None:
            continue
        start = dtstart.dt
        dtend = component.get("dtend")
        if dtend is not None:
            end = dtend.dt
        elif isinstance(start, datetime):
            end = start
        else:
            end = start + timedelta(days=1)
        if isinstance(start, datetime):
            start = _as_instant(start)
            end = _as_instant(end)

        url = _component_value(component, "url")
        description, label = split_description(_component_value(component, "description"), url)
        categories = component.get("categories")
        names = list(getattr(categories, "cats", [])) if categories is not None else []
        category = next(
            (str(c) for c in names if str(c) in KNOWN_CATEGORIES), CATEGORY_CITY
        )
        dtstamp = component.get("dtstamp")
        try:
            sequence = int(component.get("sequence") or 0)
        except (TypeError, ValueError):
            sequence = 0
        events.append(
            CalEvent(
                name=_component_value(component, "summary").strip(),
                start=start,
                end=end,
                description=description,
                url=url,
                link_label=label,
                location=_component_value(component, "location"),
                category=category,
                uid=_component_value(component, "uid"),
                sequence=sequence,
                dtstamp=dtstamp.dt if dtstamp is not None else None,
            )
        )
    return events


def load_existing_events(path: str) -> List[CalEvent]:
    """Load events from a previously published .ics, if present.

    A missing file is the first run and fine. A file that is present but cannot
    be read is not: treating it as empty would discard every preserved past event
    and leave the shrink guard with nothing to compare against, so a corrupt
    calendar would be silently republished with its history gone.
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as handle:
            return parse_calendar(handle.read())
    except Exception as exc:
        raise CalendarBuildError(
            f"could not parse the existing {path}: {exc}. Refusing to overwrite it; "
            "fix or remove the file to rebuild the calendar from scratch."
        ) from exc


def build_calendar(events: List[CalEvent]) -> Calendar:
    """Assemble the VCALENDAR, including the metadata clients display.

    Without X-WR-CALNAME a subscribed calendar shows up named after its URL, and
    without DTSTAMP the events are not strictly valid; both were missing before.
    Events are marked TRANSPARENT so subscribing does not make you look busy.
    """
    calendar = Calendar()
    calendar.add("prodid", PRODID)
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("method", "PUBLISH")
    calendar.add("x-wr-calname", CALENDAR_NAME)
    calendar.add("x-wr-caldesc", CALENDAR_DESCRIPTION)
    calendar.add("x-wr-timezone", "Africa/Johannesburg")
    calendar.add("refresh-interval", REFRESH_INTERVAL, parameters={"VALUE": "DURATION"})
    calendar.add("x-published-ttl", vDuration(REFRESH_INTERVAL))
    calendar.add_component(Timezone.from_tzid("Africa/Johannesburg"))

    for event in events:
        component = Event()
        component.add("uid", event.uid)
        component.add("dtstamp", event.dtstamp)
        component.add("summary", event.name)
        component.add("dtstart", event.start)
        component.add("dtend", event.end)
        description = render_description(event)
        if description:
            component.add("description", description)
        if event.url:
            component.add("url", event.url)
        if event.location:
            component.add("location", event.location)
        component.add("categories", [event.category])
        component.add("sequence", event.sequence)
        component.add("last-modified", event.dtstamp)
        component.add("transp", "TRANSPARENT")
        calendar.add_component(component)
    return calendar


def stamp_events(
    events: List[CalEvent], previous: List[CalEvent], now: Optional[datetime] = None
) -> List[CalEvent]:
    """Assign UID, DTSTAMP and SEQUENCE, carrying unchanged events over verbatim.

    An event whose content has not changed keeps its previous DTSTAMP and
    SEQUENCE, so a no-op rebuild produces a byte-identical file; one that has
    changed gets a fresh DTSTAMP and its SEQUENCE bumped, which is how clients
    know to re-sync a moved fixture.
    """
    moment = now or datetime.now(timezone.utc)
    by_uid = {event.uid: event for event in previous if event.uid}
    stamped: List[CalEvent] = []
    for event in events:
        event = replace(event, uid=event.uid or make_uid(event.name, event.start))
        old = by_uid.get(event.uid)
        if old is not None and fingerprint(old) == fingerprint(event):
            stamped.append(replace(event, dtstamp=old.dtstamp or moment, sequence=old.sequence))
        elif old is not None:
            stamped.append(replace(event, dtstamp=moment, sequence=old.sequence + 1))
        else:
            stamped.append(replace(event, dtstamp=moment, sequence=0))
    return stamped


def merge_events(fresh: List[CalEvent], existing: List[CalEvent]) -> List[CalEvent]:
    """Combine freshly fetched events with the previously published calendar.

    Freeze rule:
      - Past events (already finished) are preserved from the existing file so
        history survives even after the stadium API stops returning them.
      - Future events come only from the fresh fetch, so reschedules and
        cancellations are honoured (no ghost entries for moved fixtures).
    A fresh copy always wins on UID collision, keeping details up to date.
    """
    merged: Dict[str, CalEvent] = {}
    for event in existing:
        if is_past(event):
            uid = event.uid or make_uid(event.name, event.start)
            merged[uid] = replace(event, uid=uid)
    for event in fresh:
        uid = event.uid or make_uid(event.name, event.start)
        merged[uid] = replace(event, uid=uid)
    return sorted(merged.values(), key=lambda ev: (ev.start_instant, ev.name))


# ------------------------------------------------------------
# Guards
# ------------------------------------------------------------

def _future(events: Iterable[CalEvent]) -> List[CalEvent]:
    return [event for event in events if not is_past(event)]


def check_regression(
    stadium: List[CalEvent],
    city: List[CalEvent],
    fresh: List[CalEvent],
    existing: List[CalEvent],
    *,
    allow_shrink: bool = False,
) -> None:
    """Refuse to publish a calendar that has lost most of what it used to hold.

    The failure this exists for: a network blip empties the stadium fetch, the
    build cheerfully writes a calendar with every upcoming fixture deleted, and
    CI commits it. Subscribers then see an empty calendar until the next
    scheduled run. Aborting leaves the last good file in place instead.

    ``stadium`` and ``city`` are the per-source events before deduplication (so a
    source that returned nothing is named); ``fresh`` is what would be published
    and is what the count is compared on.
    """
    problems: List[str] = []

    if not stadium:
        problems.append("the stadium fetch produced no events at all")
    if not city:
        problems.append("the city scrapers produced no dated events at all")

    previous_future = len(_future(existing))
    current_future = len(_future(fresh))
    if previous_future and current_future < previous_future * MIN_RETAINED_FRACTION:
        problems.append(
            f"upcoming events fell from {previous_future} to {current_future} "
            f"(below the {MIN_RETAINED_FRACTION:.0%} floor)"
        )

    if not problems:
        return
    summary = "; ".join(problems)
    if allow_shrink:
        print(f"Warning: publishing despite a suspected regression: {summary}")
        return
    raise CalendarBuildError(
        f"refusing to publish: {summary}. Re-run with --allow-shrink if this is real."
    )


def check_stadium_horizon(
    events: List[CalEvent], now: Optional[datetime] = None
) -> Optional[str]:
    """Warn when the stadium feed's newest event is suspiciously close to today.

    The endpoint has silently frozen before (the old host stalled and kept serving
    a fixed set of events). A feed that has stopped being updated looks healthy
    from the outside; what gives it away is that it stops reaching into the future.
    """
    moment = now or datetime.now(SAST)
    stadium = [event for event in events if event.category == CATEGORY_STADIUM]
    if not stadium:
        return "stadium feed returned no events"
    newest = max(event.start_instant for event in stadium)
    if newest - moment < MIN_STADIUM_HORIZON:
        return (
            f"stadium feed's newest event is {newest.date()}, only "
            f"{(newest - moment).days} days out — the endpoint may have frozen or moved"
        )
    return None


# ------------------------------------------------------------
# Health report
# ------------------------------------------------------------

def load_health(path: str) -> dict:
    """Load the previous health report, if any."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        print(f"Warning: could not parse existing {path}: {exc}")
        return {}


def find_degradations(health: dict) -> List[str]:
    """List the sources that have stopped reading their date off the live site.

    This is the check CLAUDE.md convention 1 describes doing by hand: spotting a
    scraper that is coasting on its computed fallback, which looks fine on the
    calendar but is a date nobody confirmed.

    Each source carries ``last_live`` — when it last read a real date — carried
    forward from run to run. Comparing against that rather than against the
    previous run's report matters: the workflow commits the report it just wrote,
    so a pairwise comparison would find the degraded state already recorded next
    time and go quiet, alarming exactly once for a scraper that stays broken.
    """
    degradations: List[str] = []
    for key, entry in (health.get("sources") or {}).items():
        last_live = entry.get("last_live")
        if last_live and entry.get("source") not in SCRAPED_SOURCES:
            degradations.append(
                f"{key}: has not read a live date since {last_live} "
                f"(now falling back to '{entry.get('source')}')"
            )
    return degradations


def build_health(
    records: List[Dict[str, str]],
    events: List[CalEvent],
    warnings: List[str],
    previous: dict,
    now: Optional[datetime] = None,
) -> dict:
    """Assemble the health report published alongside the calendar."""
    moment = now or datetime.now(timezone.utc)
    old_sources = previous.get("sources") or {}
    sources: Dict[str, dict] = {}
    for record in records:
        key = record.get("fetcher") or record["name"]
        if key == FIRST_THURSDAYS_FETCHER:  # one computed rule, 24 identical records
            continue
        source = record.get("source", "none")
        # Carried forward so a scraper that stays broken keeps being reported.
        last_live = (old_sources.get(key) or {}).get("last_live")
        if source in SCRAPED_SOURCES:
            last_live = moment.date().isoformat()
        sources[key] = {
            "name": record.get("name", ""),
            "source": source,
            "last_live": last_live,
            "start_date": record.get("start_date"),
            "end_date": record.get("end_date"),
            "url": record.get("url", ""),
        }

    stadium = [event for event in events if event.category == CATEGORY_STADIUM]
    current = {
        "generated_at": moment.isoformat(),
        "calendar": {
            "total": len(events),
            "upcoming": len(_future(events)),
            "past": len(events) - len(_future(events)),
        },
        "stadium": {
            "events": len(stadium),
            "newest_start": (
                max(event.start_instant for event in stadium).date().isoformat()
                if stadium
                else None
            ),
        },
        "sources": sources,
        "warnings": warnings,
    }
    current["degradations"] = find_degradations(current) + warnings
    return current


# ------------------------------------------------------------
# Entry point
# ------------------------------------------------------------

def check_health_file(path: str = HEALTH_PATH) -> int:
    """Exit status for CI: non-zero when the last build recorded a degradation.

    Kept separate from the build so a degraded source still publishes a calendar
    (a computed date beats no calendar) while the workflow still goes red.
    """
    health = load_health(path)
    if not health:
        print(f"No {path} to check.")
        return 0
    degradations = health.get("degradations") or []
    if not degradations:
        print("Health check passed: no source degraded since the previous run.")
        return 0
    print("Health check failed:")
    for line in degradations:
        print(f"  - {line}")
    return 1


def generate(ics_path: str = ICS_PATH, health_path: str = HEALTH_PATH,
             events_path: str = EVENTS_PATH, *, allow_shrink: bool = False) -> dict:
    """Build the calendar and the health report, and write both."""
    existing = load_existing_events(ics_path)

    resp = fetch_stadium_api(api_floor())
    stadium_events = get_api_events(resp)
    records = fetch_all_events()
    city_events = get_city_events(records)
    # First Thursdays come from an unconditional calendar rule, so they would keep
    # the city list non-empty even with every real scraper dead. The guard is given
    # the scraped events only, or it could never fire.
    scraped_city = get_city_events(
        record for record in records if record.get("fetcher") != FIRST_THURSDAYS_FETCHER
    )

    fresh = dedupe_events(stadium_events + city_events)
    check_regression(stadium_events, scraped_city, fresh, existing, allow_shrink=allow_shrink)

    merged = merge_events(fresh, existing)
    stamped = stamp_events(merged, existing)

    warnings = [warning for warning in [check_stadium_horizon(stadium_events)] if warning]
    health = build_health(records, stamped, warnings, load_health(health_path))

    with open(ics_path, "wb") as handle:
        handle.write(build_calendar(stamped).to_ical())
    with open(health_path, "w", encoding="utf-8") as handle:
        json.dump(health, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    dump_events(records, events_path)

    print(
        f"Wrote {len(stamped)} events to {ics_path} "
        f"({health['calendar']['upcoming']} upcoming, {health['calendar']['past']} past)."
    )
    for warning in warnings:
        print(f"Warning: {warning}")
    return health


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--allow-shrink",
        action="store_true",
        help="publish even if the calendar lost most of its upcoming events",
    )
    parser.add_argument(
        "--check-health",
        action="store_true",
        help="exit non-zero if the last build recorded a degraded source",
    )
    args = parser.parse_args(argv)

    if args.check_health:
        return check_health_file()
    try:
        generate(allow_shrink=args.allow_shrink)
    except (StadiumApiError, CalendarBuildError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
