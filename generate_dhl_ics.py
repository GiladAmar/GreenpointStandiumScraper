import requests
from datetime import datetime
from ics import Calendar, Event

API_URL = "https://content-dhlstadium.azurewebsites.net/api/events?filters[event][daterange][start][$gte]={}&populate[0]=event.image&populate[1]=event.daterange&populate[2]=thumbnail"

def fetch_events():
    """Fetch upcoming events from DHL Stadium API"""
    start_iso = datetime.utcnow().isoformat()
    response = requests.get(API_URL.format(start_iso))
    response.raise_for_status()
    return response.json().get("data", [])

def create_ics_file(events, output_path="dhl_stadium.ics"):
    """Create an ICS file from events"""
    cal = Calendar()
    for e in events:
        attr = e["attributes"]
        for ev in attr.get("event", []):
            for dr in ev.get("daterange", []):
                event = Event()
                event.name = ev.get("title", attr.get("title", "Untitled Event")).strip()
                event.begin = dr.get("start")
                if dr.get("end"):
                    event.end = dr.get("end")
                event.description = ev.get("description", "")
                if ev.get("externallink"):
                    event.url = ev["externallink"]
                cal.events.add(event)

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(cal)
    print(f"ICS file written to {output_path}")

if __name__ == "__main__":
    events = fetch_events()
    create_ics_file(events)