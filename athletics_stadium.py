#!/usr/bin/env python3
"""Green Point Athletics Stadium — venue feed for the traffic calendar.

The athletics stadium is a separate City facility from DHL Stadium, ~400 m away
in the Green Point Urban Park. Nothing in the DHL Stadium API covers it, so its
meets never reach the calendar even though the big ones put buses and parents
onto Fritz Sonnenberg and Helen Suzman.

**UNVERIFIED.** Every parser here was written without ever fetching the pages it
targets: the session that wrote it had those hosts blocked by a network policy.
The candidate list and the shapes below come from search results, not from the
real HTML. Run ``probe_sources.py`` from a machine with normal network access
before trusting any of it — that prints which candidates answer, which expose a
WordPress REST API, and whether their titles carry parseable dates. Until then
this module is disabled by default (see ``generate_dhl_ics.ENABLE_ATHLETICS``),
so it cannot touch the published calendar.

Deliberately has **no computed fallback.** The obvious candidates for one — the
national primary schools championships, the WP high schools championships — move
host city and venue year to year (the WP meet was moved to Paarl at short notice
once, precisely because Green Point was too busy). A calendar rule would publish
confident road closures for a meet happening 60 km away, so per CLAUDE.md these
stay scrape-only: no date read, no event published.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Optional, Pattern

from city_events import (
    EventRecord,
    SOURCE_JSONLD,
    SOURCE_NONE,
    SOURCE_TEXT,
    _is_upcoming,  # same date guard the city scrapers use; duplicating it would let the two drift
    generic_date_hunt,
    html_to_text,
    jsonld_event_dates,
    safe_get,
    session,
)

VENUE_NAME = "Green Point Athletics Stadium"
VENUE_LOCATION = "Green Point Athletics Stadium, Fritz Sonnenberg Road, Green Point"
FETCHER_KEY = "fetch_athletics_stadium"

# Names the venue goes by. A source that calls it "Green Point Track" or just
# "Green Point Stadium" is talking about the same place — but note that
# "Green Point Stadium" was also the old name of the demolished stadium that DHL
# Stadium replaced, so a match alone is not proof the event is at the track.
VENUE_ALIASES: Pattern = re.compile(
    r"green\s*point\s*(athletics?\s*)?(stadium|track|oval)", re.IGNORECASE
)


@dataclass(frozen=True)
class Candidate:
    """One place the venue's fixtures might be readable from.

    ``kind`` selects the strategy: ``wordpress`` queries the REST API (both
    confirmed-WordPress candidates use ``?p=NNNN`` permalinks, so ``wp-json`` is
    very likely exposed), ``html`` falls back to scraping a single page.
    """

    key: str
    base: str
    kind: str
    note: str


# Ranked best-first. The ranking is an argument, not a measurement — probe_sources.py
# is what turns it into one.
CANDIDATES: List[Candidate] = [
    Candidate(
        key="wpa",
        base="https://wpa.org.za",
        kind="wordpress",
        note="Western Province Athletics. Authoritative for provincial athletics. Post "
             "titles carry both date and venue ('WPA Track & Field - 8 October 2022 - "
             "Green Point Athletics Stadium'), which is unusually parseable. The season "
             "fixture list itself is a versioned PDF, not scraped here.",
    ),
    Candidate(
        key="athleticsresults",
        base="https://athleticsresults.co.za/wp",
        kind="wordpress",
        note="Carries the ATC Green Point Athletics Series and similar club meets. "
             "Higher volume, lower signal than WPA.",
    ),
    Candidate(
        key="city_venue",
        base="https://www.capetown.gov.za/Explore%20and%20enjoy/See-all-city-facilities/"
             "our-signature-venues/green-point-athletic-stadium",
        kind="html",
        note="The City owns and books the venue, so this is the only candidate that could "
             "cover non-athletics use (school sports days, football, filming). Expected to "
             "be a static brochure page with booking contacts rather than a calendar — "
             "if it does carry a calendar, it supersedes everything above.",
    ),
]

# Meets worth a calendar entry: the ones that fill the stands and the surrounding
# streets. A championship, a national or provincial meet or an international
# invitational brings buses, parents and spectators; a midweek club league meeting
# brings 150 athletes and no traffic at all. Publishing the latter would bury the
# events this calendar exists to warn about.
MATERIAL_PATTERNS: Pattern = re.compile(
    r"\b("
    r"champs?|championships?|"
    r"national|provincial|inter[- ]?high|interhigh|"
    r"schools?|grand\s*prix|challenger|continental|invitational|"
    r"international|trials?|final"
    r")\b",
    re.IGNORECASE,
)

# Checked first: a routine fixture stays off even when its name happens to contain a
# material word ("League Final", "Masters Championships" — small, regular, local).
ROUTINE_PATTERNS: Pattern = re.compile(
    r"\b(league|time\s*trial|club\s*meeting|open\s*meeting|masters|training|"
    r"twilight|development|pre[- ]?season)\b",
    re.IGNORECASE,
)


def is_material(name: str) -> bool:
    """Whether a meet is big enough to be worth a traffic warning.

    A name-shaped heuristic, because no source publishes expected attendance. It
    will be wrong at the edges; ``probe_sources.py`` output is what should decide
    whether meet names carry enough signal to be filtered this way at all. Callers
    can bypass it (see ``fetch_athletics_events(material_only=False)``).
    """
    if ROUTINE_PATTERNS.search(name):
        return False
    return bool(MATERIAL_PATTERNS.search(name))


def mentions_venue(*texts: str) -> bool:
    """Whether any of the given strings names the athletics stadium."""
    return any(VENUE_ALIASES.search(text or "") for text in texts)


def wordpress_posts(
    base: str, query: str = "Green Point", per_page: int = 50
) -> List[dict]:
    """Search a WordPress site's REST API and return the matching posts.

    Preferred over scraping rendered HTML: the REST API returns clean JSON that
    does not change when the theme does. Returns an empty list (and logs) when the
    endpoint is absent or unreadable — plenty of WordPress installs disable it.
    """
    url = (
        f"{base.rstrip('/')}/wp-json/wp/v2/posts"
        f"?search={requests_quote(query)}&per_page={per_page}"
        "&orderby=date&order=desc&_fields=id,link,title,excerpt,date"
    )
    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logging.warning(f"WordPress REST unavailable at {base}: {exc}")
        return []
    return payload if isinstance(payload, list) else []


def requests_quote(value: str) -> str:
    """Percent-encode a query-string value (kept local to avoid an import for one call)."""
    from urllib.parse import quote

    return quote(value)


def _rendered(field: object) -> str:
    """Pull the text out of a WordPress ``{"rendered": "..."}`` field."""
    if isinstance(field, dict):
        return str(field.get("rendered") or "")
    return str(field or "")


def events_from_posts(posts: Iterable[dict]) -> List[EventRecord]:
    """Turn WordPress posts into event records.

    Only posts that name the venue *and* yield an upcoming date are kept. The date
    is hunted in the title first: these sites put it there ("WPA Track & Field -
    8 October 2022 - Green Point Athletics Stadium"), and a title date is far less
    likely to be some unrelated date from the body copy.
    """
    records: List[EventRecord] = []
    for post in posts:
        title = html_to_text(_rendered(post.get("title")))
        excerpt = html_to_text(_rendered(post.get("excerpt")))
        if not mentions_venue(title, excerpt):
            continue
        hit = generic_date_hunt(title) or generic_date_hunt(excerpt)
        if not hit or not _is_upcoming(hit):
            continue
        records.append(
            {
                "name": clean_meet_name(title),
                "url": str(post.get("link") or ""),
                "source": SOURCE_TEXT,
                "start_date": hit["start_date"],
                "end_date": hit["end_date"],
                "location": VENUE_LOCATION,
            }
        )
    return records


def events_from_html(url: str) -> List[EventRecord]:
    """Scrape a single page for one upcoming event at the venue.

    A fallback for a candidate with no REST API. Prefers schema.org Event markup
    and falls back to a text date hunt, the same order the city scrapers use.
    """
    html = safe_get(url)
    if not html:
        return []
    for source, hit in (
        (SOURCE_JSONLD, jsonld_event_dates(html)),
        (SOURCE_TEXT, generic_date_hunt(html_to_text(html))),
    ):
        if hit and _is_upcoming(hit):
            return [
                {
                    "name": VENUE_NAME,
                    "url": url,
                    "source": source,
                    "start_date": hit["start_date"],
                    "end_date": hit["end_date"],
                    "location": VENUE_LOCATION,
                }
            ]
    return []


# Editorial noise these sites put in front of a meet name. Stripped so the published
# SUMMARY reads as an event, and — because the UID is hashed from the name — so the
# same meet keeps one identity when a site reposts it with a different prefix.
TITLE_NOISE: Pattern = re.compile(
    r"^\s*(reminder|notice|update|entries?\s+(open|close)|results?)\s*[:\-–—]\s*",
    re.IGNORECASE,
)


def clean_meet_name(title: str) -> str:
    """Reduce a post title to the meet name.

    Trims an editorial prefix and any trailing ' - <date> - <venue>' tail, then
    prefixes the venue so the calendar entry says where the disruption is.
    """
    name = TITLE_NOISE.sub("", title).strip()
    # Drop everything from the first separator that introduces a date or the venue.
    parts = re.split(r"\s+[-–—]\s+", name)
    kept = [
        part
        for part in parts
        if not VENUE_ALIASES.search(part) and not generic_date_hunt(part)
    ]
    name = " - ".join(kept).strip() or name
    name = re.sub(r"\s{2,}", " ", name).strip(" -–—:")
    return f"{name} (Green Point Track)" if name else VENUE_NAME


def fetch_athletics_events(
    candidates: Optional[Iterable[Candidate]] = None,
    *,
    material_only: bool = True,
) -> List[EventRecord]:
    """Collect upcoming meets at the athletics stadium from the candidate sources.

    Every candidate is tried and the results pooled: one source failing should cost
    its own events, not the others'. Never raises — the caller treats this as a soft
    source that must not be able to block publication of the rest of the calendar.
    """
    records: List[EventRecord] = []
    for candidate in candidates if candidates is not None else CANDIDATES:
        try:
            if candidate.kind == "wordpress":
                found = events_from_posts(wordpress_posts(candidate.base))
            else:
                found = events_from_html(candidate.base)
        except Exception as exc:  # a broken candidate must not cost the others
            logging.error(f"Athletics candidate {candidate.key} failed: {exc}")
            continue
        logging.info(f"Athletics candidate {candidate.key}: {len(found)} event(s)")
        records.extend(found)

    if material_only:
        records = [record for record in records if is_material(record["name"])]
    return dedupe_records(records)


def dedupe_records(records: List[EventRecord]) -> List[EventRecord]:
    """Drop records for the same meet on the same day arriving from two candidates.

    Only exact same-name-same-start collisions are dropped here; near-duplicates
    with different names are left for ``generate_dhl_ics.dedupe_events``, which
    already does fuzzy matching across sources.
    """
    seen: Dict[tuple, EventRecord] = {}
    for record in records:
        key = (record["name"].casefold(), record.get("start_date"))
        seen.setdefault(key, record)
    return list(seen.values())


def health_record(records: List[EventRecord]) -> EventRecord:
    """Summarise the venue feed as a single record for the health report.

    Reuses the existing per-source machinery rather than adding a parallel one: the
    report keys on ``fetcher``, and ``source`` drives the ``last_live`` carry-forward,
    so a feed that stops reading live dates is reported like any other scraper.
    """
    upcoming = sorted(records, key=lambda record: record.get("start_date", ""))
    summary: EventRecord = {
        "name": VENUE_NAME,
        "url": CANDIDATES[0].base,
        "source": upcoming[0]["source"] if upcoming else SOURCE_NONE,
        "fetcher": FETCHER_KEY,
    }
    if upcoming:
        summary["start_date"] = upcoming[0]["start_date"]
        summary["end_date"] = upcoming[0].get("end_date", upcoming[0]["start_date"])
    return summary


def main() -> None:
    """Print what the venue feed currently yields, for a quick manual check."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    records = fetch_athletics_events()
    if not records:
        print("No upcoming events found at the athletics stadium.")
        print("Run probe_sources.py to see which candidate sources are reachable.")
        return
    for record in sorted(records, key=lambda r: r["start_date"]):
        print(f"{record['start_date']} .. {record['end_date']}  {record['name']}")
        print(f"    {record['url']}")


if __name__ == "__main__":
    main()
