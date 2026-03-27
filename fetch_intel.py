#!/usr/bin/env python3
"""
fetch_intel.py — Henter metals/gruvenyheter fra Google News RSS

Ingen API-nøkkel kreves. Søker etter nyheter om gull, sølv, kobber og geopolitikk.
Lagrer til data/geointel/intel.json.
"""
import json
import time
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = Path(__file__).parent
OUT  = BASE / "data" / "geointel" / "intel.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

CATEGORIES = [
    {
        "id":    "gold",
        "label": "Gull",
        "color": "gold",
        "query": "gold mine OR gold price OR gold reserves",
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
        "query": "mining conflict chokepoint shipping disruption metals",
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
            raw = r.read().decode("utf-8", errors="replace")
        root = ET.fromstring(raw)
        channel = root.find("channel")
        if channel is None:
            return []
        result = []
        for item in channel.findall("item")[:10]:
            title   = item.findtext("title", "").strip()
            link    = item.findtext("link", "").strip()
            source_el = item.find("source")
            source  = source_el.text.strip() if source_el is not None and source_el.text else ""
            pub_raw = item.findtext("pubDate", "")
            try:
                pub_dt = parsedate_to_datetime(pub_raw)
                pub_str = pub_dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pub_str = pub_raw[:16] if pub_raw else ""
            if not title:
                continue
            result.append({
                "title":  title,
                "url":    link,
                "source": source,
                "time":   pub_str,
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
    "updated":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "articles":   all_articles[:40],
    "categories": [{"id": c["id"], "label": c["label"], "color": c["color"]} for c in CATEGORIES],
}

with open(OUT, "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"  → {len(all_articles)} artikler totalt lagret til {OUT}")
