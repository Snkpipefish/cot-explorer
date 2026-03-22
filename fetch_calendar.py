#!/usr/bin/env python3
import urllib.request, json, os
from datetime import datetime, timezone, timedelta

BASE = os.path.expanduser("~/cot-explorer/data/calendar")
os.makedirs(BASE, exist_ok=True)
OUT  = os.path.join(BASE, "latest.json")

BERORTE = {
    "USD": ["EURUSD","USDJPY","GBPUSD","AUDUSD","DXY","SPX","NAS100","Gold","WTI","Brent"],
    "EUR": ["EURUSD"],
    "GBP": ["GBPUSD"],
    "JPY": ["USDJPY"],
    "AUD": ["AUDUSD"],
    "CAD": ["USDCAD"],
    "CHF": ["USDCHF"],
    "NZD": ["NZDUSD"],
}

url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = json.loads(r.read())
except Exception as e:
    print(f"FEIL: {e}")
    exit(1)

now    = datetime.now(timezone.utc)
events = []
for ev in raw:
    impact  = ev.get("impact","")
    if impact not in ("High","Medium"):
        continue
    country  = ev.get("country","")
    title    = ev.get("title","")
    date_str = ev.get("date","")
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
    except:
        continue
    cet = dt_utc + timedelta(hours=1)
    events.append({
        "date":       dt_utc.isoformat(),
        "cet":        cet.strftime("%a %d.%m %H:%M"),
        "title":      title,
        "country":    country,
        "impact":     impact,
        "forecast":   ev.get("forecast",""),
        "previous":   ev.get("previous",""),
        "berorte":    BERORTE.get(country, []),
        "hours_away": round((dt_utc - now).total_seconds()/3600, 1),
    })

events.sort(key=lambda x: x["date"])
out = {"updated": now.isoformat(), "events": events}
with open(OUT,"w") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"Lagret {len(events)} events ({sum(1 for e in events if e['impact']=='High')} High)")
for e in events[:8]:
    print(f"  {e['cet']:18s} {e['country']:4s} [{e['impact']:6s}] {e['title'][:40]}")
