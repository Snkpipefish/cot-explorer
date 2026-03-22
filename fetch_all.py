#!/usr/bin/env python3
import urllib.request, urllib.parse, json, os
from datetime import datetime, timezone

BASE = os.path.expanduser("~/cot-explorer/data")
OUT  = os.path.join(BASE, "macro", "latest.json")
os.makedirs(os.path.join(BASE, "macro"), exist_ok=True)

INSTRUMENTS = [
    {"key":"EURUSD", "navn":"EUR/USD",  "symbol":"EURUSD=X", "label":"Valuta",  "kat":"valuta"},
    {"key":"USDJPY", "navn":"USD/JPY",  "symbol":"JPY=X",    "label":"Valuta",  "kat":"valuta"},
    {"key":"GBPUSD", "navn":"GBP/USD",  "symbol":"GBPUSD=X", "label":"Valuta",  "kat":"valuta"},
    {"key":"USDCHF", "navn":"USD/CHF",  "symbol":"CHFUSD=X", "label":"Valuta",  "kat":"valuta"},
    {"key":"AUDUSD", "navn":"AUD/USD",  "symbol":"AUDUSD=X", "label":"Valuta",  "kat":"valuta"},
    {"key":"Gold",   "navn":"Gull",     "symbol":"GC=F",     "label":"Råvare",  "kat":"ravarer"},
    {"key":"Silver", "navn":"Sølv",     "symbol":"SI=F",     "label":"Råvare",  "kat":"ravarer"},
    {"key":"Brent",  "navn":"Brent",    "symbol":"BZ=F",     "label":"Råvare",  "kat":"ravarer"},
    {"key":"WTI",    "navn":"WTI",      "symbol":"CL=F",     "label":"Råvare",  "kat":"ravarer"},
    {"key":"SPX",    "navn":"S&P 500",  "symbol":"^GSPC",    "label":"Aksjer",  "kat":"aksjer"},
    {"key":"NAS100", "navn":"Nasdaq",   "symbol":"^NDX",     "label":"Aksjer",  "kat":"aksjer"},
    {"key":"VIX",    "navn":"VIX",      "symbol":"^VIX",     "label":"Vol",     "kat":"aksjer"},
    {"key":"DXY",    "navn":"DXY",      "symbol":"DX-Y.NYB", "label":"Valuta",  "kat":"valuta"},
]

COT_MAP = {
    "EURUSD":"euro fx","USDJPY":"japanese yen","GBPUSD":"british pound",
    "Gold":"gold","Silver":"silver","Brent":"crude oil, light sweet",
    "WTI":"crude oil, light sweet","SPX":"s&p 500 consolidated",
    "NAS100":"nasdaq mini","DXY":"usd index",
}

def fetch_yahoo(symbol, interval="1d", range_="3mo"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval={interval}&range={range_}"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        res = d["chart"]["result"][0]
        q   = res["indicators"]["quote"][0]
        rows = [(h,l,c) for h,l,c in zip(q.get("high",[]),q.get("low",[]),q.get("close",[])) if h and l and c]
        return rows
    except Exception as e:
        print(f"  FEIL {symbol} ({interval}): {e}")
        return []

def calc_atr(rows, n=14):
    if len(rows) < n+1: return None
    trs = [max(rows[i][0]-rows[i][1], abs(rows[i][0]-rows[i-1][2]), abs(rows[i][1]-rows[i-1][2]))
           for i in range(1, len(rows))]
    return sum(trs[-n:]) / n

def to_4h(rows_1h):
    """Grupperer 1h-data til 4h-stearinlys"""
    out = []
    for i in range(0, len(rows_1h)-3, 4):
        grp = rows_1h[i:i+4]
        h = max(r[0] for r in grp)
        l = min(r[1] for r in grp)
        c = grp[-1][2]
        out.append((h,l,c))
    return out

def find_levels(rows, n=5):
    curr = rows[-1][2]
    res, sup = [], []
    for i in range(n, len(rows)-n):
        if rows[i][0] == max(r[0] for r in rows[i-n:i+n+1]):
            res.append(rows[i][0])
        if rows[i][1] == min(r[1] for r in rows[i-n:i+n+1]):
            sup.append(rows[i][1])
    r_filt = sorted([r for r in set(res) if r > curr], key=lambda x: abs(x-curr))[:4]
    s_filt = sorted([s for s in set(sup) if s < curr], key=lambda x: abs(x-curr))[:4]
    return r_filt, s_filt

def make_setup(curr, atr, sup, res, direction, min_rr=2.0, timeframe="swing"):
    if not atr or atr <= 0: return None
    sl_mult = 1.2 if timeframe == "intradag" else 1.5
    if direction == "long":
        if not sup: return None
        sl = sup[0] - atr * sl_mult * 0.2
        risk = curr - sl
        if risk <= 0 or risk > atr * 4: return None
        t1 = curr + risk * min_rr
        t2 = curr + risk * min_rr * 1.5
        entry_name = "Nåpris" if timeframe == "intradag" else "Nåpris (swing)"
        note = f"SL under S1 ({round(sup[0],4)}) − {sl_mult*0.2:.1f}×ATR. ATR={round(atr,4)}. Holdtid: {timeframe}"
    else:
        if not res: return None
        sl = res[0] + atr * sl_mult * 0.2
        risk = sl - curr
        if risk <= 0 or risk > atr * 4: return None
        t1 = curr - risk * min_rr
        t2 = curr - risk * min_rr * 1.5
        entry_name = "Nåpris" if timeframe == "intradag" else "Nåpris (swing)"
        note = f"SL over R1 ({round(res[0],4)}) + {sl_mult*0.2:.1f}×ATR. ATR={round(atr,4)}. Holdtid: {timeframe}"
    return {
        "entry": round(curr,5), "sl": round(sl,5),
        "t1": round(t1,5), "t2": round(t2,5),
        "rr_t1": round((t1-curr)/risk if direction=="long" else (curr-t1)/risk, 2),
        "rr_t2": round((t2-curr)/risk if direction=="long" else (curr-t2)/risk, 2),
        "min_rr": min_rr, "entry_dist_atr": 0.0,
        "entry_name": entry_name, "note": note,
        "timeframe": timeframe,
    }

def fetch_fear_greed():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://edition.cnn.com/markets/fear-and-greed",
            "Origin": "https://edition.cnn.com",
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
        score = d["fear_and_greed"]["score"]
        rating = d["fear_and_greed"]["rating"]
        return {"score": round(score,1), "rating": rating}
    except Exception as e:
        print(f"  Fear&Greed FEIL: {e}")
        return None

def detect_conflict(vix, dxy_5d, fg, cot_usd):
    """Returner liste med konflikter og samlet vurdering"""
    conflicts = []
    if vix > 25 and dxy_5d < 0:
        conflicts.append("VIX>25 men DXY faller – risk-off uten USD-etterspørsel")
    if fg and fg["score"] < 30 and dxy_5d < 0:
        conflicts.append("Ekstrem frykt men USD svekkes – unormalt")
    if fg and fg["score"] > 70 and vix > 22:
        conflicts.append("Grådighet men VIX forhøyet – divergens")
    if cot_usd and cot_usd > 0 and dxy_5d < -1:
        conflicts.append("COT long USD men pris faller – smart money vs marked")
    return conflicts

# ── Last COT ──────────────────────────────────────────────
cot_data = {}
cot_file = os.path.join(BASE, "combined", "latest.json")
if os.path.exists(cot_file):
    with open(cot_file) as f:
        for d in json.load(f):
            cot_data[d["market"].lower()] = d

# ── Fear & Greed ──────────────────────────────────────────
print("Henter Fear & Greed...")
fg = fetch_fear_greed()
if fg:
    print(f"  → {fg['score']} ({fg['rating']})")

# ── Priser og setups ──────────────────────────────────────
prices, levels = {}, {}

for inst in INSTRUMENTS:
    print(f"Henter {inst['navn']}...")

    # Daglige data (trend, SMA200, swing-ATR)
    daily = fetch_yahoo(inst["symbol"], "1d", "1y")
    # 1h data (intradag ATR og nivåer)
    hourly_raw = fetch_yahoo(inst["symbol"], "60m", "60d")
    h4 = to_4h(hourly_raw) if hourly_raw else []

    if not daily or len(daily) < 10:
        continue

    curr    = daily[-1][2]
    atr_d   = calc_atr(daily, 14)       # daglig ATR
    atr_4h  = calc_atr(h4, 14) if len(h4) >= 15 else None   # 4h ATR
    sma200  = sum(r[2] for r in daily[-200:]) / min(200, len(daily))

    c1  = daily[-2][2] if len(daily)>=2  else curr
    c5  = daily[-6][2] if len(daily)>=6  else curr
    c20 = daily[-21][2] if len(daily)>=21 else curr
    prices[inst["key"]] = {
        "price":  round(curr, 4 if curr < 100 else 2),
        "chg1d":  round((curr/c1-1)*100, 2),
        "chg5d":  round((curr/c5-1)*100, 2),
        "chg20d": round((curr/c20-1)*100, 2),
    }

    if inst["key"] == "VIX": continue

    # Velg ATR og nivåer basert på tilgjengelig data
    use_4h   = atr_4h is not None
    atr_use  = atr_4h if use_4h else atr_d
    timeframe = "intradag" if use_4h else "swing"
    lvl_rows  = h4 if (use_4h and len(h4)>20) else daily
    res_lvl, sup_lvl = find_levels(lvl_rows)

    # COT
    cot_key   = COT_MAP.get(inst["key"],"")
    cot_entry = cot_data.get(cot_key, {})
    spec_net  = (cot_entry.get("spekulanter") or {}).get("net", 0) or 0
    oi        = cot_entry.get("open_interest", 1) or 1
    cot_pct   = spec_net / oi * 100
    cot_bias  = "LONG" if cot_pct>4 else "SHORT" if cot_pct<-4 else "NØYTRAL"
    cot_color = "bull"  if cot_pct>4 else "bear"  if cot_pct<-4 else "neutral"

    # Sentiment-bekrefting
    above_sma = curr > sma200
    chg5      = prices[inst["key"]]["chg5d"]
    chg20     = prices[inst["key"]]["chg20d"]

    # Bullish hvis Fear<30 (kjøp ved frykt) på risk assets, eller Greed>60 på momentum
    fg_score  = fg["score"] if fg else 50
    sent_bull = (fg_score < 35 and inst["kat"] in ("ravarer",)) or \
                (fg_score > 60 and inst["kat"] == "aksjer" and chg5 > 0) or \
                (fg_score < 30)  # ekstrem frykt = kontrarian kjøp

    # Score 8 punkter
    score_details = [
        {"kryss":"Over SMA200",          "verdi": above_sma},
        {"kryss":"5d trend opp",          "verdi": chg5 > 0},
        {"kryss":"COT long bias",         "verdi": cot_pct > 4},
        {"kryss":"COT ikke short",        "verdi": cot_pct > -4},
        {"kryss":"Støtte nær (<2×ATR)",   "verdi": bool(sup_lvl and atr_use and abs(curr-sup_lvl[0]) < atr_use*2)},
        {"kryss":"Motstand fritt (>1.5×)","verdi": bool(res_lvl and atr_use and abs(curr-res_lvl[0]) > atr_use*1.5)},
        {"kryss":"Momentum 20d",          "verdi": chg20 > 0},
        {"kryss":"Sentiment bekrefter",   "verdi": sent_bull},
    ]
    score      = sum(1 for s in score_details if s["verdi"])
    grade      = "A+" if score>=7 else "B" if score>=5 else "C"
    grade_color= "bull" if score>=7 else "warn" if score>=5 else "bear"

    if above_sma and chg5>0:  dir_color="bull"
    elif not above_sma and chg5<0: dir_color="bear"
    elif above_sma: dir_color="bull"
    else: dir_color="bear"

    # Setups med riktig ATR
    setup_long  = make_setup(curr, atr_use, sup_lvl, res_lvl, "long",  timeframe=timeframe)
    setup_short = make_setup(curr, atr_use, sup_lvl, res_lvl, "short", timeframe=timeframe)

    vix_price = (prices.get("VIX") or {}).get("price", 20)
    pos_size  = "Full" if vix_price<20 else "Halv" if vix_price<30 else "Kvart"

    def fmt_level(lvl, typ, atr):
        return [{"name":f"{typ}{i+1}","level":round(l, 5 if l<100 else 2),
                 "dist_atr":round(abs(l-curr)/(atr or 1),1)} for i,l in enumerate(lvl[:4])]

    levels[inst["key"]] = {
        "name":          inst["navn"],
        "label":         inst["label"],
        "class":         inst["kat"][0].upper(),
        "current":       round(curr, 4 if curr<100 else 2),
        "atr14":         round(atr_use, 5) if atr_use else None,
        "atr_daily":     round(atr_d, 5) if atr_d else None,
        "atr_4h":        round(atr_4h, 5) if atr_4h else None,
        "timeframe":     timeframe,
        "sma200":        round(sma200, 4 if sma200<100 else 2),
        "sma200_pos":    "over" if above_sma else "under",
        "chg5d":         chg5,
        "chg20d":        chg20,
        "dir_color":     dir_color,
        "grade":         grade,
        "grade_color":   grade_color,
        "score":         score,
        "score_pct":     round(score/8*100),
        "score_details": score_details,
        "open_interest": oi,
        "resistances":   fmt_level(res_lvl,"R",atr_use),
        "supports":      fmt_level(sup_lvl,"S",atr_use),
        "setup_long":    setup_long,
        "setup_short":   setup_short,
        "session":       {"active": True, "label": "24h"},
        "binary_risk":   [],
        "dxy_conf":      "medvind" if (inst["kat"]=="valuta" and (prices.get("DXY") or {}).get("chg5d",0)<0) else "motvind",
        "pos_size":      pos_size,
        "vix_spread_factor": 1.0 if vix_price<20 else 1.5 if vix_price<30 else 2.0,
        "cot": {
            "bias":   cot_bias, "color": cot_color,
            "net":    spec_net, "chg": cot_entry.get("change_spec_net",0),
            "pct":    round(abs(cot_pct),1),
            "date":   cot_entry.get("date",""), "report": cot_entry.get("report",""),
        },
        "combined_bias": "LONG" if dir_color=="bull" else "SHORT",
        "sentiment": {"fear_greed": fg, "sent_bull": sent_bull},
    }
    atr_s = f"{atr_use:.4f}" if atr_use else "N/A"
    print(f"  {inst['navn']:10s} {curr:.4f}  ATR({timeframe[:2]})={atr_s}  {grade}({score}/8)  {pos_size}")

# ── Makro-analyse ─────────────────────────────────────────
vix_price = (prices.get("VIX") or {}).get("price", 20)
dxy_5d    = (prices.get("DXY") or {}).get("chg5d", 0)
brent_p   = (prices.get("Brent") or {}).get("price", 80)
fg_score  = fg["score"] if fg else 50
cot_dxy   = (cot_data.get("usd index") or {})
cot_dxy_net = ((cot_dxy.get("spekulanter") or {}).get("net",0) or 0)

conflicts = detect_conflict(vix_price, dxy_5d, fg, cot_dxy_net)

# Dollar Smile med konflikt-deteksjon
if conflicts:
    smile_pos  = "konflikt"
    usd_bias   = "UKLAR"
    usd_color  = "warn"
    smile_desc = "Motstridende signaler – reduser størrelse: " + " | ".join(conflicts[:2])
elif vix_price > 30:
    smile_pos,usd_bias,usd_color,smile_desc = "venstre","STERKT","bull","Risk-off – USD trygg havn"
elif vix_price < 18 and brent_p < 85:
    smile_pos,usd_bias,usd_color,smile_desc = "midten","SVAKT","bear","Goldilocks – svak USD"
else:
    smile_pos,usd_bias,usd_color,smile_desc = "hoyre","MODERAT","bull","Vekst/inflasjon driver USD"

if vix_price > 30:
    vix_regime = {"value":vix_price,"label":"Ekstrem frykt – KVART størrelse","color":"bear","regime":"extreme"}
elif vix_price > 20:
    vix_regime = {"value":vix_price,"label":"Forhøyet – HALV størrelse","color":"warn","regime":"elevated"}
else:
    vix_regime = {"value":vix_price,"label":"Normalt – full størrelse","color":"bull","regime":"normal"}

macro = {
    "date":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "cot_date": max((d.get("date","") for d in cot_data.values() if d.get("date")), default="ukjent"),
    "prices":  prices,
    "vix_regime": vix_regime,
    "sentiment": {"fear_greed": fg, "conflicts": conflicts},
    "dollar_smile": {
        "position":smile_pos,"usd_bias":usd_bias,
        "usd_color":usd_color,"desc":smile_desc,
        "conflicts": conflicts,
        "inputs":{"vix":vix_price,"hy_stress":False,"brent":brent_p,
                  "tip_trend_5d":0,"dxy_trend_5d":dxy_5d}
    },
    "trading_levels": levels,
    "calendar": [],
}

with open(OUT,"w") as f:
    json.dump(macro, f, ensure_ascii=False, indent=2)
print(f"\nOK → {OUT}  ({len(levels)} instruments, {len(conflicts)} konflikter)")
if conflicts:
    print("Konflikter funnet:")
    for c in conflicts: print(f"  ⚠️  {c}")
