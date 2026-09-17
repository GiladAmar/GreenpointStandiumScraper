# CLAUDE.md

Guidance for working in this repo. It scrapes/computes Cape Town events that disrupt
CBD / Green Point / Atlantic-seaboard traffic and publishes them as `dhl_stadium.ics`.

## Layout
- `test.py` — despite the name, this is the **city-event scraper** (not tests). Each
  `fetch_*` returns `{name, url, start_date, end_date, description?, location?}` and is
  registered in `fetch_all_events()`. Computed date rules live in the `*_date(s)` helpers;
  shared scraping in `scrape_event_date()`, `fetch_site()`, `generic_date_hunt()`,
  `jsonld_event_dates()`. Blurbs in `EVENT_DESCRIPTIONS`.
- `generate_dhl_ics.py` — builds the ICS. Pulls the DHL Stadium API (`fetch_stadium_api`,
  paginated), adds First Thursdays + `test.py` events, then `merge_events()` preserves past
  events from the existing file. Entry point is `main()` (guarded by `__main__`).
- `test_events.py` — pytest suite. Run: `python3 -m pytest test_events.py -q`.
- CI (`.github/workflows/update_icl.yml`) runs `generate_dhl_ics.py` on the 1st & 15th and
  commits the regenerated `.ics`. Tests are **not** run in CI — run them locally.

## Conventions (keep to these)

1. **Download the real page HTML and confirm the parser actually works — for existing
   scrapers, not just new ones.** Don't rely on a computed fallback masking a broken scrape
   (a scraper can silently fall back forever while the site has moved or its date has
   drifted). When testing a feature, audit the current scrapers too:
   - Run each fetcher and note what it returns (scraped date vs computed fallback).
   - Fetch each target page (`test.safe_get(url)` for the exact bytes the scraper sees, and
     WebFetch for the human-rendered view) and read the real date on the site.
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
   (defined in both modules). Timed events carry SAST tzinfo; all-day events use
   `VALUE=DATE` with an exclusive (`+1 day`) end. Never emit naïve/UTC-local times to the
   calendar.

3. **Every event should carry a description and a source URL when possible.** Add a
   traffic-focused blurb to `EVENT_DESCRIPTIONS` (why it affects Green Point/CBD/seaboard),
   set `url` (and `location` where known), and in the ICS use `apply_link()` so clients get
   both a clickable `URL` and an inline link. When merging/regenerating, carry these fields
   over rather than dropping them.

4. **Each development session, reconcile the stadium events against the live site.**
   Compare what the stadium source produces against <https://www.dhlstadium.co.za/events>
   (the site is a JS SPA, so read events from its API, `api.dhlstadium.co.za/api/events`,
   with `populate[…]=event.daterange` etc., not the raw HTML). If a fixture on the site is
   missing or wrong in the calendar, fix the scraper. The endpoint has silently moved and
   frozen before (`content-dhlstadium.azurewebsites.net` stalled at Aug 2026), so also
   sanity-check that the API's newest event isn't suspiciously close to "today" — a sign it
   has gone stale and the site has moved to a new host again.

## Gotchas
- Scrapers guard with `is_recent_date()` (this year or next) **and** a future-date check, so
  a stale prior edition isn't picked up.
- Scrape-only events (no dependable recurrence) return name-only when the scrape fails and
  are intentionally left off the calendar rather than inventing a date.
- Events are Cape Town / seaboard only — don't add out-of-town events (e.g. Knysna was
  removed for this reason).
