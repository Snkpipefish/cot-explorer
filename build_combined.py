#!/usr/bin/env python3
"""
Bygger data/combined/latest.json fra siste ukes rådata.
Leser fra data/{report}/latest.json — IKKE timeseries (historikk).
Timeseries brukes kun til COT-historikk-fanen.
"""
import json, os

BASE = os.path.expanduser("~/cot-explorer/data")
OUT  = os.path.join(BASE, "combined", "latest.json")
os.makedirs(os.path.join(BASE, "combined"), exist_ok=True)

REPORTS = ["tff", "legacy", "disaggregated", "supplemental"]

# Slå sammen alle rapporter, unngå duplikater (velg beste rapport per marked)
RAPPORT_PRIORITET = {"tff": 0, "disaggregated": 1, "legacy": 2, "supplemental": 3}

seen = {}  # market.lower() → entry

for rep in REPORTS:
    fpath = os.path.join(BASE, rep, "latest.json")
    if not os.path.exists(fpath):
        print(f"  Mangler: {fpath}")
        continue

    with open(fpath) as f:
        rows = json.load(f)

    print(f"  {rep}: {len(rows)} markeder, dato={rows[0].get('date','?') if rows else '?'}")

    for row in rows:
        market = row.get("market","").strip()
        if not market:
            continue

        mk = market.lower()
        pri = RAPPORT_PRIORITET.get(rep, 9)

        # Behold kun høyest-prioritert rapport per marked
        if mk in seen and RAPPORT_PRIORITET.get(seen[mk]["report"], 9) <= pri:
            continue

        seen[mk] = {
            "symbol":          row.get("symbol",""),
            "market":          market,
            "navn_no":         row.get("navn_no") or market,
            "kategori":        row.get("kategori","annet"),
            "report":          rep,
            "forklaring":      row.get("forklaring",""),
            "date":            row.get("date",""),
            "spekulanter":     row.get("spekulanter", {}),
            "open_interest":   row.get("open_interest", 0),
            "change_spec_net": row.get("change_spec_net", 0),
        }

result = sorted(seen.values(), key=lambda x: abs((x.get("spekulanter") or {}).get("net",0)), reverse=True)

with open(OUT, "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

dato = result[0]["date"] if result else "?"
print(f"\nOK: {len(result)} markeder → {OUT}")
print(f"COT-dato: {dato}")
