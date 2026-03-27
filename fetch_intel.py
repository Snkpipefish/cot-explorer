#!/usr/bin/env python3
"""
fetch_intel.py — Henter metals/gruvenyheter fra GDELT DOC 2.0 API

Ingen API-nøkkel kreves. Søker etter nyheter om gull, sølv, kobber, gruver,
geopolitikk og metall-relevante konflikter.
Lagrer til data/geointel/intel.json.
"""
import json
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
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
        "query": "mining conflict OR chokepoint OR strait OR shipping disruption metals",
    },
]

GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"

def fetch_category(cat, retries=2):
    params = urllib.parse.urlencode({
        "query":      cat["query"],
        "mode":       "artlist",
        "maxrecords": "10",
        "format":     "json",
        "sort":       "DateDesc",
    })
    url = f"{GDELT_BASE}?{params}"
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cot-explorer/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
            if not raw.strip():
                raise ValueError("Tom respons fra GDELT")
            data = json.loads(raw)
            articles = data.get("articles", [])
            result = []
            for a in articles:
                result.append({
                    "title":   a.get("title", ""),
                    "url":     a.get("url", ""),
                    "source":  a.get("domain", ""),
                    "time":    a.get("seendate", "")[:16].replace("T", " ") if a.get("seendate") else "",
                    "lang":    a.get("language", ""),
                    "cat":     cat["id"],
                    "color":   cat["color"],
                })
            return result
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                wait = (attempt + 1) * 8
                print(f"    Rate-limit 429, venter {wait}s...")
                time.sleep(wait)
            else:
                print(f"  FEIL {cat['id']}: {e}")
                return []
        except Exception as e:
            print(f"  FEIL {cat['id']}: {e}")
            return []
    return []

all_articles = []
for i, cat in enumerate(CATEGORIES):
    if i > 0:
        time.sleep(4)
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
