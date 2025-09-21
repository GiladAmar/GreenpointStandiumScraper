from datetime import datetime, timedelta
from ics import Calendar, Event
import requests

url = "https://content-dhlstadium.azurewebsites.net/api/events?filters[event][daterange][start][$gte]=2025-09-21T14:39:46.411Z&populate[0]=event.image&populate[1]=event.daterange&populate[2]=thumbnail"
resp = requests.get(url).json()

cal = Calendar()

for item in resp.get("data", []):
    for ev in item["attributes"]["event"]:
        for dr in ev.get("daterange", []):
            event = Event()
            start = dr.get("start")
            end = dr.get("end")

            if start:
                event.begin = start
            # if end is missing or end <= start, set to midnight of the start day
            if not end or end <= start:
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                # set end to midnight of the same day (23:59:59)
                event.end = start_dt.replace(hour=23, minute=59, second=59)
            else:
                event.end = end

            event.name = ev.get("title", "No title")
            event.description = ev.get("description", "")
            cal.events.add(event)

# write to file
with open("dhl_stadium.ics", "w") as f:
    f.writelines(cal)