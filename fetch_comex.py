#!/usr/bin/env python3
"""
fetch_comex.py — Henter COMEX lagerdata

Kilder (i prioritert rekkefølge):
  1. heavymetalstats.com — gull, sølv, kobber (Next.js RSC push #12)
  2. goldsilver.ai       — sølv (fallback / historikk)
  3. Eksisterende latest.json

Stress-indeks 0–100:
  - Basert på andel registered av total (lav = mer stress)
  - Pluss trendkomponent: synkende registered = +stress
"""
import json, re, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
OUT  = BASE / "data" / "comex" / "latest.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

existing = {}
if OUT.exists():
    try:
        with open(OUT) as f:
            existing = json.load(f)
    except Exception:
        pass

def stress(registered, total, prev_registered):
    if total <= 0:
        return 50
    coverage = registered / total
    base = (1.0 - coverage) * 80
    if prev_registered and prev_registered > 0:
        chg_pct = (registered - prev_registered) / prev_registered
        if chg_pct < -0.05:
            base += 15
        elif chg_pct < 0:
            base += 5
        elif chg_pct > 0.05:
            base -= 5
    return round(max(0, min(100, base)), 1)

def fetch_html(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="ignore")

def extract_json_object(text, start_pattern):
    """Finn og ekstraher et komplett JSON-objekt fra en streng via brace-matching."""
    idx = text.find(start_pattern)
    if idx == -1:
        return None
    depth, start = 0, idx
    for i, ch in enumerate(text[idx:], idx):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except Exception:
                    return None
    return None

def get_rsc_pushes(html):
    """Hent alle RSC push-blokker fra Next.js HTML."""
    return re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.DOTALL)

# ── 1. heavymetalstats.com ────────────────────────────────────────────
fetched = {}
source_used = "fallback"
hms_date = None

try:
    html = fetch_html("https://www.heavymetalstats.com/")
    pushes = get_rsc_pushes(html)
    print(f"  heavymetalstats: {len(pushes)} RSC-blokker funnet")

    # Finn den største push-blokken (inneholder all data)
    biggest = max(pushes, key=len) if pushes else ""
    raw = biggest.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')

    data_obj = extract_json_object(raw, '{"data":{"Aluminum":')
    if data_obj:
        metals = data_obj.get("data", {})
        for metal_key, out_key in [("Gold", "gold"), ("Silver", "silver"), ("Copper", "copper")]:
            m = metals.get(metal_key, {})
            totals = m.get("totals", {})
            reg  = totals.get("registered", 0)
            elig = totals.get("eligible", 0)
            prev = m.get("previous_registered", reg)
            date = m.get("report_date") or m.get("activity_date", "")
            if reg > 0 or elig > 0:
                fetched[out_key] = {"registered": reg, "eligible": elig, "prev": prev, "date": date}
                print(f"  heavymetalstats {out_key}: registered={reg:,} eligible={elig:,} dato={date}")
                source_used = "heavymetalstats.com"
                hms_date = date
        if not fetched:
            print("  heavymetalstats: JSON funnet men ingen metalldata")
    else:
        print("  heavymetalstats: fant ikke {'data':{'Aluminum':...}} i RSC-payload")
except Exception as e:
    print(f"  heavymetalstats FEIL: {e}")

# ── 2. goldsilver.ai — sølv (fallback eller supplement) ───────────────
if "silver" not in fetched:
    try:
        html = fetch_html("https://goldsilver.ai/metal-prices/comex-silver")
        pushes = get_rsc_pushes(html)
        dates, numbers = [], []
        for chunk in pushes:
            chunk = chunk.replace('\\"', '"').replace('\\n', '\n')
            for m in re.finditer(r'\[("202\d-\d{2}-\d{2}"(?:,"202\d-\d{2}-\d{2}")+)\]', chunk):
                arr = [d.strip('"') for d in m.group(1).split(",")]
                if len(arr) >= 10:
                    dates.append(arr)
            for m in re.finditer(r'\[(\d+(?:,\d+){9,})\]', chunk):
                arr = [int(x) for x in m.group(1).split(",")]
                if len(arr) >= 10:
                    numbers.append(arr)
        if dates and len(numbers) >= 2:
            reg  = numbers[0][-1]
            elig = numbers[1][-1]
            date = dates[0][-1]
            fetched["silver"] = {"registered": reg, "eligible": elig, "prev": reg, "date": date}
            print(f"  goldsilver.ai silver: registered={reg:,} eligible={elig:,} dato={date}")
            if source_used == "fallback":
                source_used = "goldsilver.ai"
        else:
            print("  goldsilver.ai silver: ikke nok data å parse")
    except Exception as e:
        print(f"  goldsilver.ai silver FEIL: {e}")

# ── Bygg output ───────────────────────────────────────────────────────
def oz_block(metal_key, fetched_data, existing_data, unit_key, unit_label):
    ex = existing_data.get(metal_key, {})
    if metal_key in fetched_data:
        f    = fetched_data[metal_key]
        reg  = f["registered"]
        elig = f["eligible"]
        prev = f.get("prev", ex.get(f"registered_{unit_key}", reg))
    else:
        reg  = ex.get(f"registered_{unit_key}", 0)
        elig = ex.get(f"eligible_{unit_key}", 0)
        prev = ex.get(f"registered_prev_{unit_key}", reg)
    total = reg + elig
    cov   = round((reg / total * 100) if total else 0, 1)
    return {
        f"registered_{unit_key}":      reg,
        f"eligible_{unit_key}":        elig,
        f"total_{unit_key}":           total,
        f"registered_prev_{unit_key}": prev,
        f"change_{unit_key}":          reg - prev,
        "coverage_pct":                cov,
        "unit":                        unit_label,
    }

gold_block   = oz_block("gold",   fetched, existing, "oz", "troy oz")
silver_block = oz_block("silver", fetched, existing, "oz", "troy oz")
copper_block = oz_block("copper", fetched, existing, "st", "short tons")

result = {
    "updated":      datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "source":       source_used,
    "report_date":  hms_date or fetched.get("silver", {}).get("date", ""),
    "gold":         gold_block,
    "silver":       silver_block,
    "copper":       copper_block,
    "stress_index": {
        "gold":   stress(gold_block["registered_oz"],   gold_block["total_oz"],   gold_block["registered_prev_oz"]),
        "silver": stress(silver_block["registered_oz"], silver_block["total_oz"], silver_block["registered_prev_oz"]),
        "copper": stress(copper_block["registered_st"], copper_block["total_st"], copper_block["registered_prev_st"]),
        "note":   "0=ingen stress, 100=ekstremt stress. Lav registered-dekning + synkende trend øker stress.",
    }
}

with open(OUT, "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"  → {OUT}  (kilde: {source_used})")
