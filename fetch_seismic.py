#!/usr/bin/env python3
"""
fetch_seismic.py — Henter jordskjelvdata fra USGS for gruveregioner

Ingen API-nøkkel kreves. Henter M >= 4.5 siste 7 dager globalt,
filtrerer på relevante gruveregioner og lagrer til data/geointel/seismic.json.
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
OUT  = BASE / "data" / "geointel" / "seismic.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"

# Gruveregioner: (navn, min_lat, max_lat, min_lon, max_lon)
MINE_REGIONS = [
    ("Chile / Peru",         -40.0,  -14.0, -76.0, -62.0),
    ("Mexico / Mellom-Amerika", 14.0,  32.0, -117.0, -85.0),
    ("USA / Canada",          30.0,   70.0, -130.0, -60.0),
    ("DRC / Zambia",          -15.0,   5.0,   22.0,  35.0),
    ("Sør-Afrika",            -34.0,  -22.0,   16.0,  33.0),
    ("Mongolia / Kina",        38.0,   52.0,   88.0, 122.0),
    ("Indonesia / Papua",      -8.0,    2.0,  130.0, 145.0),
    ("Australia",             -42.0,  -10.0,  113.0, 154.0),
    ("Russland / Sibir",       50.0,   72.0,   60.0, 140.0),
    ("Øst-Afrika",            -10.0,   15.0,   25.0,  45.0),
]

def in_mine_region(lat, lon):
    for name, mlat, xlat, mlon, xlon in MINE_REGIONS:
        if mlat <= lat <= xlat and mlon <= lon <= xlon:
            return name
    return None

print("Henter USGS jordskjelvdata...")
try:
    req = urllib.request.Request(USGS_URL, headers={"User-Agent": "cot-explorer/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
except urllib.error.URLError as e:
    print(f"  FEIL USGS: {e}")
    data = {"features": []}

events = []
for feat in data.get("features", []):
    props = feat.get("properties", {})
    geom  = feat.get("geometry", {})
    coords = geom.get("coordinates", [None, None, None])
    if len(coords) < 2 or coords[0] is None:
        continue
    lon, lat = coords[0], coords[1]
    depth = coords[2] if len(coords) > 2 else None
    mag   = props.get("mag")
    if mag is None or mag < 4.5:
        continue
    region = in_mine_region(lat, lon)
    ts = props.get("time")
    iso = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else ""
    events.append({
        "id":       feat.get("id", ""),
        "mag":      round(mag, 1),
        "lat":      round(lat, 3),
        "lon":      round(lon, 3),
        "depth_km": round(depth, 1) if depth is not None else None,
        "place":    props.get("place", ""),
        "time":     iso,
        "region":   region,
        "url":      props.get("url", ""),
    })

# Sorter etter magnitude (sterkest først)
events.sort(key=lambda x: x["mag"], reverse=True)

mine_events = [e for e in events if e["region"]]
all_events  = events[:50]  # maks 50 totalt

result = {
    "updated":      datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "total":        len(data.get("features", [])),
    "mine_region":  mine_events,
    "all":          all_events,
}

with open(OUT, "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"  → {len(mine_events)} jordskjelv i gruveregioner / {len(all_events)} totalt lagret")
print(f"  → {OUT}")
