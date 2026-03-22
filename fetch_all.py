#!/usr/bin/env python3
"""Bygger data/macro/latest.json med ekte priser + setups fra Yahoo Finance"""
import urllib.request, urllib.parse, json, os
from datetime import datetime, timezone

BASE = os.path.expanduser("~/cot-explorer/data")
OUT  = os.path.join(BASE, "macro", "latest.json")
os.makedirs(os.path.join(BASE, "macro"), exist_ok=True)

INSTRUMENTS = [
    {"key":"EURUSD", "navn":"EUR/USD",  "symbol":"EURUSD=X", "label":"Valuta",  "kat":"valuta",  "pip":0.0001},
    {"key":"USDJPY", "navn":"USD/JPY",  "symbol":"JPY=X",    "label":"Valuta",  "kat":"valuta",  "pip":0.01},
    {"key":"GBPUSD", "navn":"GBP/USD",  "symbol":"GBPUSD=X", "label":"Valuta",  "kat":"valuta",  "pip":0.0001},
    {"key":"USDCHF", "navn":"USD/CHF",  "symbol":"CHFUSD=X", "label":"Valuta",  "kat":"valuta",  "pip":0.0001},
    {"key":"AUDUSD", "navn":"AUD/USD",  "symbol":"AUDUSD=X", "label":"Valuta",  "kat":"valuta",  "pip":0.0001},
    {"key":"Gold",   "navn":"Gull",     "symbol":"GC=F",     "label":"Råvare",  "kat":"ravarer", "pip":0.1},
    {"key":"Silver", "navn":"Solv",     "symbol":"SI=F",     "label":"Råvare",  "kat":"ravarer", "pip":0.01},
    {"key":"Brent",  "navn":"Brent",    "symbol":"BZ=F",     "label":"Råvare",  "kat":"ravarer", "pip":0.01},
    {"key":"WTI",    "navn":"WTI",      "symbol":"CL=F",     "label":"Råvare",  "kat":"ravarer", "pip":0.01},
    {"key":"SPX",    "navn":"S&P 500",  "symbol":"^GSPC",    "label":"Aksjer",  "kat":"aksjer",  "pip":0.25},
    {"key":"NAS100", "navn":"Nasdaq",   "symbol":"^NDX",     "label":"Aksjer",  "kat":"aksjer",  "pip":0.25},
    {"key":"VIX",    "navn":"VIX",      "symbol":"^VIX",     "label":"Vol",     "kat":"aksjer",  "pip":0.01},
    {"key":"DXY",    "navn":"DXY",      "symbol":"DX-Y.NYB", "label":"Valuta",  "kat":"valuta",  "pip":0.01},
]

COT_MAP = {
    "EURUSD": "Euro Fx", "USDJPY": "Japanese Yen", "GBPUSD": "British Pound",
    "Gold": "Gold",      "Silver": "Silver",         "Brent": "Crude Oil, Light Sweet",
    "WTI":  "Crude Oil, Light Sweet", "SPX": "S&P 500 Consolidated",
    "NAS100":"Nasdaq Mini", "DXY": "Usd Index",
}

def fetch_yahoo(symbol, days=60):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=3mo"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        res  = d["chart"]["result"][0]
        q    = res["indicators"]["quote"][0]
        highs  = q.get("high",[])
        lows   = q.get("low",[])
        closes = q.get("close",[])
        # Rens None
        rows = [(h,l,c) for h,l,c in zip(highs,lows,closes) if h and l and c]
        return rows
    except Exception as e:
        print(f"  FEIL {symbol}: {e}")
        return []

def calc_atr(rows, n=14):
    if len(rows) < n+1: return None
    trs = []
    for i in range(1, len(rows)):
        h,l,c = rows[i]
        pc = rows[i-1][2]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs[-n:]) / n

def find_levels(rows, n=5):
    """Enkle støtte/motstand fra lokale topper/bunner"""
    highs  = [r[0] for r in rows]
    lows   = [r[1] for r in rows]
    closes = [r[2] for r in rows]
    curr   = closes[-1]

    resistances, supports = [], []
    for i in range(n, len(highs)-n):
        if highs[i] == max(highs[i-n:i+n+1]):
            resistances.append(highs[i])
        if lows[i] == min(lows[i-n:i+n+1]):
            supports.append(lows[i])

    res = sorted([r for r in resistances if r > curr], key=lambda x: abs(x-curr))[:4]
    sup = sorted([s for s in supports   if s < curr], key=lambda x: abs(x-curr))[:4]
    return res, sup

def make_setup(curr, atr, sup, res, direction, min_rr=2.0):
    if not atr: return None
    if direction == "long":
        if not sup: return None
        sl_raw = sup[0] - atr*0.2
        entry  = curr
        risk   = entry - sl_raw
        if risk <= 0: return None
        t1 = entry + risk * min_rr
        t2 = entry + risk * min_rr * 1.5
        dist_atr = abs(entry - curr) / atr
        rr1 = round((t1-entry)/risk, 2)
        rr2 = round((t2-entry)/risk, 2)
        return {"entry": round(entry,5), "sl": round(sl_raw,5), "t1": round(t1,5),
                "t2": round(t2,5), "rr_t1": rr1, "rr_t2": rr2, "min_rr": min_rr,
                "entry_dist_atr": round(dist_atr,2), "entry_name": "Nåpris",
                "note": f"SL under støtte ({round(sup[0],4)}). ATR={round(atr,4)}"}
    else:
        if not res: return None
        sl_raw = res[0] + atr*0.2
        entry  = curr
        risk   = sl_raw - entry
        if risk <= 0: return None
        t1 = entry - risk * min_rr
        t2 = entry - risk * min_rr * 1.5
        dist_atr = abs(entry - curr) / atr
        rr1 = round((entry-t1)/risk, 2)
        rr2 = round((entry-t2)/risk, 2)
        return {"entry": round(entry,5), "sl": round(sl_raw,5), "t1": round(t1,5),
                "t2": round(t2,5), "rr_t1": rr1, "rr_t2": rr2, "min_rr": min_rr,
                "entry_dist_atr": round(dist_atr,2), "entry_name": "Nåpris",
                "note": f"SL over motstand ({round(res[0],4)}). ATR={round(atr,4)}"}

# Last COT
cot_data = {}
cot_file = os.path.join(BASE, "combined", "latest.json")
if os.path.exists(cot_file):
    with open(cot_file) as f:
        cot_list = json.load(f)
    for d in cot_list:
        cot_data[d["market"].lower()] = d

prices  = {}
levels  = {}

for inst in INSTRUMENTS:
    print(f"Henter {inst['navn']} ({inst['symbol']})...")
    rows = fetch_yahoo(inst["symbol"])
    if not rows:
        continue

    curr   = rows[-1][2]
    atr    = calc_atr(rows)
    sma200 = sum(r[2] for r in rows[-200:]) / min(200, len(rows))
    res_lvl, sup_lvl = find_levels(rows)

    # Priser
    c1  = rows[-2][2] if len(rows)>=2 else curr
    c5  = rows[-6][2] if len(rows)>=6 else curr
    c20 = rows[-21][2] if len(rows)>=21 else curr
    prices[inst["key"]] = {
        "price":  round(curr, 4 if curr < 100 else 2),
        "chg1d":  round((curr/c1-1)*100, 2),
        "chg5d":  round((curr/c5-1)*100, 2),
        "chg20d": round((curr/c20-1)*100, 2),
    }

    if inst["key"] == "VIX": continue  # ingen setup for VIX

    # COT-data
    cot_key = COT_MAP.get(inst["key"],"").lower()
    cot_entry = cot_data.get(cot_key, {})
    spec_net = (cot_entry.get("spekulanter") or {}).get("net", 0) or 0
    oi = cot_entry.get("open_interest", 1) or 1
    cot_pct = spec_net / oi * 100
    cot_bias = "LONG" if cot_pct > 4 else "SHORT" if cot_pct < -4 else "NOYTRAL"
    cot_color = "bull" if cot_pct > 4 else "bear" if cot_pct < -4 else "neutral"

    # Retning
    above_sma = curr > sma200
    chg5 = prices[inst["key"]]["chg5d"]
    if above_sma and chg5 > 0 and cot_pct > 0:
        dir_color = "bull"; bias_score = 2
    elif not above_sma and chg5 < 0 and cot_pct < 0:
        dir_color = "bear"; bias_score = -2
    elif above_sma or chg5 > 0:
        dir_color = "bull"; bias_score = 1
    else:
        dir_color = "bear"; bias_score = -1

    # Score (7 punkter)
    score_details = [
        {"kryss": "Over SMA200",     "verdi": above_sma},
        {"kryss": "5d trend opp",    "verdi": chg5 > 0},
        {"kryss": "COT Long bias",   "verdi": cot_pct > 4},
        {"kryss": "COT ikke short",  "verdi": cot_pct > -4},
        {"kryss": "Støtte nær",      "verdi": bool(sup_lvl and atr and abs(curr-sup_lvl[0]) < atr*2)},
        {"kryss": "Motstand fritt",  "verdi": bool(res_lvl and atr and abs(curr-res_lvl[0]) > atr*1.5)},
        {"kryss": "Momentum 20d",    "verdi": prices[inst["key"]]["chg20d"] > 0},
    ]
    score = sum(1 for s in score_details if s["verdi"])
    grade = "A+" if score >= 6 else "B" if score >= 4 else "C"
    grade_color = "bull" if score >= 6 else "warn" if score >= 4 else "bear"

    # Setups
    setup_long  = make_setup(curr, atr, sup_lvl, res_lvl, "long")
    setup_short = make_setup(curr, atr, sup_lvl, res_lvl, "short")

    levels[inst["key"]] = {
        "name":          inst["navn"],
        "label":         inst["label"],
        "class":         inst["kat"][0].upper(),
        "current":       round(curr, 4 if curr < 100 else 2),
        "atr14":         round(atr, 5) if atr else None,
        "sma200":        round(sma200, 4 if sma200 < 100 else 2),
        "sma200_pos":    "over" if above_sma else "under",
        "chg5d":         prices[inst["key"]]["chg5d"],
        "chg20d":        prices[inst["key"]]["chg20d"],
        "dir_color":     dir_color,
        "grade":         grade,
        "grade_color":   grade_color,
        "score":         score,
        "score_pct":     round(score/7*100),
        "score_details": score_details,
        "open_interest": oi,
        "resistances":   [{"name":f"R{i+1}","level":round(r,5),"dist_atr":round(abs(r-curr)/(atr or 1),1)} for i,r in enumerate(res_lvl[:4])],
        "supports":      [{"name":f"S{i+1}","level":round(s,5),"dist_atr":round(abs(s-curr)/(atr or 1),1)} for i,s in enumerate(sup_lvl[:4])],
        "setup_long":    setup_long,
        "setup_short":   setup_short,
        "session":       {"active": True, "label": "24h"},
        "binary_risk":   [],
        "dxy_conf":      "medvind" if (inst["kat"]=="valuta" and (prices.get("DXY") or {}).get("chg5d",0) < 0) else "motvind",
        "pos_size":      "Full" if (prices.get("VIX") or {}).get("price",20) < 20 else "Halv",
        "vix_spread_factor": 1.0 if (prices.get("VIX") or {}).get("price",20) < 20 else 1.5,
        "cot": {
            "bias":   cot_bias,
            "color":  cot_color,
            "net":    spec_net,
            "chg":    cot_entry.get("change_spec_net", 0),
            "pct":    round(abs(cot_pct), 1),
            "date":   cot_entry.get("date",""),
            "report": cot_entry.get("report",""),
        },
        "combined_bias": "LONG" if dir_color == "bull" else "SHORT",
    }
    atr_s = f"{atr:.4f}" if atr else "0.0000"; print(f"  {inst['navn']:10s} curr={curr:.4f}  atr={atr_s}  grade={grade} ({score}/7)")

vix_price = (prices.get("VIX") or {}).get("price", 20)
dxy_5d    = (prices.get("DXY") or {}).get("chg5d", 0)
brent_p   = (prices.get("Brent") or {}).get("price", 80)
tip_5d    = 0
hyg_5d    = 0

if vix_price > 30:
    smile_pos, usd_bias, usd_color, smile_desc = "venstre","STERKT","bull","Risk-off – USD trygg havn"
elif vix_price < 18 and brent_p < 85:
    smile_pos, usd_bias, usd_color, smile_desc = "midten","SVAKT","bear","Goldilocks – svak USD"
else:
    smile_pos, usd_bias, usd_color, smile_desc = "hoyre","MODERAT","bull","Vekst/inflasjon driver USD"

if vix_price > 30:
    vix_regime = {"value": vix_price, "label": "Ekstrem frykt – kvart størrelse", "color":"bear","regime":"extreme"}
elif vix_price > 20:
    vix_regime = {"value": vix_price, "label": "Forhøyet – halv størrelse", "color":"warn","regime":"elevated"}
else:
    vix_regime = {"value": vix_price, "label": "Normalt – full størrelse", "color":"bull","regime":"normal"}

macro = {
    "date":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "cot_date": "2025-12-30",
    "prices":  prices,
    "vix_regime": vix_regime,
    "dollar_smile": {
        "position": smile_pos, "usd_bias": usd_bias,
        "usd_color": usd_color, "desc": smile_desc,
        "inputs": {"vix": vix_price, "hy_stress": hyg_5d < -1,
                   "brent": brent_p, "tip_trend_5d": tip_5d, "dxy_trend_5d": dxy_5d}
    },
    "trading_levels": levels,
    "calendar": [],
}

with open(OUT, "w") as f:
    json.dump(macro, f, ensure_ascii=False, indent=2)
print(f"\nOK → {OUT}  ({len(levels)} instruments)")
