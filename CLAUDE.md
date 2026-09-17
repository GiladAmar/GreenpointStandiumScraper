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

1. **When adding or changing a scraper, look at the real page HTML and confirm the parser
   actually works.** Don't rely on the computed fallback masking a broken scrape. Fetch the
   target page (or its JSON-LD), verify `scrape_event_date`/regex extracts the correct date,
   and add a test that feeds representative mock HTML (see `SCRAPE_SAMPLES` in
   `test_events.py`) asserting the extracted date — plus a date-rule test for any computed
   fallback. Also confirm API shapes (e.g. Strapi pagination — always follow `pageCount`,
   never assume one page).

2. **Use South African time.** All datetimes use `SAST = ZoneInfo("Africa/Johannesburg")`
   (defined in both modules). Timed events carry SAST tzinfo; all-day events use
   `VALUE=DATE` with an exclusive (`+1 day`) end. Never emit naïve/UTC-local times to the
   calendar.

3. **Every event should carry a description and a source URL when possible.** Add a
   traffic-focused blurb to `EVENT_DESCRIPTIONS` (why it affects Green Point/CBD/seaboard),
   set `url` (and `location` where known), and in the ICS use `apply_link()` so clients get
   both a clickable `URL` and an inline link. When merging/regenerating, carry these fields
   over rather than dropping them.

## Gotchas
- Scrapers guard with `is_recent_date()` (this year or next) **and** a future-date check, so
  a stale prior edition isn't picked up.
- Scrape-only events (no dependable recurrence) return name-only when the scrape fails and
  are intentionally left off the calendar rather than inventing a date.
- Events are Cape Town / seaboard only — don't add out-of-town events (e.g. Knysna was
  removed for this reason).
