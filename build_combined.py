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
# Finansielle markeder: TFF (hedge funds/asset managers) er mest granulært
# Landbruk/råvarer: Disaggregated (Managed Money + Produsenter) er riktigere
RAPPORT_PRIORITET_DEFAULT  = {"tff": 0, "disaggregated": 1, "legacy": 2, "supplemental": 3}
RAPPORT_PRIORITET_LANDBRUK = {"disaggregated": 0, "supplemental": 1, "legacy": 2, "tff": 3}

def _get_priority(report_id, kategori):
    if kategori == "landbruk":
        return RAPPORT_PRIORITET_LANDBRUK.get(report_id, 9)
    return RAPPORT_PRIORITET_DEFAULT.get(report_id, 9)

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
        kategori = row.get("kategori", "annet")
        pri = _get_priority(rep, kategori)

        # Behold kun høyest-prioritert rapport per marked
        if mk in seen and _get_priority(seen[mk]["report"], seen[mk].get("kategori","annet")) <= pri:
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

# Berik hvert marked med spec_net-historikk fra timeseries (siste 8 uker) for sparkline
ts_dir = os.path.join(BASE, "timeseries")
enriched = 0
for entry in result:
    sym = entry.get("symbol", "")
    rep = entry.get("report", "")
    ts_file = os.path.join(ts_dir, f"{sym}_{rep}.json")
    if not os.path.exists(ts_file):
        continue
    try:
        with open(ts_file) as f:
            ts_data = json.load(f)
        weeks = [d["spec_net"] for d in ts_data.get("data", [])[-8:] if d.get("spec_net") is not None]
        entry["spec_net_history"] = weeks
        enriched += 1
    except Exception:
        pass

print(f"  Sparkline-historikk beriket: {enriched}/{len(result)} markeder")

with open(OUT, "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

dato = result[0]["date"] if result else "?"
print(f"\nOK: {len(result)} markeder → {OUT}")
print(f"COT-dato: {dato}")
