# Cape Town Stadium Events Calendar

This repository automatically updates once a month to collect upcoming events at Cape Town Stadium and publish them as a downloadable calendar.

## 📅 Subscribe to the live calendar:

```
https://raw.githubusercontent.com/GiladAmar/GreenpointStandiumScraper/refs/heads/master/dhl_stadium.ics
```

You can add this .ics link to your preferred calendar app:
- **Google Calendar**:
  
  [Add by URL](https://calendar.google.com/calendar/u/0/r/settings/addbyurl)
  
  Paste the link above when prompted.
  
- **Outlook (Web or Desktop)**:

  [Add by URL](https://support.microsoft.com/en-us/office/import-or-subscribe-to-a-calendar-in-outlook-com-or-outlook-on-the-web-503ffaf6-7b86-44fe-8dd6-8099d95f38df)
 
- **Apple Calendar (Mac/iPhone)**:
  
  [Subscribe to a calendar on Mac](https://support.apple.com/guide/calendar/subscribe-to-calendars-icl1022/mac)
  
  [Subscribe on iPhone/iPad](https://support.apple.com/en-za/guide/iphone/iph3d1110d4/ios)

✅ The calendar auto-updates twice a month — no manual refresh needed. It
subscribes as **Cape Town Traffic Events**, and entries are marked "free" so
adding it does not make you look busy.

📚 Past events stay on the calendar as a historical record. Each update keeps
previously-published events that have already happened (even once the stadium
API stops listing them) and refreshes upcoming events from the live sources, so
reschedules and cancellations are reflected while history is never lost.

💡 Perfect for staying on top of concerts, matches, and other events at the DHL Stadium.

## 📋 What the calendar gathers

The calendar aggregates events from three types of source, all of which drive
traffic and road closures around Green Point, Sea Point and the Atlantic Seaboard.

### 1. DHL Stadium events — via the official stadium API
Live events pulled straight from the DHL Stadium (Cape Town Stadium) API. Dates
update automatically as the stadium publishes them.

| Category | Examples |
|---|---|
| Rugby (URC & internationals) | DHL Stormers home games, Springboks tests |
| Football | Cape Town City FC, Stellenbosch FC home games |
| Concerts & festivals | Stadium concerts, music festivals |
| Major sporting events | HSBC SVNS Cape Town, World Supercross |
| Expos & conventions | Cycle Tour Expo, Marathon Expo, conventions |

### 2. Recurring city events — scraped from official websites
Dates are scraped from each event's official site, with a calendar-rule fallback
if the scrape fails.

| Event                                 | Typical timing | Area affected |
|---------------------------------------|---|---|
| Cape Town Cycle Tour                  | 2nd Sunday of March | CBD, Green Point, Sea Point, peninsula |
| Absa Cape Epic                        | March | Western Cape (start/finish traffic) |
| Two Oceans Marathon                   | Easter Sat–Sun | Southern suburbs, peninsula |
| Sanlam Cape Town Marathon             | Varies (May in 2026) | Green Point, Sea Point, CBD, suburbs |
| Investing in African Mining Indaba    | Early February (Mon–Thu) | Foreshore / CBD (CTICC) |
| State of the Nation Address (SONA)    | Evening, ~2nd Thursday of February | CBD (City Hall / Grand Parade / Parliament precinct) |
| Slave Route Challenge                 | ~3rd Sunday of October | CBD, District Six, Bo-Kaap, DHL Stadium |
| Cape Town Big Walk                    | Varies (recently March) | Green Point, Sea Point Promenade |
| Cape Town International Jazz Festival | Last weekend of March | Foreshore / CBD (CTICC) |
| Africa Oil Week                       | Sept–Oct | Foreshore / CBD (CTICC) |
| Africa Energy Indaba                  | Early March (Tue–Thu) | Foreshore / CBD (CTICC) |
| Enlit Africa                          | Mid-to-late May (Tue–Thu) | Foreshore / CBD (CTICC) |
| Comic Con Cape Town                   | Late-April long weekend | Foreshore / CBD (CTICC) |
| FAME Week Africa                      | Late October / early November | Foreshore / CBD (CTICC) |

### 3. Calculated recurring events — fixed calendar rules
Predictable annual events computed directly (no scrape needed).

| Event | Timing | Area affected |
|---|---|---|
| Minstrel Carnival (Kaapse Klopse) | 2 January | CBD, Bo-Kaap, Green Point |
| Cape Town Pride Parade | Last Saturday of February | Green Point, Sea Point, De Waterkant |
| Cape Town Carnival | Saturday after the Cycle Tour | Green Point / Sea Point (Fan Walk) |
| The Gun Run | 2nd Sunday of September | Green Point, Sea Point, Mouille Point |
| V&A Waterfront New Year's Eve | 31 December | Green Point Main Rd, Beach Rd, V&A |
| First Thursdays | First Thursday of every month, 16:00–23:00 | CBD |

## 🔍 How it stays honest

A calendar people subscribe to is worse than useless when it is quietly wrong,
so the build is designed to fail loudly rather than publish something broken.

- **It fails closed.** If the stadium API cannot be read, or either source comes
  back empty, or the number of upcoming events falls below half what was last
  published, the build aborts and writes nothing. The previously published
  calendar stays up until the next run rather than being replaced by a gutted
  one. (Run `python generate_dhl_ics.py --allow-shrink` to publish anyway once
  you have confirmed the drop is real.)

- **It reports its own sources.** `health.json` records, for every scraper,
  whether the date published came off the live site (`jsonld` / `title` / `text`)
  or from a calendar rule used as a fallback (`computed`), or whether there was
  no date at all (`none`). `python generate_dhl_ics.py --check-health` exits
  non-zero when a scraper that used to read a live date has stopped, and keeps
  failing every run until it recovers — the failure a fallback would otherwise
  hide indefinitely.

- **It watches for a frozen feed.** The stadium endpoint has silently stalled
  before while still answering normally. A feed whose newest event is less than
  30 days out is flagged, because a healthy one reaches months ahead.

- **Rebuilds are stable.** An event's `DTSTAMP` and `SEQUENCE` only change when
  its content does, so a rebuild that changes nothing produces an identical file
  and your calendar app does not re-notify you about events that have not moved.

Run the test suite with `python3 -m pytest test_events.py -q`; CI runs it before
every build.
