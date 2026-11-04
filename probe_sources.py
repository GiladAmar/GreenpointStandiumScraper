#!/usr/bin/env python3
"""Probe the candidate sources for Green Point Athletics Stadium fixtures.

The venue's events never reach the calendar, and the obvious sources could not be
checked from the session that proposed them: a network policy blocked every host.
This script does that check. Run it from a machine with normal network access:

    python3 probe_sources.py                  # human-readable report
    python3 probe_sources.py --json out.json  # also dump the raw findings

For each candidate it reports whether the host answers, where it redirects to,
whether it exposes a WordPress REST API, whether it publishes schema.org Event
markup, how often it names the venue, and — the question that actually decides
the design — whether a usable date can be parsed out of what it serves.

It only reads. Nothing here writes to the calendar or the health report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

import requests

from athletics_stadium import CANDIDATES, VENUE_ALIASES, events_from_posts, is_material
from city_events import generic_date_hunt, html_to_text, jsonld_event_dates

TIMEOUT = 25
HEADERS = {"User-Agent": "CapeTownTrafficEventsBot/1.5 (source probe)"}

# Everything worth evaluating in one run, not just the sources already wired up.
# Each entry is (key, url, what we are hoping to learn).
EXTRA_TARGETS: List[tuple] = [
    ("asa_fixtures", "https://athleticssa.org.za/",
     "Athletics SA — national fixtures only, which is a natural materiality filter"),
    ("backtrack_fixtures", "https://backtrack.co.za/2026/01/16/2026-athletics-south-africa-fixtures-list/",
     "Mirror of the ASA annual fixtures list; WordPress, so possibly REST-readable"),
    ("quicket", "https://www.quicket.co.za/events/",
     "Ticketed meets only, but structured; check whether venue search is possible"),
    ("entryninja", "https://www.entryninja.com/events",
     "Entry platform; search suggested it does not carry Green Point meets"),
    ("city_events_permits", "https://www.capetown.gov.za/Media-and-news",
     "City Event Permit Office notices — covers all permitted events, not just athletics"),
]


@dataclass
class Probe:
    """What one candidate URL turned out to be."""

    key: str
    url: str
    note: str = ""
    ok: bool = False
    status: Optional[int] = None
    final_url: Optional[str] = None
    redirected: bool = False
    content_type: Optional[str] = None
    bytes: Optional[int] = None
    elapsed_ms: Optional[int] = None
    error: Optional[str] = None
    # What the body turned out to contain.
    is_wordpress: bool = False
    wp_rest_ok: bool = False
    wp_post_count: Optional[int] = None
    has_jsonld_event: bool = False
    venue_mentions: int = 0
    parsed_date: Optional[str] = None
    sample_titles: List[str] = field(default_factory=list)
    parsed_events: List[Dict[str, str]] = field(default_factory=list)
    verdict: str = ""


def fetch(url: str) -> tuple:
    """GET a URL, returning (response, error-string). Never raises."""
    started = time.monotonic()
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        return response, None, int((time.monotonic() - started) * 1000)
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}", int((time.monotonic() - started) * 1000)


def probe_wordpress(base: str, probe: Probe) -> None:
    """Check for a WordPress REST API and try the real venue search against it.

    This is the decisive test for the two WordPress candidates: if the search
    returns posts whose titles carry a parseable date, the scraper approach works;
    if it returns nothing useful, it does not, whatever the HTML looks like.
    """
    rest = f"{base.rstrip('/')}/wp-json/wp/v2/posts?per_page=5&_fields=id,title"
    response, error, _ = fetch(rest)
    if error or response is None or response.status_code != 200:
        probe.wp_rest_ok = False
        return
    try:
        payload = response.json()
    except ValueError:
        probe.wp_rest_ok = False
        return
    probe.wp_rest_ok = isinstance(payload, list)

    # The question that matters: does a venue search yield dated, parseable meets?
    search = (
        f"{base.rstrip('/')}/wp-json/wp/v2/posts?search=Green%20Point&per_page=50"
        "&orderby=date&order=desc&_fields=id,link,title,excerpt,date"
    )
    response, error, _ = fetch(search)
    if error or response is None or response.status_code != 200:
        return
    try:
        posts = response.json()
    except ValueError:
        return
    if not isinstance(posts, list):
        return
    probe.wp_post_count = len(posts)
    probe.sample_titles = [
        html_to_text(str((post.get("title") or {}).get("rendered", "")))[:110]
        for post in posts[:8]
    ]
    for record in events_from_posts(posts):
        probe.parsed_events.append(
            {
                "name": record["name"],
                "start_date": record["start_date"],
                "end_date": record["end_date"],
                "material": str(is_material(record["name"])),
                "url": record["url"],
            }
        )


def probe_url(key: str, url: str, note: str, kind: str = "html") -> Probe:
    """Fetch one candidate and work out what it is."""
    probe = Probe(key=key, url=url, note=note)
    response, error, elapsed = fetch(url)
    probe.elapsed_ms = elapsed
    if error or response is None:
        probe.error = error
        probe.verdict = "unreachable"
        return probe

    probe.ok = response.ok
    probe.status = response.status_code
    probe.final_url = response.url
    probe.redirected = response.url.rstrip("/") != url.rstrip("/")
    probe.content_type = response.headers.get("content-type", "")
    body = response.text or ""
    probe.bytes = len(body)

    probe.is_wordpress = (
        "wp-content" in body or "wp-json" in body or "/wp/" in url
    )
    probe.has_jsonld_event = jsonld_event_dates(body) is not None
    probe.venue_mentions = len(VENUE_ALIASES.findall(body))
    hit = generic_date_hunt(html_to_text(body))
    probe.parsed_date = f"{hit['start_date']}..{hit['end_date']}" if hit else None

    if kind == "wordpress" or probe.is_wordpress:
        base = url if kind == "wordpress" else f"{response.url.split('/wp/')[0]}/wp" \
            if "/wp/" in response.url else f"{response.url.rstrip('/')}"
        probe_wordpress(base, probe)

    probe.verdict = verdict_for(probe)
    return probe


def verdict_for(probe: Probe) -> str:
    """A one-line judgement, so the report can be read without interpreting fields."""
    if not probe.ok:
        return f"http {probe.status} — not usable"
    if probe.parsed_events:
        material = sum(1 for e in probe.parsed_events if e["material"] == "True")
        return (
            f"USABLE — {len(probe.parsed_events)} dated meet(s) at the venue, "
            f"{material} of them material"
        )
    if probe.wp_rest_ok and probe.wp_post_count:
        return (
            f"REST works ({probe.wp_post_count} posts matched 'Green Point') but no "
            "parseable upcoming date — title format needs a look"
        )
    if probe.wp_rest_ok:
        return "REST works but the venue search matched nothing"
    if probe.has_jsonld_event:
        return "has schema.org Event markup — worth parsing directly"
    if probe.venue_mentions:
        return f"names the venue {probe.venue_mentions}x but no structured data found"
    return "reachable, nothing useful found"


def render(probes: List[Probe]) -> None:
    """Print the findings in the order a reader needs them."""
    print()
    print("=" * 78)
    print("GREEN POINT ATHLETICS STADIUM — SOURCE PROBE")
    print("=" * 78)
    for probe in probes:
        print()
        print(f"[{probe.key}] {probe.url}")
        if probe.note:
            print(f"    why: {probe.note}")
        if probe.error:
            print(f"    FAILED: {probe.error}")
            continue
        print(
            f"    http {probe.status} in {probe.elapsed_ms}ms, "
            f"{probe.bytes} bytes, {probe.content_type}"
        )
        if probe.redirected:
            print(f"    redirected to: {probe.final_url}")
        flags = []
        if probe.is_wordpress:
            flags.append("wordpress")
        if probe.wp_rest_ok:
            flags.append("wp-rest")
        if probe.has_jsonld_event:
            flags.append("json-ld Event")
        print(f"    signals: {', '.join(flags) or 'none'}; "
              f"venue named {probe.venue_mentions}x; "
              f"first date parsed: {probe.parsed_date or 'none'}")
        if probe.sample_titles:
            print("    posts matching 'Green Point':")
            for title in probe.sample_titles:
                print(f"      - {title}")
        if probe.parsed_events:
            print("    events extracted:")
            for event in probe.parsed_events:
                mark = "*" if event["material"] == "True" else " "
                print(f"      {mark} {event['start_date']}..{event['end_date']}  {event['name']}")
            print("      (* = passes the materiality filter and would be published)")
        print(f"    => {probe.verdict}")

    print()
    print("-" * 78)
    print("SUMMARY")
    for probe in probes:
        print(f"  {probe.key:22} {probe.verdict}")
    print("-" * 78)
    print(
        "\nNext step: whichever candidate reads USABLE becomes the primary source.\n"
        "If none do, the honest answer is that no machine-readable fixture list\n"
        "exists and the venue needs a different approach (see the PR description).\n"
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", metavar="PATH", help="also write the raw findings here")
    parser.add_argument(
        "--only", metavar="KEY", help="probe a single candidate by key"
    )
    args = parser.parse_args(argv)

    targets = [(c.key, c.base, c.note, c.kind) for c in CANDIDATES]
    targets += [(key, url, note, "html") for key, url, note in EXTRA_TARGETS]
    if args.only:
        targets = [t for t in targets if t[0] == args.only]
        if not targets:
            print(f"No candidate with key {args.only!r}", file=sys.stderr)
            return 2

    probes = [probe_url(key, url, note, kind) for key, url, note, kind in targets]
    render(probes)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump([asdict(p) for p in probes], handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        print(f"Raw findings written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
