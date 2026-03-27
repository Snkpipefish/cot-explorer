#!/usr/bin/env python3
"""
fetch_intel.py — Henter metals/gruvenyheter via Google News RSS

Ingen API-nøkkel kreves. Bruker Google News RSS (samme kilde som fetch_all.py).
Lagrer til data/geointel/intel.json.
"""
import json
import time
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

BASE = Path(__file__).parent
OUT  = BASE / "data" / "geointel" / "intel.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

CATEGORIES = [
    {
        "id":    "gold",
        "label": "Gull",
        "color": "gold",
        "query": "gold mine OR gold price OR COMEX gold",
    },
    {
        "id":    "silver",
        "label": "Sølv",
        "color": "silver",
        "query": "silver mine OR silver price OR COMEX silver",
    },
    {
        "id":    "copper",
        "label": "Kobber",
        "color": "copper",
        "query": "copper mine OR copper supply OR copper price",
    },
    {
        "id":    "geopolitics",
        "label": "Geopolitikk",
        "color": "red",
        "query": "mining conflict OR strait OR shipping disruption OR chokepoint metals",
    },
]

GNEWS_BASE = "https://news.google.com/rss/search"

def fetch_category(cat):
    params = urllib.parse.urlencode({
        "q":    cat["query"],
        "hl":   "en-US",
        "gl":   "US",
        "ceid": "US:en",
    })
    url = f"{GNEWS_BASE}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
        root = ET.fromstring(raw)
        ns = {"media": "http://search.yahoo.com/mrss/"}
        items = root.findall(".//item")
        result = []
        for item in items[:10]:
            title   = (item.findtext("title") or "").strip()
            link    = item.findtext("link") or ""
            pubdate = item.findtext("pubDate") or ""
            source  = item.findtext("source") or ""
            # parse pubdate to ISO
            try:
                dt = parsedate_to_datetime(pubdate)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                time_str = pubdate[:16] if pubdate else ""
            # Google News links are redirects; extract domain from source
            domain = source.strip() if source else ""
            result.append({
                "title":  title,
                "url":    link,
                "source": domain,
                "time":   time_str,
                "cat":    cat["id"],
                "color":  cat["color"],
            })
        return result
    except Exception as e:
        print(f"  FEIL {cat['id']}: {e}")
        return []

all_articles = []
for i, cat in enumerate(CATEGORIES):
    if i > 0:
        time.sleep(2)
    print(f"  Henter {cat['label']}...")
    arts = fetch_category(cat)
    all_articles.extend(arts)
    print(f"    → {len(arts)} artikler")

# Sorter etter tid (nyeste først)
all_articles.sort(key=lambda x: x["time"], reverse=True)

result = {
    "updated":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "articles": all_articles[:40],
    "categories": [{"id": c["id"], "label": c["label"], "color": c["color"]} for c in CATEGORIES],
}

with open(OUT, "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"  → {len(all_articles)} artikler totalt lagret til {OUT}")
