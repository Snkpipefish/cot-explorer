#!/usr/bin/env python3
"""
Bygger data/timeseries/{symbol}_{report}.json fra data/history/
Én fil per marked med alle ukentlige datapunkter sortert kronologisk.
"""
import json, os
from datetime import datetime

BASE    = os.path.expanduser("~/cot-explorer/data")
HIST    = os.path.join(BASE, "history")
TS_DIR  = os.path.join(BASE, "timeseries")
os.makedirs(TS_DIR, exist_ok=True)

# Prioriter disaggregated > tff > legacy > supplemental for spec_net
REPORTS = ["disaggregated", "tff", "legacy", "supplemental"]

# Samle alle datapunkter per (symbol, report)
markets = {}  # key = (symbol, report) → metadata + data[]

for report in REPORTS:
    hist_dir = os.path.join(HIST, report)
    if not os.path.exists(hist_dir):
        print(f"Mangler: {hist_dir}")
        continue

    files = sorted(os.listdir(hist_dir))
    print(f"\n{report}: {len(files)} år")

    for fname in files:
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(hist_dir, fname)
        try:
            rows = json.load(open(fpath))
        except:
            continue

        for row in rows:
            sym  = row.get("symbol","").strip()
            mkt  = row.get("market","").strip()
            date = row.get("date","").strip()
            spec = row.get("spekulanter", {}) or {}
            net  = spec.get("net")
            if not sym or not mkt or not date:
                continue
            # Hopp over rader uten spec_net
            if net is None:
                continue

            key = (sym, report)
            if key not in markets:
                markets[key] = {
                    "symbol":   sym,
                    "market":   mkt,
                    "navn_no":  row.get("navn_no", mkt),
                    "kategori": row.get("kategori", "annet"),
                    "report":   report,
                    "data":     {}
                }

            # Bruk dato som nøkkel for å unngå duplikater
            markets[key]["data"][date] = {
                "date":       date,
                "spec_net":   net,
                "spec_long":  spec.get("long", 0) or 0,
                "spec_short": spec.get("short", 0) or 0,
                "oi":         row.get("open_interest", 0) or 0,
            }

# Legg til siste uke fra latest.json
for report in REPORTS:
    latest = os.path.join(BASE, report, "latest.json")
    if not os.path.exists(latest):
        continue
    try:
        rows = json.load(open(latest))
    except:
        continue
    for row in rows:
        sym  = row.get("symbol","").strip()
        mkt  = row.get("market","").strip()
        date = row.get("date","").strip()
        spec = row.get("spekulanter", {}) or {}
        net  = spec.get("net")
        if not sym or not mkt or not date or net is None:
            continue
        key = (sym, report)
        if key not in markets:
            markets[key] = {
                "symbol":   sym,
                "market":   mkt,
                "navn_no":  row.get("navn_no", mkt),
                "kategori": row.get("kategori", "annet"),
                "report":   report,
                "data":     {}
            }
        markets[key]["data"][date] = {
            "date":       date,
            "spec_net":   net,
            "spec_long":  spec.get("long", 0) or 0,
            "spec_short": spec.get("short", 0) or 0,
            "oi":         row.get("open_interest", 0) or 0,
        }

# Skriv timeseries-filer
written = 0
skipped = 0
for (sym, report), meta in markets.items():
    data_sorted = sorted(meta["data"].values(), key=lambda x: x["date"])

    # Hopp over hvis færre enn 10 datapunkter
    if len(data_sorted) < 10:
        skipped += 1
        continue

    out = {
        "symbol":   meta["symbol"],
        "market":   meta["market"],
        "navn_no":  meta["navn_no"],
        "kategori": meta["kategori"],
        "report":   report,
        "weeks":    len(data_sorted),
        "data":     data_sorted,
    }

    fname = f"{sym.lower()}_{report}.json"
    fpath = os.path.join(TS_DIR, fname)
    with open(fpath, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    written += 1

# Oppdater index.json
index = []
for (sym, report), meta in markets.items():
    n = len(meta["data"])
    if n < 10:
        continue
    index.append({
        "key":     f"{sym}_{report}",
        "symbol":  sym,
        "navn_no": meta["navn_no"],
        "market":  meta["market"],
        "kategori":meta["kategori"],
        "report":  report,
        "weeks":   n,
    })

index.sort(key=lambda x: (-x["weeks"], x["navn_no"]))
with open(os.path.join(TS_DIR, "index.json"), "w") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)

print(f"\nFerdig! {written} filer skrevet, {skipped} hoppet over (<10 uker)")
print(f"Index: {len(index)} markeder")

# Vis topp 10
print("\nTopp 10 med mest data:")
for entry in index[:10]:
    print(f"  {entry['weeks']:4d} uker  {entry['navn_no']:30s}  {entry['report']}")
