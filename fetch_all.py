#!/usr/bin/env python3
import urllib.request, urllib.parse, json, os
from datetime import datetime, timezone

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

def get_pdh_pdl_pdc(daily):
    """Gårsdagens high/low/close"""
    if len(daily) < 2: return None,None,None
    return daily[-2][0], daily[-2][1], daily[-2][2]

def get_pwh_pwl(daily):
    """Forrige ukes high/low (siste 6-10 dager, ekskl denne uken)"""
    if len(daily) < 10: return None,None
    week = daily[-8:-1]  # ca forrige uke
    return max(r[0] for r in week), min(r[1] for r in week)

def get_session_status():
    """Returner aktiv sesjon basert på UTC-tid"""
    from datetime import datetime, timezone
    h = datetime.now(timezone.utc).hour
    m = datetime.now(timezone.utc).minute
    t = h*60 + m
    # CET = UTC+1 (vinter) / UTC+2 (sommer) — bruker UTC+1
    cet = (t + 60) % (24*60)
    ch  = cet // 60
    sessions = []
    if 7*60 <= cet < 12*60:   sessions.append("London")
    if 13*60 <= cet < 17*60:  sessions.append("NY Overlap")
    if 8*60 <= cet < 12*60:   sessions.append("London Fix")
    if not sessions:           sessions.append("Off-session")
    return {"active": bool([s for s in sessions if s != "Off-session"]),
            "label": " / ".join(sessions), "cet_hour": ch}

def regime_alignment(closes_d1, closes_4h, curr):
    """Enkel regime: pris vs EMA9 på D1 og 4H"""
    ema_d1 = calc_ema(closes_d1, 9)
    ema_4h = calc_ema(closes_4h, 9) if closes_4h else None
    d1_bull = curr > ema_d1 if ema_d1 else None
    h4_bull = curr > ema_4h if ema_4h else None
    if d1_bull is None: return "NØYTRAL","NØYTRAL","—"
    d1_r = "BULLISH" if d1_bull else "BEARISH"
    h4_r = ("BULLISH" if h4_bull else "BEARISH") if h4_bull is not None else "NØYTRAL"
    # Alignment
    if d1_bull and (h4_bull or h4_bull is None): align = "bull"
    elif not d1_bull and not h4_bull:             align = "bear"
    else:                                          align = "mixed"
    return d1_r, h4_r, align

def to_4h(rows_1h):
    out = []
    for i in range(0, len(rows_1h)-3, 4):
        grp = rows_1h[i:i+4]
        h = max(r[0] for r in grp)
        l = min(r[1] for r in grp)
        c = grp[-1][2]
        out.append((h,l,c))
    return out

def find_levels(rows, n=5):
    """Finn støtte/motstand fra lokale topper og bunner"""
    curr = rows[-1][2]
    res, sup = [], []
    for i in range(n, len(rows)-n):
        if rows[i][0] == max(r[0] for r in rows[i-n:i+n+1]):
            res.append(rows[i][0])
        if rows[i][1] == min(r[1] for r in rows[i-n:i+n+1]):
            sup.append(rows[i][1])
    r_filt = sorted(list(set([r for r in res if r > curr])), key=lambda x: abs(x-curr))[:4]
    s_filt = sorted(list(set([s for s in sup if s < curr])), key=lambda x: abs(x-curr))[:4]
    return r_filt, s_filt

def make_setup_level2level(curr, atr, sup_levels, res_levels, direction, klasse, min_rr=1.5):
    """
    LEVEL-TIL-LEVEL logikk:
    - Entry: nåpris (MÅ være nær et nivå)
    - SL: rett bak nærmeste nivå i motsatt retning
    - T1: NESTE faktiske nivå i handelsretningen
    - T2: Nivå etter det
    - Dropp setup hvis R:R < min_rr
    """
    if not atr or atr <= 0: return None

    # Spread-buffer per klasse
    spread_mult = 1.5
    spread_buf = atr * 0.08 * spread_mult

    if direction == "long":
        if not sup_levels or not res_levels: return None
        entry_level = sup_levels[0]   # Vi er VED støtten
        sl = entry_level - spread_buf
        risk = curr - sl
        if risk <= 0: return None

        # T1 = nærmeste motstand, T2 = neste
        t1 = res_levels[0]
        t2 = res_levels[1] if len(res_levels) > 1 else t1 + risk

        reward1 = t1 - curr
        reward2 = t2 - curr
        rr1 = round(reward1 / risk, 2)
        rr2 = round(reward2 / risk, 2)

        if rr1 < min_rr:
            return None  # T1 for nær — ikke verdt det

        dist_atr = round(abs(curr - entry_level) / atr, 2)
        status = "aktiv" if dist_atr <= 1.0 else "watchlist"

        return {
            "entry": round(curr, 5), "sl": round(sl, 5),
            "t1": round(t1, 5), "t2": round(t2, 5),
            "rr_t1": rr1, "rr_t2": rr2, "min_rr": min_rr,
            "entry_dist_atr": dist_atr,
            "entry_name": f"Støtte {round(entry_level,4)}",
            "entry_level": round(entry_level, 5),
            "status": status,
            "note": f"L2L: {round(entry_level,4)} → T1 {round(t1,4)} | SL bak støtte. ATR={round(atr,4)}",
            "timeframe": "4h-intradag",
            "session": "",
        }
    else:  # short
        if not res_levels or not sup_levels: return None
        entry_level = res_levels[0]   # Vi er VED motstanden
        sl = entry_level + spread_buf
        risk = sl - curr
        if risk <= 0: return None

        t1 = sup_levels[0]
        t2 = sup_levels[1] if len(sup_levels) > 1 else t1 - risk

        reward1 = curr - t1
        reward2 = curr - t2
        rr1 = round(reward1 / risk, 2)
        rr2 = round(reward2 / risk, 2)

        if rr1 < min_rr:
            return None

        dist_atr = round(abs(curr - entry_level) / atr, 2)
        status = "aktiv" if dist_atr <= 1.0 else "watchlist"

        return {
            "entry": round(curr, 5), "sl": round(sl, 5),
            "t1": round(t1, 5), "t2": round(t2, 5),
            "rr_t1": rr1, "rr_t2": rr2, "min_rr": min_rr,
            "entry_dist_atr": dist_atr,
            "entry_name": f"Motstand {round(entry_level,4)}",
            "entry_level": round(entry_level, 5),
            "status": status,
            "note": f"L2L: {round(entry_level,4)} → T1 {round(t1,4)} | SL bak motstand. ATR={round(atr,4)}",
            "timeframe": "4h-intradag",
            "session": "",
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
        score = d["fear_and_greed"]["score"]
        rating = d["fear_and_greed"]["rating"]
        return {"score": round(score,1), "rating": rating}
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
        conflicts.append("COT long USD men pris faller – smart money vs marked")
    return conflicts

# ── Last COT (siste uke) ───────────────────────────────────
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

# ── Hent priser og bygg setups ────────────────────────────
prices, levels = {}, {}

for inst in INSTRUMENTS:
    print(f"Henter {inst['navn']}...")

    daily  = fetch_yahoo(inst["symbol"], "1d", "1y")
    h1_raw = fetch_yahoo(inst["symbol"], "60m", "60d")
    h4     = to_4h(h1_raw) if h1_raw else []

    if not daily or len(daily) < 15:
        continue

    curr   = daily[-1][2]
    atr_d  = calc_atr(daily, 14)
    atr_4h = calc_atr(h4, 14) if len(h4) >= 15 else None
    atr_use = atr_4h if atr_4h else atr_d
    sma200 = sum(r[2] for r in daily[-200:]) / min(200, len(daily))

    c1  = daily[-2][2] if len(daily)>=2  else curr
    c5  = daily[-6][2] if len(daily)>=6  else curr
    c20 = daily[-21][2] if len(daily)>=21 else curr
    prices[inst["key"]] = {
        "price":  round(curr, 4 if curr<100 else 2),
        "chg1d":  round((curr/c1-1)*100, 2),
        "chg5d":  round((curr/c5-1)*100, 2),
        "chg20d": round((curr/c20-1)*100, 2),
    }

    if inst["key"] == "VIX": continue

    # Nivåer fra 4h (intradag) og daglig (swing)
    lvl_rows = h4 if len(h4) > 20 else daily
    res_lvl, sup_lvl = find_levels(lvl_rows)

    # ── PDH / PDL / PDC / PWH / PWL / EMA9 ─────────────────
    pdh, pdl, pdc = get_pdh_pdl_pdc(daily)
    pwh, pwl      = get_pwh_pwl(daily)
    closes_d1     = [r[2] for r in daily]
    closes_4h     = [r[2] for r in h4]
    ema9_d1       = calc_ema(closes_d1, 9)
    ema9_4h       = calc_ema(closes_4h, 9) if closes_4h else None
    d1_regime, h4_regime, align = regime_alignment(closes_d1, closes_4h, curr)
    session_now   = get_session_status()

    # Legg PDH/PDL/PWH/PWL til nivålister
    extra_res, extra_sup = [], []
    for lvl, name in [(pdh,"PDH"),(pwh,"PWH"),(pdc,"PDC")]:
        if lvl and lvl > curr: extra_res.append((lvl, name))
    for lvl, name in [(pdl,"PDL"),(pwl,"PWL"),(pdc,"PDC")]:
        if lvl and lvl < curr: extra_sup.append((lvl, name))

    # Slå sammen med tekniske nivåer og sorter
    all_res = sorted(list(set(res_lvl)) + [x[0] for x in extra_res if x[0] > curr], key=lambda x: abs(x-curr))[:5]
    all_sup = sorted(list(set(sup_lvl)) + [x[0] for x in extra_sup if x[0] < curr], key=lambda x: abs(x-curr))[:5]

    # Merk kilde per nivå
    lvl_sources = {round(pdh,5):"PDH", round(pdl,5):"PDL", round(pdc,5):"PDC",
                   round(pwh,5):"PWH" if pwh else None, round(pwl,5):"PWL" if pwl else None}

    # ── COT
    cot_key   = COT_MAP.get(inst["key"],"")
    cot_entry = cot_data.get(cot_key, {})
    spec_net  = (cot_entry.get("spekulanter") or {}).get("net", 0) or 0
    oi        = cot_entry.get("open_interest", 1) or 1
    cot_pct   = spec_net / oi * 100
    cot_bias  = "LONG" if cot_pct>4 else "SHORT" if cot_pct<-4 else "NØYTRAL"
    cot_color = "bull"  if cot_pct>4 else "bear"  if cot_pct<-4 else "neutral"

    above_sma = curr > sma200
    chg5      = prices[inst["key"]]["chg5d"]
    chg20     = prices[inst["key"]]["chg20d"]
    fg_score  = fg["score"] if fg else 50
    sent_bull = fg_score < 35

    # Score 8 punkter
    score_details = [
        {"kryss":"Over SMA200",           "verdi": above_sma},
        {"kryss":"5d trend opp",           "verdi": chg5 > 0},
        {"kryss":"COT long bias",          "verdi": cot_pct > 4},
        {"kryss":"COT ikke short",         "verdi": cot_pct > -4},
        {"kryss":"Støtte nær (≤1×ATR)",   "verdi": bool(sup_lvl and atr_use and abs(curr-sup_lvl[0]) <= atr_use)},
        {"kryss":"Motstand fritt (>1.5×)","verdi": bool(res_lvl and atr_use and abs(curr-res_lvl[0]) > atr_use*1.5)},
        {"kryss":"Momentum 20d",           "verdi": chg20 > 0},
        {"kryss":"Sentiment bekrefter",    "verdi": sent_bull},
    ]
    score       = sum(1 for s in score_details if s["verdi"])
    grade       = "A+" if score>=7 else "B" if score>=5 else "C"
    grade_color = "bull" if score>=7 else "warn" if score>=5 else "bear"
    dir_color   = "bull" if (above_sma and chg5>0) else "bear" if (not above_sma and chg5<0) else ("bull" if above_sma else "bear")

    vix_price = (prices.get("VIX") or {}).get("price", 20)
    pos_size  = "Full" if vix_price<20 else "Halv" if vix_price<30 else "Kvart"

    # L2L setups — T1/T2 er faktiske nivåer
    klasse       = inst.get("klasse","B")
    setup_long   = make_setup_level2level(curr, atr_use, all_sup, all_res, "long",  klasse)
    setup_short  = make_setup_level2level(curr, atr_use, all_sup, all_res, "short", klasse)

    # Sett sesjon på setupene
    for s in [setup_long, setup_short]:
        if s: s["session"] = inst["session"]

    # Aktiv-status basert på nærmeste nivå
    nearest_sup  = abs(curr - sup_lvl[0]) / atr_use if sup_lvl and atr_use else 99
    nearest_res  = abs(curr - res_lvl[0]) / atr_use if res_lvl and atr_use else 99
    is_active    = min(nearest_sup, nearest_res) <= 1.0
    status_label = "aktiv" if is_active else "watchlist"

    def fmt_level(lvl, typ, atr):
        out = []
        for i,l in enumerate(lvl[:5]):
            lr = round(l, 5 if l<100 else 2)
            src = lvl_sources.get(round(l,5), f"{typ}{i+1}")
            out.append({"name": src, "level": lr,
                        "dist_atr": round(abs(l-curr)/(atr or 1), 1)})
        return out

    levels[inst["key"]] = {
        "name":          inst["navn"],
        "label":         inst["label"],
        "klasse":        klasse,
        "session":       inst["session"],
        "class":         inst["kat"][0].upper(),
        "current":       round(curr, 4 if curr<100 else 2),
        "atr14":         round(atr_use, 5) if atr_use else None,
        "atr_daily":     round(atr_d,  5) if atr_d  else None,
        "atr_4h":        round(atr_4h, 5) if atr_4h else None,
        "status":        status_label,
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
        "resistances":   fmt_level(all_res,"R",atr_use),
        "supports":      fmt_level(all_sup,"S",atr_use),
        "setup_long":    setup_long,
        "setup_short":   setup_short,
        "binary_risk":   [],
        "pdh": round(pdh,5) if pdh else None,
        "pdl": round(pdl,5) if pdl else None,
        "pdc": round(pdc,5) if pdc else None,
        "pwh": round(pwh,5) if pwh else None,
        "pwl": round(pwl,5) if pwl else None,
        "ema9_d1": round(ema9_d1,5) if ema9_d1 else None,
        "ema9_4h": round(ema9_4h,5) if ema9_4h else None,
        "ema9_above": curr > ema9_d1 if ema9_d1 else None,
        "d1_regime": d1_regime,
        "h4_regime": h4_regime,
        "regime_align": align,
        "session_now": session_now,
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
        "sentiment":     {"fear_greed": fg},
    }

    sl  = setup_long["sl"] if setup_long else "-"
    t1  = setup_long["t1"] if setup_long else "-"
    rr  = setup_long["rr_t1"] if setup_long else "-"
    st  = "🟢" if status_label=="aktiv" else "🟡"
    atr_s = f"{atr_use:.4f}" if atr_use else "N/A"
    print(f"  {st} {inst['navn']:10s} {curr:.4f}  ATR={atr_s}  {grade}({score}/8)  L→T1:{t1}  R:R:{rr}")

# ── Makro ──────────────────────────────────────────────────
vix_price = (prices.get("VIX") or {}).get("price", 20)
dxy_5d    = (prices.get("DXY") or {}).get("chg5d", 0)
brent_p   = (prices.get("Brent") or {}).get("price", 80)
fg_score  = fg["score"] if fg else 50
cot_dxy   = cot_data.get("usd index",{})
cot_dxy_net = ((cot_dxy.get("spekulanter") or {}).get("net",0) or 0)
conflicts   = detect_conflict(vix_price, dxy_5d, fg, cot_dxy_net)

if conflicts:
    smile_pos,usd_bias,usd_color,smile_desc = "konflikt","UKLAR","warn","Motstridende signaler – reduser størrelse: " + " | ".join(conflicts[:2])
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
print(f"\nOK → {OUT}  ({len(levels)} instruments)")
if conflicts:
    print("Konflikter:"); [print(f"  ⚠️  {c}") for c in conflicts]
