#!/usr/bin/env python3
import urllib.request, urllib.parse, json, os
from datetime import datetime, timezone
import sys
sys.path.insert(0, os.path.expanduser('~/cot-explorer'))
try:
    from smc import run_smc
    SMC_OK = True
except:
    SMC_OK = False
    print('  SMC ikke tilgjengelig')

BASE = os.path.expanduser("~/cot-explorer/data")
OUT  = os.path.join(BASE, "macro", "latest.json")
os.makedirs(os.path.join(BASE, "macro"), exist_ok=True)

INSTRUMENTS = [
    {"key":"EURUSD","navn":"EUR/USD", "symbol":"EURUSD=X","label":"Valuta", "kat":"valuta", "klasse":"A","session":"London 08:00–12:00 CET"},
    {"key":"USDJPY","navn":"USD/JPY", "symbol":"JPY=X",   "label":"Valuta", "kat":"valuta", "klasse":"A","session":"London 08:00–12:00 CET"},
    {"key":"GBPUSD","navn":"GBP/USD", "symbol":"GBPUSD=X","label":"Valuta", "kat":"valuta", "klasse":"A","session":"London 08:00–12:00 CET"},
    {"key":"AUDUSD","navn":"AUD/USD", "symbol":"AUDUSD=X","label":"Valuta", "kat":"valuta", "klasse":"A","session":"London 08:00–12:00 CET"},
    {"key":"Gold",  "navn":"Gull",   "symbol":"GC=F",    "label":"Råvare", "kat":"ravarer","klasse":"B","session":"London Fix 10:30 / NY Fix 15:00 CET"},
    {"key":"Silver","navn":"Sølv",   "symbol":"SI=F",    "label":"Råvare", "kat":"ravarer","klasse":"B","session":"London Fix 10:30 / NY Fix 15:00 CET"},
    {"key":"Brent", "navn":"Brent",  "symbol":"BZ=F",    "label":"Råvare", "kat":"ravarer","klasse":"B","session":"London Fix 10:30 / NY Fix 15:00 CET"},
    {"key":"WTI",   "navn":"WTI",    "symbol":"CL=F",    "label":"Råvare", "kat":"ravarer","klasse":"B","session":"London Fix 10:30 / NY Fix 15:00 CET"},
    {"key":"SPX",   "navn":"S&P 500","symbol":"^GSPC",   "label":"Aksjer", "kat":"aksjer", "klasse":"C","session":"NY Open 14:30–17:00 CET"},
    {"key":"NAS100","navn":"Nasdaq", "symbol":"^NDX",    "label":"Aksjer", "kat":"aksjer", "klasse":"C","session":"NY Open 14:30–17:00 CET"},
    {"key":"VIX",   "navn":"VIX",    "symbol":"^VIX",    "label":"Vol",    "kat":"aksjer", "klasse":"C","session":"NY Open 14:30–17:00 CET"},
    {"key":"DXY",   "navn":"DXY",    "symbol":"DX-Y.NYB","label":"Valuta", "kat":"valuta", "klasse":"A","session":"London 08:00–12:00 CET"},
]

COT_MAP = {
    "EURUSD":"euro fx","USDJPY":"japanese yen","GBPUSD":"british pound",
    "Gold":"gold","Silver":"silver","Brent":"crude oil, light sweet",
    "WTI":"crude oil, light sweet","SPX":"s&p 500 consolidated",
    "NAS100":"nasdaq mini","DXY":"usd index",
}

def fetch_yahoo(symbol, interval="1d", range_="1y"):
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

def calc_ema(closes, n=9):
    if len(closes) < n+1: return None
    k = 2/(n+1)
    ema = sum(closes[:n])/n
    for c in closes[n:]:
        ema = c*k + ema*(1-k)
    return ema

def to_4h(rows_1h):
    out = []
    for i in range(0, len(rows_1h)-3, 4):
        grp = rows_1h[i:i+4]
        h = max(r[0] for r in grp)
        l = min(r[1] for r in grp)
        c = grp[-1][2]
        out.append((h,l,c))
    return out

def get_pdh_pdl_pdc(daily):
    if len(daily) < 2: return None, None, None
    return daily[-2][0], daily[-2][1], daily[-2][2]

def get_pwh_pwl(daily):
    if len(daily) < 10: return None, None
    week = daily[-8:-1]
    return max(r[0] for r in week), min(r[1] for r in week)

def get_session_status():
    h = datetime.now(timezone.utc).hour
    m = datetime.now(timezone.utc).minute
    cet = (h*60 + m + 60) % (24*60)  # UTC+1
    ch  = cet // 60
    sessions = []
    if 7*60 <= cet < 12*60:  sessions.append("London")
    if 13*60 <= cet < 17*60: sessions.append("NY Overlap")
    if 8*60 <= cet < 12*60:  sessions.append("London Fix")
    if not sessions:          sessions.append("Off-session")
    return {"active": any(s != "Off-session" for s in sessions),
            "label": " / ".join(sessions), "cet_hour": ch}

def find_intraday_levels(rows_15m, n=3):
    """
    Finner støtte/motstand fra 15m candles.
    Bruker bare siste 2 dagers data (ca 200 candles).
    n=3: minst 3 candles på hver side for å bekrefte nivå.
    """
    rows = rows_15m[-200:] if len(rows_15m) > 200 else rows_15m
    curr = rows[-1][2]
    res, sup = [], []
    for i in range(n, len(rows)-n):
        if rows[i][0] == max(r[0] for r in rows[i-n:i+n+1]):
            res.append(rows[i][0])
        if rows[i][1] == min(r[1] for r in rows[i-n:i+n+1]):
            sup.append(rows[i][1])
    r_filt = sorted(list(dict.fromkeys([round(r,5) for r in res if r > curr])),
                    key=lambda x: abs(x-curr))[:4]
    s_filt = sorted(list(dict.fromkeys([round(s,5) for s in sup if s < curr])),
                    key=lambda x: abs(x-curr))[:4]
    return r_filt, s_filt

def find_swing_levels(rows, n=5):
    """Daglige/4H nivåer for kontekst"""
    curr = rows[-1][2]
    res, sup = [], []
    for i in range(n, len(rows)-n):
        if rows[i][0] == max(r[0] for r in rows[i-n:i+n+1]):
            res.append(rows[i][0])
        if rows[i][1] == min(r[1] for r in rows[i-n:i+n+1]):
            sup.append(rows[i][1])
    r_filt = sorted(list(dict.fromkeys([round(r,5) for r in res if r > curr])),
                    key=lambda x: abs(x-curr))[:3]
    s_filt = sorted(list(dict.fromkeys([round(s,5) for s in sup if s < curr])),
                    key=lambda x: abs(x-curr))[:3]
    return r_filt, s_filt

def is_at_level(curr, level, atr_15m, weight=1):
    """
    Hard sjekk: pris MÅ være innen tight×ATR(15m) fra nivå.
    HTF-nivåer (weight>=3) får litt mer toleranse siden de er soner, ikke linjer.
      weight 1 (15m):    0.30×ATR
      weight 2 (4H/SMC): 0.35×ATR
      weight 3+ (D1/Ukentlig): 0.45×ATR
    """
    tight = 0.30 if weight <= 1 else (0.35 if weight == 2 else 0.45)
    return abs(curr - level) <= atr_15m * tight

def merge_tagged_levels(tagged, curr, atr, max_n=6):
    """
    Slår sammen nivåer som er innen 0.5×ATR av hverandre.
    Beholder det med høyest weight (tidsvindus-styrke).
    Sorterer etter nærhet til nåpris.

    Vektskala:
      1 = 15m pivot (svakest)
      2 = 4H swing / SMC-sone
      3 = Daglig swing / PDC
      4 = PDH / PDL
      5 = PWH / PWL (sterkest)
    """
    if not tagged:
        return []
    atr_buf = (atr or 0) * 0.5
    merged = []
    for lvl in sorted(tagged, key=lambda x: abs(x["price"] - curr)):
        absorbed = False
        for m in merged:
            if atr_buf > 0 and abs(lvl["price"] - m["price"]) < atr_buf:
                # Behold høyest weight; oppdater kilde og pris hvis sterkere
                if lvl["weight"] > m["weight"]:
                    m["price"]  = lvl["price"]
                    m["source"] = lvl["source"]
                    m["weight"] = lvl["weight"]
                absorbed = True
                break
        if not absorbed:
            merged.append(dict(lvl))
    return sorted(merged, key=lambda x: abs(x["price"] - curr))[:max_n]


def make_setup_l2l(curr, atr_15m, atr_daily, sup_tagged, res_tagged, direction, klasse, min_rr=1.5):
    """
    Level-til-level intradag med tidsvindus-vekting:
    - Entry: nærmeste nivå (hvilken som helst TF)
    - SL: rett bak entry-nivå + 1.5×spread
    - T1: nærmeste HTF-nivå (weight>=3, D1+) på motsatt side.
          Faller tilbake på nærmeste nivå uansett TF hvis ingen D1+ finnes.
    - T2: neste nivå etter T1
    - entry_weight i output → frontend kan vise styrke-badge
    - Dropp hvis R:R < min_rr eller SL > 2.5×ATR(15m)
    """
    if not atr_15m or atr_15m <= 0:
        return None
    spread_buf = atr_15m * 0.15

    def best_t1(levels, min_w=3):
        """
        Velg T1-mål med prioritet:
          1. Nærmeste nivå med weight >= min_w (D1+)
          2. Nærmeste nivå med weight >= 2 (4H/SMC) — fallback
          3. Nærmeste nivå uansett (siste utvei, merkes som svak T1)
        Returnerer nivå-obj med ekstra felt 't1_quality': 'htf'|'4h'|'weak'
        """
        for l in levels:
            if l["weight"] >= min_w:
                return dict(l, t1_quality="htf")
        for l in levels:
            if l["weight"] >= 2:
                return dict(l, t1_quality="4h")
        if levels:
            return dict(levels[0], t1_quality="weak")
        return None

    if direction == "long":
        if not sup_tagged or not res_tagged:
            return None
        entry_obj   = sup_tagged[0]
        entry_level = entry_obj["price"]
        entry_w     = entry_obj["weight"]

        sl   = entry_level - spread_buf
        risk = curr - sl
        if risk <= 0:             return None
        if risk > atr_15m * 2.5: return None

        t1_obj = best_t1(res_tagged, min_w=3)
        if t1_obj is None:        return None
        t1 = t1_obj["price"]

        # T2: neste nivå etter T1 (uansett weight)
        res_after = [l for l in res_tagged if l["price"] > t1]
        t2 = res_after[0]["price"] if res_after else round(t1 + risk, 5)

        rr1 = round((t1 - curr) / risk, 2)
        rr2 = round((t2 - curr) / risk, 2)
        if rr1 < min_rr: return None

        at_level = is_at_level(curr, entry_level, atr_15m, entry_w)
        q = t1_obj.get("t1_quality", "weak")
        return {
            "entry": round(curr, 5), "sl": round(sl, 5),
            "t1": round(t1, 5),     "t2": round(t2, 5),
            "rr_t1": rr1, "rr_t2": rr2, "min_rr": min_rr,
            "entry_dist_atr":  round(abs(curr - entry_level) / atr_15m, 2),
            "entry_name":      f"Støtte {round(entry_level,5)} [{entry_obj['source']}]",
            "entry_level":     round(entry_level, 5),
            "entry_weight":    entry_w,
            "t1_source":       t1_obj["source"],
            "t1_weight":       t1_obj["weight"],
            "t1_quality":      q,
            "status":          "aktiv" if at_level else "watchlist",
            "note": (f"L2L: S {round(entry_level,4)} [{entry_obj['source']} w{entry_w}]"
                     f" → T1 {round(t1,4)} [{t1_obj['source']} w{t1_obj['weight']} {q}]"
                     f" | SL={round(sl,4)} | ATR15m={round(atr_15m,4)}"),
            "timeframe": "15m",
        }
    else:
        if not res_tagged or not sup_tagged:
            return None
        entry_obj   = res_tagged[0]
        entry_level = entry_obj["price"]
        entry_w     = entry_obj["weight"]

        sl   = entry_level + spread_buf
        risk = sl - curr
        if risk <= 0:             return None
        if risk > atr_15m * 2.5: return None

        t1_obj = best_t1(sup_tagged, min_w=3)
        if t1_obj is None:        return None
        t1 = t1_obj["price"]

        sup_after = [l for l in sup_tagged if l["price"] < t1]
        t2 = sup_after[0]["price"] if sup_after else round(t1 - risk, 5)

        rr1 = round((curr - t1) / risk, 2)
        rr2 = round((curr - t2) / risk, 2)
        if rr1 < min_rr: return None

        at_level = is_at_level(curr, entry_level, atr_15m, entry_w)
        q = t1_obj.get("t1_quality", "weak")
        return {
            "entry": round(curr, 5), "sl": round(sl, 5),
            "t1": round(t1, 5),     "t2": round(t2, 5),
            "rr_t1": rr1, "rr_t2": rr2, "min_rr": min_rr,
            "entry_dist_atr":  round(abs(curr - entry_level) / atr_15m, 2),
            "entry_name":      f"Motstand {round(entry_level,5)} [{entry_obj['source']}]",
            "entry_level":     round(entry_level, 5),
            "entry_weight":    entry_w,
            "t1_source":       t1_obj["source"],
            "t1_weight":       t1_obj["weight"],
            "t1_quality":      q,
            "status":          "aktiv" if at_level else "watchlist",
            "note": (f"L2L: R {round(entry_level,4)} [{entry_obj['source']} w{entry_w}]"
                     f" → T1 {round(t1,4)} [{t1_obj['source']} w{t1_obj['weight']} {q}]"
                     f" | SL={round(sl,4)} | ATR15m={round(atr_15m,4)}"),
            "timeframe": "15m",
        }

def fetch_fear_greed():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://edition.cnn.com/markets/fear-and-greed",
            "Origin": "https://edition.cnn.com",
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
        return {"score": round(d["fear_and_greed"]["score"],1),
                "rating": d["fear_and_greed"]["rating"]}
    except Exception as e:
        print(f"  Fear&Greed FEIL: {e}")
        return None

def detect_conflict(vix, dxy_5d, fg, cot_usd):
    conflicts = []
    if vix > 25 and dxy_5d < 0:
        conflicts.append("VIX>25 men DXY faller – risk-off uten USD-etterspørsel")
    if fg and fg["score"] < 30 and dxy_5d < 0:
        conflicts.append("Ekstrem frykt men USD svekkes – unormalt")
    if fg and fg["score"] > 70 and vix > 22:
        conflicts.append("Grådighet men VIX forhøyet – divergens")
    if cot_usd and cot_usd > 0 and dxy_5d < -1:
        conflicts.append("COT long USD men pris faller – divergens")
    return conflicts

# ── Last kalender ────────────────────────────────────────────
calendar_events = []
cal_file = os.path.join(BASE, 'calendar', 'latest.json')
if os.path.exists(cal_file):
    try:
        with open(cal_file) as f:
            cal_data = json.load(f)
        calendar_events = cal_data.get('events', [])
        print(f'Kalender: {len(calendar_events)} events lastet')
    except:
        pass

def get_binary_risk(instrument_key, hours=4):
    risks = []
    for ev in calendar_events:
        if ev.get('impact') != 'High': continue
        ha = ev.get('hours_away', 99)
        if ha < 0 or ha > hours: continue
        berorte = ev.get('berorte', [])
        if instrument_key in berorte or not berorte:
            risks.append({'title': ev['title'], 'cet': ev['cet'], 'country': ev['country']})
    return risks

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
if fg: print(f"  → {fg['score']} ({fg['rating']})")

# ── Priser og setups ──────────────────────────────────────
prices, levels = {}, {}

for inst in INSTRUMENTS:
    print(f"Henter {inst['navn']}...")

    daily   = fetch_yahoo(inst["symbol"], "1d", "1y")
    rows_15m = fetch_yahoo(inst["symbol"], "15m", "5d")
    rows_1h  = fetch_yahoo(inst["symbol"], "60m", "60d")
    h4       = to_4h(rows_1h) if rows_1h else []

    if not daily or len(daily) < 15:
        continue

    curr     = daily[-1][2]
    # Bruk siste 15m close hvis tilgjengelig (mer oppdatert)
    if rows_15m and len(rows_15m) > 0:
        curr = rows_15m[-1][2]

    atr_d    = calc_atr(daily, 14)
    atr_15m  = calc_atr(rows_15m, 14) if len(rows_15m) >= 15 else None
    atr_4h   = calc_atr(h4, 14) if len(h4) >= 15 else None
    sma200   = sum(r[2] for r in daily[-200:]) / min(200, len(daily))

    c1  = daily[-2][2] if len(daily)>=2  else curr
    c5  = daily[-6][2] if len(daily)>=6  else curr
    c20 = daily[-21][2] if len(daily)>=21 else curr
    prices[inst["key"]] = {
        "price":  round(curr, 4 if curr<100 else 2),
        "chg1d":  round((curr/c1-1)*100,  2),
        "chg5d":  round((curr/c5-1)*100,  2),
        "chg20d": round((curr/c20-1)*100, 2),
    }

    if inst["key"] == "VIX": continue

    # ── SMC analyse ──────────────────────────────────────
    smc = None
    if SMC_OK and rows_15m and len(rows_15m) > 50:
        try:
            smc = run_smc(rows_15m, swing_length=5)
        except Exception as e:
            print(f"  SMC FEIL: {e}")

    # ── Nivåer med tidsvindus-vekting ────────────────────
    #  weight 5 = Ukentlig (sterkest), 4 = PDH/PDL, 3 = D1 swing/PDC,
    #  weight 2 = 4H / SMC-sone,       1 = 15m pivot (svakest)
    pdh, pdl, pdc = get_pdh_pdl_pdc(daily)
    pwh, pwl      = get_pwh_pwl(daily)

    raw_res, raw_sup = [], []

    # Ukentlige nøkkelnivåer (weight 5)
    if pwh and pwh > curr: raw_res.append({"price": pwh, "source": "PWH", "weight": 5})
    if pwl and pwl < curr: raw_sup.append({"price": pwl, "source": "PWL", "weight": 5})

    # Daglige nøkkelnivåer (weight 4)
    if pdh and pdh > curr: raw_res.append({"price": pdh, "source": "PDH", "weight": 4})
    if pdl and pdl < curr: raw_sup.append({"price": pdl, "source": "PDL", "weight": 4})

    # PDC (weight 3)
    if pdc:
        if pdc > curr: raw_res.append({"price": pdc, "source": "PDC", "weight": 3})
        elif pdc < curr: raw_sup.append({"price": pdc, "source": "PDC", "weight": 3})

    # Daglige swing-nivåer (weight 3)
    res_d, sup_d = find_swing_levels(daily)
    for r in res_d:
        if r > curr: raw_res.append({"price": r, "source": "D1", "weight": 3})
    for s in sup_d:
        if s < curr: raw_sup.append({"price": s, "source": "D1", "weight": 3})

    # 4H swing-nivåer (weight 2)
    res_4h, sup_4h = find_swing_levels(h4, n=3) if len(h4) >= 10 else ([], [])
    for r in res_4h:
        if r > curr: raw_res.append({"price": r, "source": "4H", "weight": 2})
    for s in sup_4h:
        if s < curr: raw_sup.append({"price": s, "source": "4H", "weight": 2})

    # SMC supply/demand-soner (weight 2 — struktur-basert men fra 15m)
    if smc:
        for z in smc.get("supply_zones", []):
            if z["poi"] > curr: raw_res.append({"price": z["poi"], "source": "SMC", "weight": 2})
        for z in smc.get("demand_zones", []):
            if z["poi"] < curr: raw_sup.append({"price": z["poi"], "source": "SMC", "weight": 2})

    # 15m intradag-pivots (weight 1 — svakest, kun for lokal entry-presisjon)
    res_15m, sup_15m = find_intraday_levels(rows_15m) if rows_15m else ([], [])
    for r in res_15m:
        if r > curr: raw_res.append({"price": r, "source": "15m", "weight": 1})
    for s in sup_15m:
        if s < curr: raw_sup.append({"price": s, "source": "15m", "weight": 1})

    atr_for_merge = atr_15m if atr_15m else (atr_d * 0.4 if atr_d else None)

    # Merge: nivåer innen 0.5×ATR slås sammen, høyest weight vinner
    tagged_res = merge_tagged_levels(raw_res, curr, atr_for_merge)
    tagged_sup = merge_tagged_levels(raw_sup, curr, atr_for_merge)

    # Flate lister for bakoverkompatibilitet (fmt_level, is_at_level)
    all_res = [l["price"] for l in tagged_res]
    all_sup = [l["price"] for l in tagged_sup]

    # ── EMA9 + Regime ─────────────────────────────────────
    closes_d  = [r[2] for r in daily]
    closes_15 = [r[2] for r in rows_15m] if rows_15m else []
    ema9_d    = calc_ema(closes_d,  9)
    ema9_15m  = calc_ema(closes_15, 9) if closes_15 else None

    d1_bull  = curr > ema9_d   if ema9_d  else None
    m15_bull = curr > ema9_15m if ema9_15m else None
    d1_regime  = ("BULLISH" if d1_bull  else "BEARISH") if d1_bull  is not None else "NØYTRAL"
    m15_regime = ("BULLISH" if m15_bull else "BEARISH") if m15_bull is not None else "NØYTRAL"

    if d1_bull and m15_bull:       align = "bull"
    elif not d1_bull and not m15_bull: align = "bear"
    else:                           align = "mixed"

    session_now = get_session_status()

    # ── COT ───────────────────────────────────────────────
    cot_key   = COT_MAP.get(inst["key"],"")
    cot_entry = cot_data.get(cot_key, {})
    spec_net  = (cot_entry.get("spekulanter") or {}).get("net", 0) or 0
    oi        = cot_entry.get("open_interest", 1) or 1
    cot_pct   = spec_net / oi * 100
    cot_bias  = "LONG" if cot_pct>4 else "SHORT" if cot_pct<-4 else "NØYTRAL"
    cot_color = "bull"  if cot_pct>4 else "bear"  if cot_pct<-4 else "neutral"

    # ── Score ─────────────────────────────────────────────
    above_sma = curr > sma200
    chg5      = prices[inst["key"]]["chg5d"]
    chg20     = prices[inst["key"]]["chg20d"]
    fg_score  = fg["score"] if fg else 50

    # Pris VED nivå nå — vektbevisst sjekk
    at_sup = any(
        is_at_level(curr, l["price"], atr_for_merge or atr_d*0.4, l["weight"])
        for l in tagged_sup
    ) if tagged_sup else False
    at_res = any(
        is_at_level(curr, l["price"], atr_for_merge or atr_d*0.4, l["weight"])
        for l in tagged_res
    ) if tagged_res else False
    at_level_now = at_sup or at_res

    # Nærmeste nivå har HTF-styrke (D1 / ukentlig / PDH/PDL → weight >= 3)
    nearest_sup_w = tagged_sup[0]["weight"] if tagged_sup else 0
    nearest_res_w = tagged_res[0]["weight"] if tagged_res else 0
    htf_level_nearby = max(nearest_sup_w, nearest_res_w) >= 3

    # Sesjon aktiv nå
    sesjon_aktiv = session_now["active"]
    klasse = inst["klasse"]
    sesjon_riktig = (
        (klasse == "A" and "London" in session_now["label"]) or
        (klasse == "B" and ("London" in session_now["label"] or "NY" in session_now["label"])) or
        (klasse == "C" and "NY" in session_now["label"])
    )

    cot_confirms = (cot_bias == "LONG" and dir_color == "bull") or \
                   (cot_bias == "SHORT" and dir_color == "bear")
    score_details = [
        {"kryss": "Over SMA200",             "verdi": above_sma},
        {"kryss": "D1 + 15m regime likt",    "verdi": align in ("bull","bear")},
        {"kryss": "COT bekrefter",           "verdi": cot_confirms},
        {"kryss": "Pris VED nivå nå",        "verdi": at_level_now},
        {"kryss": "HTF-nivå (D1+) bekrefter","verdi": htf_level_nearby},
        {"kryss": "Riktig sesjon aktiv",     "verdi": sesjon_riktig},
        {"kryss": "Momentum 20d",            "verdi": chg20 > 0},
        {"kryss": "Sentiment",               "verdi": fg_score < 35},
    ]
    score       = sum(1 for s in score_details if s["verdi"])
    grade       = "A+" if score>=7 else "A" if score>=5 else "B" if score>=3 else "C"
    grade_color = "bull" if score>=7 else "warn" if score>=5 else "bear"
    dir_color   = "bull" if (above_sma and chg5>0) else "bear" if (not above_sma and chg5<0) else ("bull" if above_sma else "bear")

    vix_price = (prices.get("VIX") or {}).get("price", 20)
    pos_size  = "Full" if vix_price<20 else "Halv" if vix_price<30 else "Kvart"

    # ── Setups med tagget nivåer ──────────────────────────
    atr_for_setup = atr_15m if atr_15m else (atr_d * 0.4)
    setup_long  = make_setup_l2l(curr, atr_for_setup, atr_d, tagged_sup, tagged_res, "long",  klasse)
    setup_short = make_setup_l2l(curr, atr_for_setup, atr_d, tagged_sup, tagged_res, "short", klasse)
    for s in [setup_long, setup_short]:
        if s: s["session"] = inst["session"]

    def fmt_level(tagged, typ, atr):
        out = []
        for i, l in enumerate(tagged[:5]):
            lr = round(l["price"], 5 if l["price"] < 100 else 2)
            out.append({
                "name":     l.get("source", f"{typ}{i+1}"),
                "level":    lr,
                "weight":   l.get("weight", 1),
                "dist_atr": round(abs(l["price"] - curr) / (atr or 1), 1),
            })
        return out

    atr_s = f"{atr_15m:.5f}" if atr_15m else "N/A"
    sl_s  = setup_long["sl"]  if setup_long  else "-"
    t1_s  = setup_long["t1"]  if setup_long  else "-"
    rr_s  = setup_long["rr_t1"] if setup_long else "-"
    st    = "🟢" if at_level_now else "🟡"
    htf_tag = f"HTF:w{max(nearest_sup_w, nearest_res_w)}" if htf_level_nearby else "noHTF"
    print(f"  {st} {inst['navn']:10s} {curr:.5f}  ATR15m={atr_s}  {grade}({score}/8)  {htf_tag}  T1:{t1_s}  R:R:{rr_s}")

    levels[inst["key"]] = {
        "name":          inst["navn"],
        "label":         inst["label"],
        "klasse":        klasse,
        "session":       inst["session"],
        "class":         inst["kat"][0].upper(),
        "current":       round(curr, 5 if curr<100 else 2),
        "atr14":         round(atr_15m, 5) if atr_15m else None,
        "atr_15m":       round(atr_15m, 5) if atr_15m else None,
        "atr_daily":     round(atr_d,   5) if atr_d   else None,
        "atr_4h":        round(atr_4h,  5) if atr_4h  else None,
        "at_level_now":  at_level_now,
        "status":        "aktiv" if at_level_now else "watchlist",
        "pdh": round(pdh,5) if pdh else None,
        "pdl": round(pdl,5) if pdl else None,
        "pdc": round(pdc,5) if pdc else None,
        "pwh": round(pwh,5) if pwh else None,
        "pwl": round(pwl,5) if pwl else None,
        "ema9_d1":       round(ema9_d,   5) if ema9_d   else None,
        "ema9_15m":      round(ema9_15m, 5) if ema9_15m else None,
        "ema9_above":    curr > ema9_d if ema9_d else None,
        "d1_regime":     d1_regime,
        "m15_regime":    m15_regime,
        "regime_align":  align,
        "session_now":   session_now,
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
        "resistances":   fmt_level(tagged_res, "R", atr_15m or atr_d),
        "supports":      fmt_level(tagged_sup, "S", atr_15m or atr_d),
        "setup_long":    setup_long,
        "setup_short":   setup_short,
        "binary_risk":   get_binary_risk(inst["key"]),
        "smc": {
            "structure":    smc["structure"]    if smc else None,
            "supply_zones": smc["supply_zones"] if smc else [],
            "demand_zones": smc["demand_zones"] if smc else [],
            "bos_levels":   smc["bos_levels"]   if smc else [],
            "last_swing_high": smc["last_swing_high"] if smc else None,
            "last_swing_low":  smc["last_swing_low"]  if smc else None,
        },
        "dxy_conf":      "medvind" if (inst["kat"]=="valuta" and (prices.get("DXY") or {}).get("chg5d",0)<0) else "motvind",
        "pos_size":      pos_size,
        "vix_spread_factor": 1.0 if vix_price<20 else 1.5 if vix_price<30 else 2.0,
        "cot":           {"bias": cot_bias, "color": cot_color, "net": spec_net,
                          "chg": cot_entry.get("change_spec_net",0), "pct": round(abs(cot_pct),1),
                          "date": cot_entry.get("date",""), "report": cot_entry.get("report","")},
        "combined_bias": "LONG" if dir_color=="bull" else "SHORT",
        "sentiment":     {"fear_greed": fg},
    }

# ── Makro ──────────────────────────────────────────────────
vix_price   = (prices.get("VIX") or {}).get("price", 20)
dxy_5d      = (prices.get("DXY") or {}).get("chg5d", 0)
brent_p     = (prices.get("Brent") or {}).get("price", 80)
fg_score    = fg["score"] if fg else 50
cot_dxy     = cot_data.get("usd index",{})
cot_dxy_net = ((cot_dxy.get("spekulanter") or {}).get("net",0) or 0)
conflicts   = detect_conflict(vix_price, dxy_5d, fg, cot_dxy_net)

if conflicts:
    smile_pos,usd_bias,usd_color,smile_desc = "konflikt","UKLAR","warn","Motstridende signaler: "+" | ".join(conflicts[:2])
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
        "position":smile_pos,"usd_bias":usd_bias,"usd_color":usd_color,"desc":smile_desc,
        "conflicts": conflicts,
        "inputs":{"vix":vix_price,"hy_stress":False,"brent":brent_p,"tip_trend_5d":0,"dxy_trend_5d":dxy_5d}
    },
    "trading_levels": levels,
    "calendar": calendar_events,
}

with open(OUT,"w") as f:
    json.dump(macro, f, ensure_ascii=False, indent=2)
print(f"\nOK → {OUT}  ({len(levels)} instruments)")
if conflicts:
    print("Konflikter:"); [print(f"  ⚠️  {c}") for c in conflicts]
