#!/usr/bin/env python3
"""
Python-port av FluidTrades SMC Lite (Pine Script → Python)
Beregner: Swing H/L, HH/LH/HL/LL, Supply/Demand soner, POI, BOS
"""

def calc_atr(rows, n=50):
    if len(rows) < n+1: return None
    trs = [max(rows[i][0]-rows[i][1],
               abs(rows[i][0]-rows[i-1][2]),
               abs(rows[i][1]-rows[i-1][2]))
           for i in range(1, len(rows))]
    return sum(trs[-n:]) / n

def find_pivot_highs(rows, length=10):
    """
    Pivot high: høy[i] er høyest av alle høyder i vindu [i-length : i+length]
    Returnerer liste av (index, verdi)
    """
    pivots = []
    for i in range(length, len(rows)-length):
        window = [rows[j][0] for j in range(i-length, i+length+1)]
        if rows[i][0] == max(window):
            pivots.append((i, rows[i][0]))
    return pivots

def find_pivot_lows(rows, length=10):
    """
    Pivot low: lav[i] er lavest av alle lave i vindu [i-length : i+length]
    """
    pivots = []
    for i in range(length, len(rows)-length):
        window = [rows[j][1] for j in range(i-length, i+length+1)]
        if rows[i][1] == min(window):
            pivots.append((i, rows[i][1]))
    return pivots

def classify_swings(pivots, swing_type):
    """
    Klassifiser swing-punkter som HH/LH (for highs) eller HL/LL (for lows)
    swing_type: 'high' eller 'low'
    Returnerer liste av (index, verdi, label)
    """
    result = []
    for i, (idx, val) in enumerate(pivots):
        if i == 0:
            result.append((idx, val, "HH" if swing_type=="high" else "HL"))
            continue
        prev_val = pivots[i-1][1]
        if swing_type == "high":
            label = "HH" if val >= prev_val else "LH"
        else:
            label = "HL" if val >= prev_val else "LL"
        result.append((idx, val, label))
    return result

def build_supply_demand_zones(pivot_highs, pivot_lows, rows, atr,
                               box_width=2.5, history=20):
    """
    Bygg supply/demand soner fra pivot highs/lows.
    Supply: ved pivot high — top = high, bottom = high - atr_buffer
    Demand: ved pivot low  — bottom = low,  top = low + atr_buffer
    Sjekk overlapping: ikke tegn hvis ny POI er innen 2×ATR fra eksisterende.
    Returnerer lister av soner: [{"top","bottom","poi","idx","type","status"}]
    """
    atr_buffer  = atr * (box_width / 10)
    atr_overlap = atr * 2
    curr        = rows[-1][2]

    supply_zones = []
    demand_zones = []

    def overlapping(new_poi, zones):
        for z in zones:
            if abs(new_poi - z["poi"]) <= atr_overlap:
                return True
        return False

    # Supply soner fra pivot highs
    for idx, val in pivot_highs[-history:]:
        top    = val
        bottom = val - atr_buffer
        poi    = (top + bottom) / 2
        if not overlapping(poi, supply_zones):
            supply_zones.append({
                "top":    round(top, 5),
                "bottom": round(bottom, 5),
                "poi":    round(poi, 5),
                "idx":    idx,
                "type":   "supply",
                "status": "intakt",
            })

    # Demand soner fra pivot lows
    for idx, val in pivot_lows[-history:]:
        bottom = val
        top    = val + atr_buffer
        poi    = (top + bottom) / 2
        if not overlapping(poi, demand_zones):
            demand_zones.append({
                "top":    round(top, 5),
                "bottom": round(bottom, 5),
                "poi":    round(poi, 5),
                "idx":    idx,
                "type":   "demand",
                "status": "intakt",
            })

    return supply_zones, demand_zones

def detect_bos(supply_zones, demand_zones, rows):
    """
    BOS: når close lukker GJENNOM en sone blir den en BOS-linje.
    Supply BOS: close >= top → brutt oppover
    Demand BOS: close <= bottom → brutt nedover
    Returnerer oppdaterte soner + liste av BOS-nivåer.
    """
    bos_levels = []

    for z in supply_zones:
        for i in range(z["idx"]+1, len(rows)):
            if rows[i][2] >= z["top"]:
                z["status"] = "bos_brutt"
                bos_levels.append({
                    "level":     z["poi"],
                    "type":      "BOS_opp",
                    "idx":       i,
                    "zone_top":  z["top"],
                    "zone_bot":  z["bottom"],
                })
                break

    for z in demand_zones:
        for i in range(z["idx"]+1, len(rows)):
            if rows[i][2] <= z["bottom"]:
                z["status"] = "bos_brutt"
                bos_levels.append({
                    "level":     z["poi"],
                    "type":      "BOS_ned",
                    "idx":       i,
                    "zone_top":  z["top"],
                    "zone_bot":  z["bottom"],
                })
                break

    return supply_zones, demand_zones, bos_levels

def determine_structure(swing_highs_classified, swing_lows_classified):
    """
    Overordnet struktur basert på siste swing-labels:
    - Bullish: HH + HL
    - Bearish: LL + LH
    - Mixed: annet
    """
    last_high_label = swing_highs_classified[-1][2] if swing_highs_classified else None
    last_low_label  = swing_lows_classified[-1][2]  if swing_lows_classified  else None

    if last_high_label == "HH" and last_low_label == "HL":
        return "BULLISH"
    elif last_high_label == "LH" and last_low_label == "LL":
        return "BEARISH"
    elif last_high_label == "HH":
        return "BULLISH_SVAK"
    elif last_low_label == "LL":
        return "BEARISH_SVAK"
    else:
        return "MIXED"

def filter_relevant_zones(supply_zones, demand_zones, bos_levels, curr, atr, max_dist=8):
    """
    Filtrer til relevante soner:
    - Kun intakte soner (ikke brutt)
    - Innen max_dist × ATR fra nåpris
    - Nærmeste supply over pris, nærmeste demand under pris
    """
    relevant_supply = [z for z in supply_zones
                       if z["status"] == "intakt"
                       and z["bottom"] > curr
                       and abs(z["poi"] - curr) <= atr * max_dist]

    relevant_demand = [z for z in demand_zones
                       if z["status"] == "intakt"
                       and z["top"] < curr
                       and abs(z["poi"] - curr) <= atr * max_dist]

    # Sorter: nærmest pris øverst
    relevant_supply.sort(key=lambda z: abs(z["poi"] - curr))
    relevant_demand.sort(key=lambda z: abs(z["poi"] - curr))

    # Siste BOS-nivåer (maks 3)
    recent_bos = sorted(bos_levels, key=lambda b: b["idx"], reverse=True)[:3]

    return relevant_supply[:4], relevant_demand[:4], recent_bos

def run_smc(rows, swing_length=10, box_width=2.5):
    """
    Hovedfunksjon — kjør full SMC-analyse på en liste med (high, low, close) rows.
    Returnerer dict med alle SMC-data.
    """
    if len(rows) < swing_length*2 + 5:
        return None

    curr = rows[-1][2]
    atr  = calc_atr(rows, 50) or calc_atr(rows, 20)
    if not atr:
        return None

    # Pivot highs og lows
    ph = find_pivot_highs(rows, swing_length)
    pl = find_pivot_lows(rows,  swing_length)

    if not ph or not pl:
        return None

    # Klassifiser HH/LH og HL/LL
    swing_highs = classify_swings(ph, "high")
    swing_lows  = classify_swings(pl,  "low")

    # Supply/Demand soner
    supply, demand = build_supply_demand_zones(ph, pl, rows, atr, box_width)

    # BOS-deteksjon
    supply, demand, bos = detect_bos(supply, demand, rows)

    # Struktur
    structure = determine_structure(swing_highs, swing_lows)

    # Filtrer til relevante
    rel_supply, rel_demand, recent_bos = filter_relevant_zones(
        supply, demand, bos, curr, atr, max_dist=15
    )

    return {
        "structure":    structure,
        "atr":          round(atr, 5),
        "supply_zones": rel_supply,
        "demand_zones": rel_demand,
        "bos_levels":   recent_bos,
        "last_swing_high": {
            "value": round(swing_highs[-1][1], 5),
            "label": swing_highs[-1][2],
        } if swing_highs else None,
        "last_swing_low": {
            "value": round(swing_lows[-1][1], 5),
            "label": swing_lows[-1][2],
        } if swing_lows else None,
    }

# ── Test ──────────────────────────────────────────────────
if __name__ == "__main__":
    import urllib.request, urllib.parse, json

    def fetch(symbol, interval="15m", range_="5d"):
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval={interval}&range={range_}"
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        q = d["chart"]["result"][0]["indicators"]["quote"][0]
        return [(h,l,c) for h,l,c in zip(q["high"],q["low"],q["close"]) if h and l and c]

    for sym, name in [("EURUSD=X","EUR/USD"), ("GC=F","Gull"), ("CL=F","WTI")]:
        print(f"\n{'='*50}")
        print(f"{name} — 15m SMC")
        rows = fetch(sym)
        if not rows:
            print("  Ingen data"); continue
        result = run_smc(rows, swing_length=5)
        if not result:
            print("  For lite data"); continue
        curr = rows[-1][2]
        print(f"  Nåpris:    {curr:.5f}")
        print(f"  Struktur:  {result['structure']}")
        print(f"  Siste HH/LH: {result['last_swing_high']}")
        print(f"  Siste HL/LL: {result['last_swing_low']}")
        print(f"  Supply soner ({len(result['supply_zones'])}):")
        for z in result['supply_zones']:
            dist = abs(z['poi'] - curr) / result['atr']
            print(f"    {z['top']:.5f} – {z['bottom']:.5f}  POI:{z['poi']:.5f}  {dist:.1f}×ATR")
        print(f"  Demand soner ({len(result['demand_zones'])}):")
        for z in result['demand_zones']:
            dist = abs(z['poi'] - curr) / result['atr']
            print(f"    {z['top']:.5f} – {z['bottom']:.5f}  POI:{z['poi']:.5f}  {dist:.1f}×ATR")
        print(f"  BOS ({len(result['bos_levels'])}):")
        for b in result['bos_levels']:
            print(f"    {b['type']}  nivå:{b['level']:.5f}")
