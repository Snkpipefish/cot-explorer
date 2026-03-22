#!/usr/bin/env python3
"""
Henter ukentlig prishistorikk fra Yahoo og lagrer som data/prices/{symbol}.json
Kjøres lokalt sammen med fetch_cot.py
"""
import urllib.request, urllib.parse, json, os
from datetime import datetime, timezone

BASE = os.path.expanduser("~/cot-explorer/data/prices")
os.makedirs(BASE, exist_ok=True)

INSTRUMENTS = [
    {"key":"eurusd",  "yahoo":"EURUSD=X",  "navn":"EUR/USD"},
    {"key":"usdjpy",  "yahoo":"JPY=X",      "navn":"USD/JPY"},
    {"key":"gbpusd",  "yahoo":"GBPUSD=X",   "navn":"GBP/USD"},
    {"key":"audusd",  "yahoo":"AUDUSD=X",   "navn":"AUD/USD"},
    {"key":"gold",    "yahoo":"GC=F",        "navn":"Gull"},
    {"key":"silver",  "yahoo":"SI=F",        "navn":"Sølv"},
    {"key":"brent",   "yahoo":"BZ=F",        "navn":"Brent"},
    {"key":"wti",     "yahoo":"CL=F",        "navn":"WTI"},
    {"key":"spx",     "yahoo":"^GSPC",       "navn":"S&P 500"},
    {"key":"nas100",  "yahoo":"^NDX",        "navn":"Nasdaq"},
    {"key":"dxy",     "yahoo":"DX-Y.NYB",    "navn":"DXY"},
    {"key":"corn",    "yahoo":"ZC=F",        "navn":"Mais"},
    {"key":"wheat",   "yahoo":"ZW=F",        "navn":"Hvete"},
    {"key":"soybean", "yahoo":"ZS=F",        "navn":"Soyabønner"},
    {"key":"sugar",   "yahoo":"SB=F",        "navn":"Sukker"},
    {"key":"coffee",  "yahoo":"KC=F",        "navn":"Kaffe"},
    {"key":"cocoa",   "yahoo":"CC=F",        "navn":"Kakao"},
]

# COT-symbol til pris-nøkkel mapping
COT_TO_PRICE = {
    "099741": "eurusd",
    "096742": "usdjpy",
    "092741": "gbpusd",
    "232741": "audusd",
    "088691": "gold",
    "084691": "silver",
    "067651": "wti",
    "023651": "brent",
    "133741": "spx",
    "209742": "nas100",
    "098662": "dxy",
    "002602": "corn",
    "001602": "wheat",
    "005602": "soybean",
    "083731": "sugar",
    "073732": "coffee",
    "080732": "cocoa",
}

def fetch_weekly(yahoo_sym, years=15):
    import time
    end   = int(time.time())
    start = end - years * 365 * 24 * 3600
    url   = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo_sym)}?interval=1wk&period1={start}&period2={end}"
    req   = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        res = d["chart"]["result"][0]
        ts  = res["timestamp"]
        cl  = res["indicators"]["quote"][0]["close"]
        out = []
        for i in range(len(ts)):
            if cl[i] is None: continue
            dt = datetime.fromtimestamp(ts[i], tz=timezone.utc).strftime("%Y-%m-%d")
            out.append({"date": dt, "price": round(cl[i], 5 if cl[i]<100 else 2)})
        return out
    except Exception as e:
        print(f"  FEIL: {e}")
        return []

for inst in INSTRUMENTS:
    print(f"Henter {inst['navn']} ({inst['yahoo']})...")
    rows = fetch_weekly(inst["yahoo"])
    if not rows:
        continue
    out = {"key": inst["key"], "navn": inst["navn"], "yahoo": inst["yahoo"], "data": rows}
    path = os.path.join(BASE, inst["key"] + ".json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"  {len(rows)} uker → {path}")

# Lagre COT→pris mapping
with open(os.path.join(BASE, "cot_map.json"), "w") as f:
    json.dump(COT_TO_PRICE, f, ensure_ascii=False, indent=2)

print(f"\nFerdig! Lagret i data/prices/")
