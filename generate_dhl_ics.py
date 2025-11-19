from datetime import datetime, timedelta
from ics import Calendar, Event
import requests
from typing import List, Any
from dateutil import parser as date_parser

url = "https://content-dhlstadium.azurewebsites.net/api/events?filters[event][daterange][start][$gte]=2025-09-21T14:39:46.411Z&populate[0]=event.image&populate[1]=event.daterange&populate[2]=thumbnail"
resp = requests.get(url).json()

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
            start_dt = dt.replace(hour=16, minute=0, second=0)
            end_dt = dt.replace(hour=23, minute=0, second=0)
            event = Event()
            event.name = "First Thursdays"
            event.begin = start_dt
            event.end = end_dt
            event.description = "Monthly art and culture event in Cape Town."
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
                    event.end = start_dt.replace(hour=23, minute=59, second=59)
                else:
                    event.end = end
                event.name = ev.get("title", "No title")
                event.description = ev.get("description", "")
                events.append(event)
    return events

def get_event_start_dt(event: Event) -> datetime:
    """Return the event's start datetime as a datetime object."""
    begin = event.begin
    if hasattr(begin, 'datetime'):
        return begin.datetime
    if isinstance(begin, datetime):
        return begin
    if isinstance(begin, str):
        # Try parsing ISO format
        try:
            return date_parser.parse(begin)
        except Exception:
            return datetime.max
    return datetime.max

cal: Calendar = Calendar()

now: int = datetime.now().year
all_events: List[Event] = get_api_events(resp) + add_first_thursdays([now, now+1])
# Sort events by start datetime robustly
all_events.sort(key=get_event_start_dt)
for event in all_events:
    cal.events.add(event)

with open("dhl_stadium.ics", "w") as f:
    f.write(str(cal))
