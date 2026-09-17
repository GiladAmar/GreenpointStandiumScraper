# CLAUDE.md

Guidance for working in this repo. It scrapes/computes Cape Town events that disrupt
CBD / Green Point / Atlantic-seaboard traffic and publishes them as `dhl_stadium.ics`.

## Layout
- `city_events.py` — the **city-event scraper**. Each `fetch_*` returns
  `{name, url, source, start_date?, end_date?, description?, location?}` and is registered
  in `EXTRACTORS`. Computed date rules live in the `*_date(s)` helpers and are applied by
  `next_computed()`; scrape-then-fall-back events go through `_scrape_then_rule()`. Shared
  scraping in `scrape_event_date()`, `fetch_site()`, `generic_date_hunt()`,
  `jsonld_event_dates()`. Blurbs in `EVENT_DESCRIPTIONS`.
- `generate_dhl_ics.py` — builds the ICS. Pulls the DHL Stadium API (`fetch_stadium_api`,
  paginated), adds `city_events.py` events, deduplicates across the two sources
  (`dedupe_events`), checks the result is safe to publish (`check_regression`), then
  `merge_events()` preserves past events from the existing file and `stamp_events()`
  assigns UID/DTSTAMP/SEQUENCE. Entry point is `main()` (guarded by `__main__`).
- `test_events.py` — pytest suite. Run: `python3 -m pytest test_events.py -q`.
- Outputs, all regenerated and committed by each run: `dhl_stadium.ics` (the calendar),
  `events.json` (the raw scrape) and `health.json` (per-source provenance, including
  `last_live` — when each scraper last read a real date — plus anything degraded).
- CI (`.github/workflows/update_icl.yml`) runs the tests, then `generate_dhl_ics.py` on the
  1st & 15th, commits the three outputs, and finally runs `--check-health`.

## Conventions (keep to these)

1. **Confirm the parser actually works against the real page — for existing scrapers, not
   just new ones.** A scraper can silently fall back to its computed rule forever while the
   site has moved or its date has drifted. `health.json` now does most of this watching for
   you: every record carries a `source` (`jsonld` / `title` / `text` / `computed` / `none`),
   and `--check-health` fails the workflow, every run until it recovers, when one that
   used to read a live date stops doing so. That comparison is against each source's
   `last_live`, not against the previous run: the workflow commits the report it just
   wrote, so a pairwise diff would alarm once and then accept broken as the new normal.
   When you touch a scraper, still:
   - Run the fetcher and check `source` is what you expect, not just that a date came back.
   - Fetch the target page (`city_events.safe_get(url)` for the exact bytes the scraper
     sees, and WebFetch for the human-rendered view) and read the real date on the site.
   - Compare the two. Watch for: **URL drift** (301 redirects, moved/rebranded domains,
     expired/mismatched TLS certs, dead domains — check with `requests.get`), a page that
     defaults to the *wrong* edition (e.g. Comic Con's root shows Johannesburg, not Cape
     Town), and dates that have moved off the month a regex assumed (the marathon left
     October). Fix the URL/parser/rule as needed; leave scrape-only events off-calendar
     rather than publishing a wrong or duplicated date.
   - Add a test feeding representative mock HTML (see `SCRAPE_SAMPLES` in `test_events.py`)
     asserting the extracted date, plus a date-rule test for any computed fallback.
   - Confirm API shapes too (e.g. Strapi pagination — always follow `pageCount`, never
     assume one page), and periodically re-check every reference/"More info" URL is alive.

2. **Use South African time.** All datetimes use `SAST = ZoneInfo("Africa/Johannesburg")`
   (defined in both modules). Timed events are written with `TZID=Africa/Johannesburg`
   against the `VTIMEZONE` the calendar carries; all-day events use `VALUE=DATE` with an
   exclusive (`+1 day`) end. Never emit naïve times to the calendar.

3. **Every event should carry a description and a source URL when possible.** Add a
   traffic-focused blurb to `EVENT_DESCRIPTIONS` (why it affects Green Point/CBD/seaboard),
   set `url` (and `location` where known). `CalEvent` keeps the blurb and the link separate;
   `render_description()` appends the link line at write time so clients get both a
   clickable `URL` and an inline one, and `split_description()` takes it back off on read.
   When merging/regenerating, carry these fields over rather than dropping them.

4. **Each development session, reconcile the stadium events against the live site.**
   Compare what the stadium source produces against <https://www.dhlstadium.co.za/events>
   (the site is a JS SPA, so read events from its API, `api.dhlstadium.co.za/api/events`,
   with `populate[…]=event.daterange` etc., not the raw HTML). If a fixture on the site is
   missing or wrong in the calendar, fix the scraper. The endpoint has silently moved and
   frozen before (`content-dhlstadium.azurewebsites.net` stalled at Aug 2026);
   `check_stadium_horizon()` now flags a feed whose newest event is less than 30 days out,
   but it only catches a feed that has stopped moving — a feed that has moved *host* still
   needs a human to notice the site and the calendar disagree.

5. **Never change the UID scheme, and keep the calendar consistent with it.**
   `make_uid()` hashes `name|start-date`, the start date being the SAST calendar day
   however the event is expressed. A different scheme hands every existing subscriber a
   duplicate of every event. `test_every_published_event_uid_matches_the_scheme` asserts
   the invariant `uid == make_uid(name, start)` holds for every event in the published
   file — if you ever have to change the scheme, regenerate the whole calendar in the same
   commit, or preserved past events inside the API look-back will be published twice. If a
   name must change, prefer a `CANONICAL_NAMES` entry over editing the name at the source,
   and expect the UID to move with it.

## Gotchas
- **The build fails closed.** `check_regression()` refuses to publish when either source
  comes back empty or upcoming events drop below half the previously published count, and
  `fetch_stadium_api()` raises rather than returning nothing. A refused build writes no
  files, so the last good calendar stays up. Use `--allow-shrink` once you have confirmed a
  drop is genuine.
- Scrapers guard with `is_recent_date()` (this year or next) **and** an end-date check
  (`_is_upcoming()`), so neither a stale prior edition nor a finished current one is picked
  up. `next_computed()` rolls over on the *end* date, so an event stays on the calendar
  while it is running.
- Scrape-only events (no dependable recurrence) return name-only when the scrape fails and
  are intentionally left off the calendar rather than inventing a date.
- `dedupe_events()` collapses the same event arriving from both sources (the Gun Run is on
  the stadium feed under its sponsor name and in the city scrapers under its own) and
  consecutive days of one tournament. Add an alias to `CANONICAL_NAMES` when a new pair
  turns up; the window is 7 days.
- DTSTAMP/SEQUENCE only change when an event's content does (`fingerprint()`), so a rebuild
  that changes nothing is byte-identical. If you add a field a subscriber can see, add it to
  the fingerprint too.
- Events are Cape Town / seaboard only — don't add out-of-town events (e.g. Knysna was
  removed for this reason).
