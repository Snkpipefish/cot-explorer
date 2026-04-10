#!/usr/bin/env python3
"""
fetch_comex.py — Henter COMEX lagerdata

Kilder (i prioritert rekkefølge):
  1. metalcharts.org  — JSON API, gull/sølv/kobber (daglig oppdatert)
  2. heavymetalstats.com — gull, sølv, kobber (Next.js RSC push)
  3. goldsilver.ai       — sølv (fallback)
  4. Eksisterende latest.json

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

def fetch_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

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


fetched = {}
source_used = "fallback"
report_date = None

# ── 1. metalcharts.org — JSON API (primær) ────────────────────────────
MC_BASE = "https://metalcharts.org"
MC_HEADERS = {
    "User-Agent":        HEADERS["User-Agent"],
    "X-Requested-With":  "XMLHttpRequest",
    "Accept":            "application/json",
}
MC_SYMBOLS = [
    ("XAU", "gold", "oz", "troy oz"),
    ("XAG", "silver", "oz", "troy oz"),
    ("HG",  "copper", "st", "short tons"),
]

try:
    token_data = fetch_json(f"{MC_BASE}/api/security/token", MC_HEADERS)
    MC_HEADERS["X-MC-Token"] = token_data.get("token", "")
    print(f"  metalcharts: token OK")

    for sym, metal, _, _ in MC_SYMBOLS:
        try:
            resp = fetch_json(f"{MC_BASE}/api/comex/inventory?symbol={sym}&type=latest", MC_HEADERS)
            if not resp.get("success"):
                print(f"  metalcharts {metal}: API returnerte success=false")
                continue
            d = resp.get("data", {})
            reg  = round(d.get("registered") or 0)
            elig = round(d.get("eligible") or 0)
            total = round(d.get("total") or 0)
            prev_reg = round(d.get("prevRegistered") or 0) if d.get("prevRegistered") else reg
            date = (d.get("date") or "")[:10]

            # Kobber: metalcharts sier "pounds" men verdien er faktisk short tons
            # (typisk COMEX kobber: 30K-80K st). Ingen reg/elig breakdown.
            if sym == "HG" and reg == 0 and elig == 0 and total > 0:
                prev_total = round(d.get("prevTotal") or total)
                fetched[metal] = {
                    "registered": total,  # Hele lageret (CME har fjernet reg/elig-skillet for kobber)
                    "eligible": 0,
                    "prev": prev_total,
                    "date": date,
                }
                print(f"  metalcharts {metal}: total={total:,} st dato={date}")
            else:
                fetched[metal] = {"registered": reg, "eligible": elig, "prev": prev_reg, "date": date}
                print(f"  metalcharts {metal}: registered={reg:,} eligible={elig:,} dato={date}")

            source_used = "metalcharts.org"
            report_date = date
        except Exception as e:
            print(f"  metalcharts {metal} FEIL: {e}")
except Exception as e:
    print(f"  metalcharts FEIL: {e}")

# ── 2. heavymetalstats.com (fallback) ─────────────────────────────────
if len(fetched) < 3:
    try:
        html = fetch_html("https://www.heavymetalstats.com/")
        pushes = get_rsc_pushes(html)
        print(f"  heavymetalstats: {len(pushes)} RSC-blokker funnet")

        biggest = max(pushes, key=len) if pushes else ""
        raw = biggest.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')

        data_obj = extract_json_object(raw, '{"data":{"Aluminum":')
        if data_obj:
            metals = data_obj.get("data", {})
            for metal_key, out_key in [("Gold", "gold"), ("Silver", "silver"), ("Copper", "copper")]:
                if out_key in fetched:
                    continue  # Allerede hentet fra metalcharts
                m = metals.get(metal_key, {})
                totals = m.get("totals", {})
                reg  = totals.get("registered", 0)
                elig = totals.get("eligible", 0)
                prev = m.get("previous_registered", reg)
                date = m.get("report_date") or m.get("activity_date", "")
                date = re.sub(r'^\$D', '', str(date))[:10]
                reg, elig, prev = round(reg), round(elig), round(prev)
                if reg > 0 or elig > 0:
                    fetched[out_key] = {"registered": reg, "eligible": elig, "prev": prev, "date": date}
                    print(f"  heavymetalstats {out_key}: registered={reg:,} eligible={elig:,} dato={date}")
                    if source_used == "fallback":
                        source_used = "heavymetalstats.com"
                    if not report_date:
                        report_date = date
        else:
            print("  heavymetalstats: fant ikke data i RSC-payload")
    except Exception as e:
        print(f"  heavymetalstats FEIL: {e}")

# ── 3. goldsilver.ai — sølv (fallback) ────────────────────────────────
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
    "report_date":  report_date or fetched.get("silver", {}).get("date", ""),
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
