#!/usr/bin/env python3
"""Henter live priser fra Yahoo Finance og bygger data/macro/latest.json"""
import urllib.request, json, os
from datetime import datetime, timezone

BASE = os.path.expanduser("~/cot-explorer/data")
OUT  = os.path.join(BASE, "macro", "latest.json")
os.makedirs(os.path.join(BASE, "macro"), exist_ok=True)

SYMBOLS = {
    "VIX":    "^VIX",
    "SPX":    "^GSPC",
    "NAS100": "^NDX",
    "DXY":    "DX-Y.NYB",
    "EURUSD": "EURUSD=X",
    "USDJPY": "JPY=X",
    "GBPUSD": "GBPUSD=X",
    "USDCHF": "CHFUSD=X",
    "AUDUSD": "AUDUSD=X",
    "USDNOK": "NOKUSD=X",
    "Brent":  "BZ=F",
    "WTI":    "CL=F",
    "Gold":   "GC=F",
    "Silver": "SI=F",
    "HYG":    "HYG",
    "TIP":    "TIP",
}

def fetch_yahoo(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=1mo"
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        res = d["chart"]["result"][0]
        closes = res["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if len(closes) < 6:
            return None
        now   = closes[-1]
        day1  = closes[-2]
        day5  = closes[-6] if len(closes) >= 6 else closes[0]
        day20 = closes[-21] if len(closes) >= 21 else closes[0]
        return {
            "price":  round(now, 4),
            "chg1d":  round((now/day1 - 1)*100, 2),
            "chg5d":  round((now/day5 - 1)*100, 2),
            "chg20d": round((now/day20 - 1)*100, 2),
        }
    except Exception as e:
        print(f"  FEIL {symbol}: {e}")
        return None

import urllib.parse
prices = {}
for key, sym in SYMBOLS.items():
    print(f"Henter {key} ({sym})...")
    v = fetch_yahoo(sym)
    if v:
        prices[key] = v
        print(f"  → {v['price']} ({v['chg1d']:+.2f}%)")

vix = (prices.get("VIX") or {}).get("price", 20)
dxy_5d = (prices.get("DXY") or {}).get("chg5d", 0)
brent = (prices.get("Brent") or {}).get("price", 80)
hyg = (prices.get("HYG") or {}).get("chg5d", 0)
tip_5d = (prices.get("TIP") or {}).get("chg5d", 0)

hy_stress = hyg < -1.0
if vix > 30:
    smile_pos, usd_bias, usd_color, smile_desc = "venstre", "STERKT", "bull", "Risk-off – USD etterspurt som trygg havn"
elif vix < 18 and brent < 85:
    smile_pos, usd_bias, usd_color, smile_desc = "midten", "SVAKT", "bear", "Goldilocks – svak USD, risikoappetitt god"
else:
    smile_pos, usd_bias, usd_color, smile_desc = "hoyre", "MODERAT", "bull", "Vekst/inflasjon driver USD"

if vix > 30:
    vix_regime = {"value": vix, "label": "Ekstrem frykt – kvart størrelse", "color": "bear", "regime": "extreme"}
elif vix > 20:
    vix_regime = {"value": vix, "label": "Forhøyet – halv størrelse", "color": "warn", "regime": "elevated"}
else:
    vix_regime = {"value": vix, "label": "Normalt – full størrelse", "color": "bull", "regime": "normal"}

macro = {
    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "cot_date": "2025-12-30",
    "prices": prices,
    "vix_regime": vix_regime,
    "dollar_smile": {
        "position": smile_pos,
        "usd_bias": usd_bias,
        "usd_color": usd_color,
        "desc": smile_desc,
        "inputs": {
            "vix": vix,
            "hy_stress": hy_stress,
            "brent": brent,
            "tip_trend_5d": tip_5d,
            "dxy_trend_5d": dxy_5d,
        }
    },
    "trading_levels": {},
    "calendar": [],
}

with open(OUT, "w") as f:
    json.dump(macro, f, ensure_ascii=False, indent=2)
print(f"\nOK → {OUT}")
