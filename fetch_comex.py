#!/usr/bin/env python3
"""
fetch_comex.py — Henter COMEX lagerdata fra CME Group

Prøver å hente warehouse stock-rapport fra CME Group.
Ved feil beholdes eksisterende verdier i latest.json (kun dato oppdateres).
Lagrer til data/comex/latest.json.

Stress-indeks 0–100:
  - Basert på andel registered av total (lav = mer stress)
  - Pluss trendkomponent: synkende registered flere uker = +stress
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
OUT  = BASE / "data" / "comex" / "latest.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

# Les eksisterende verdier som fallback
existing = {}
if OUT.exists():
    try:
        with open(OUT) as f:
            existing = json.load(f)
    except Exception:
        pass

def stress(registered, total, prev_registered):
    """Beregn stress-indeks 0-100."""
    if total <= 0:
        return 50
    coverage = registered / total
    # Basis fra dekning: lav dekning = høy stress
    base = (1.0 - coverage) * 80
    # Trendkomponent: faller = +10 stress, stiger = -5
    if prev_registered and prev_registered > 0:
        chg_pct = (registered - prev_registered) / prev_registered
        if chg_pct < -0.05:
            base += 15
        elif chg_pct < 0:
            base += 5
        elif chg_pct > 0.05:
            base -= 5
    return round(max(0, min(100, base)), 1)

# ── Forsøk CME API ────────────────────────────────────────────────
# CME Group WRS (Warehouse Receipt System) daglige rapport-endepunkter
# reportId: 165=Gold, 166=Silver, 168=Copper
CME_REPORTS = {
    "gold":   165,
    "silver": 166,
    "copper": 168,
}

fetched = {}
for metal, report_id in CME_REPORTS.items():
    url = (f"https://www.cmegroup.com/CmeWS/mvc/WR/detail?"
           f"reportId={report_id}&tradeDate="
           f"{datetime.now(timezone.utc).strftime('%Y%m%d')}")
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent":  "Mozilla/5.0 (X11; Linux x86_64)",
                "Accept":      "application/json",
                "Referer":     "https://www.cmegroup.com/",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        # Prøv å parse registered/eligible totals fra CME response
        rows = data.get("items") or data.get("rows") or []
        reg = elig = 0
        for row in rows:
            # CME-format varierer; prøv vanlige feltnavn
            for k in ("registered", "Registered", "REGISTERED"):
                if k in row:
                    try:
                        reg += int(str(row[k]).replace(",", ""))
                    except ValueError:
                        pass
            for k in ("eligible", "Eligible", "ELIGIBLE"):
                if k in row:
                    try:
                        elig += int(str(row[k]).replace(",", ""))
                    except ValueError:
                        pass
        if reg > 0 or elig > 0:
            fetched[metal] = {"registered": reg, "eligible": elig}
            print(f"  CME {metal}: registered={reg:,} eligible={elig:,}")
        else:
            print(f"  CME {metal}: ingen data å parse (beholder eksisterende)")
    except Exception as e:
        print(f"  CME {metal} FEIL: {e}")

# ── Bygg output ───────────────────────────────────────────────────
def oz_block(metal_key, fetched_data, existing_data, unit_key, unit_label):
    ex = existing_data.get(metal_key, {})
    if metal_key in fetched_data:
        f   = fetched_data[metal_key]
        reg = f["registered"]
        elig = f["eligible"]
    else:
        reg  = ex.get(f"registered_{unit_key}", 0)
        elig = ex.get(f"eligible_{unit_key}", 0)
    total = reg + elig
    prev  = ex.get(f"registered_{unit_key}", reg)
    cov   = round((reg / total * 100) if total else 0, 1)
    return {
        f"registered_{unit_key}": reg,
        f"eligible_{unit_key}":   elig,
        f"total_{unit_key}":      total,
        f"registered_prev_{unit_key}": prev,
        f"change_{unit_key}":     reg - prev,
        "coverage_pct":           cov,
        "unit":                   unit_label,
    }

gold_block   = oz_block("gold",   fetched, existing, "oz", "troy oz")
silver_block = oz_block("silver", fetched, existing, "oz", "troy oz")
copper_block = oz_block("copper", fetched, existing, "st", "short tons")

gold_stress   = stress(gold_block["registered_oz"],   gold_block["total_oz"],   gold_block["registered_prev_oz"])
silver_stress = stress(silver_block["registered_oz"], silver_block["total_oz"], silver_block["registered_prev_oz"])
copper_stress = stress(copper_block["registered_st"], copper_block["total_st"], copper_block["registered_prev_st"])

result = {
    "updated":      datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "source":       "CME Group" if fetched else "fallback",
    "gold":         gold_block,
    "silver":       silver_block,
    "copper":       copper_block,
    "stress_index": {
        "gold":   gold_stress,
        "silver": silver_stress,
        "copper": copper_stress,
        "note":   "0=ingen stress, 100=ekstremt stress. Lav registered-dekning + synkende trend øker stress.",
    }
}

with open(OUT, "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"  → {OUT}")
