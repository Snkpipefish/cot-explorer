#!/usr/bin/env python3
import urllib.request, urllib.parse, json, os, time, re
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, os.path.expanduser('~/cot-explorer'))
try:
    from smc import run_smc
    SMC_OK = True
except:
    SMC_OK = False
    print('  SMC ikke tilgjengelig')

# Driver-familie-matrise (fikser C1-korrelasjons-bias, schema 2.0)
import driver_matrix as dm
import driver_group_mapping as dgm

_DRIVER_SOURCES = dgm.load_all_sources(Path(os.path.expanduser("~/cot-explorer")))

BASE = os.path.expanduser("~/cot-explorer/data")
OUT  = os.path.join(BASE, "macro", "latest.json")
os.makedirs(os.path.join(BASE, "macro"), exist_ok=True)

# ── Signal-stabilitet: last forrige kjørings scores ─────────────
STABILITY_FILE = os.path.join(BASE, "macro", "signal_stability.json")
_prev_signals = {}
try:
    with open(STABILITY_FILE) as _f:
        _prev_signals = json.load(_f)
except Exception:
    pass

# ── Olje supply-disruption: les shipping + oilgas data ────────────
SHIPPING_FILE = os.path.join(BASE, "shipping", "latest.json")
OILGAS_FILE   = os.path.join(BASE, "oilgas", "latest.json")
_oil_supply_disruption = False
_oil_supply_reason = []
try:
    with open(SHIPPING_FILE) as _f:
        _shipping = json.load(_f)
    for route in _shipping.get("routes", []):
        rid = route.get("id", "")
        if rid in ("hormuz",) and route.get("risk") == "HIGH":
            _oil_supply_disruption = True
            _oil_supply_reason.append(f"Hormuz {route.get('risk')} (score {route.get('risk_score', '?')})")
        if rid in ("asia_europe",) and route.get("risk") == "HIGH":
            # Suez/Rødehavet — påvirker tanker-ruter
            _oil_supply_reason.append(f"Suez/Rødehavet {route.get('risk')}")
except Exception:
    pass
try:
    with open(OILGAS_FILE) as _f:
        _oilgas = json.load(_f)
    for seg in _oilgas.get("segments", []):
        if seg.get("id") == "mideast" and seg.get("risk") == "HIGH":
            _oil_supply_disruption = True
            if not any("Hormuz" in r for r in _oil_supply_reason):
                _oil_supply_reason.append(f"Midtøsten konflikt {seg.get('risk')}")
except Exception:
    pass
if _oil_supply_disruption:
    print(f"⛽ Olje supply-disruption aktiv: {', '.join(_oil_supply_reason)}")
    print(f"   → Blokkerer SHORT-signaler på Brent/WTI")

# Bot-priser som fallback når Yahoo/Stooq/Twelvedata feiler
BOT_HISTORY_FILE = os.path.join(BASE, "prices", "bot_history.json")
_bot_prices = {}
try:
    with open(BOT_HISTORY_FILE) as _f:
        _bh = json.load(_f)
    for _k, _v in _bh.items():
        if isinstance(_v, list) and _v:
            _bot_prices[_k] = _v[-1].get("price")
        elif isinstance(_v, dict):
            _bot_prices[_k] = _v.get("price")
except Exception:
    pass

INSTRUMENTS = [
    {"key":"DXY",   "navn":"DXY",    "symbol":"DX-Y.NYB","label":"Valuta", "kat":"valuta", "klasse":"A","session":"London 08:00–12:00 CET"},
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
    {"key":"USDCHF","navn":"USD/CHF","symbol":"CHF=X",   "label":"Valuta", "kat":"valuta", "klasse":"A","session":"London 08:00–12:00 CET","prices_only":True},
    {"key":"USDNOK","navn":"USD/NOK","symbol":"NOK=X",   "label":"Valuta", "kat":"valuta", "klasse":"A","session":"London 08:00–12:00 CET","prices_only":True},
]

TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "")
FINNHUB_API_KEY    = os.environ.get("FINNHUB_API_KEY", "")

# Kun symboler bekreftet tilgjengelig på Twelvedata gratis-plan
TD_FREE_SYMBOLS = {"EURUSD=X", "JPY=X", "GBPUSD=X", "AUDUSD=X", "GC=F",
                   "HYG", "TIP", "EEM"}

TWELVEDATA_MAP = {
    "EURUSD=X":  "EUR/USD",
    "JPY=X":     "USD/JPY",
    "GBPUSD=X":  "GBP/USD",
    "AUDUSD=X":  "AUD/USD",
    "GC=F":      "XAU/USD",
    "HYG":       "HYG",
    "TIP":       "TIP",
    "EEM":       "EEM",
}

TD_INTERVAL = {"1d": "1day", "15m": "15min", "60m": "1h"}
TD_SIZE     = {"1y": 365, "5d": 500, "60d": 500, "30d": 35}

from scoring_config import (
    SCORE_WEIGHTS, MAX_WEIGHTED_SCORE, GRADE_THRESHOLDS, SCORE_LABELS_NO,
    CORRELATION_GROUPS, MAX_CONCURRENT, DXY_MOMENTUM_THRESHOLD,
    determine_horizon, calculate_weighted_score, get_grade,
)

# Stooq-symboler (ingen API-nøkkel, nær sanntid i markedstid)
STOOQ_MAP = {
    "EURUSD=X":  "eurusd",
    "JPY=X":     "usdjpy",
    "GBPUSD=X":  "gbpusd",
    "AUDUSD=X":  "audusd",
    "GC=F":      "xauusd",
    "SI=F":      "xagusd",
    "BZ=F":      "co.f",       # Brent (ICE)
    "CL=F":      "cl.f",       # WTI
    "^GSPC":     "^spx",
    "^NDX":      "^ndx",
    "^VIX":      "^vix",
    "DX-Y.NYB":  "dxy.f",
    "HG=F":      "hg.f",       # Kobber
    "CHF=X":     "usdchf",     # USD/CHF
    "NOK=X":     "usdnok",     # USD/NOK
    "HYG":       "hyg.us",
    "TIP":       "tip.us",
    "EEM":       "eem.us",
}
STOOQ_DAYS  = {"1y": 400, "30d": 35, "5d": 7}

# Finnhub sanntidspriser for indekser og råvarer
FINNHUB_QUOTE_MAP = {
    "^GSPC":     "^GSPC",
    "^NDX":      "^NDX",
    "^VIX":      "^VIX",
    "SI=F":      "SI1!",
    "BZ=F":      "UKOIL",
    "CL=F":      "USOIL",
    "HG=F":      "HG1!",
}

# Nyhetssentiment: hvilken retning bekrefter risk_on / risk_off per instrument
# (risk_on_dir, risk_off_dir) — None = ikke bruk nyheter for dette instrumentet
NEWS_CONFIRMS_MAP = {
    "SPX":    ("bull", "bear"),   # aksjer stiger ved risk-on
    "NAS100": ("bull", "bear"),
    "Gold":   ("bear", "bull"),   # gull faller ved risk-on, stiger ved risk-off
    "Silver": ("bear", "bull"),
    "EURUSD": ("bull", "bear"),   # risk-on = svak USD = EUR/USD opp
    "GBPUSD": ("bull", "bear"),
    "AUDUSD": ("bull", "bear"),   # AUD er risikovaluta
    "USDJPY": ("bull", "bear"),   # risk-on = JPY svekkes = USD/JPY opp
    "DXY":    ("bear", "bull"),   # risk-on = svak USD
    "Brent":  (None,  None),      # olje: geopolitikk kompliserer retning
    "WTI":    (None,  None),
    "VIX":    ("bear", "bull"),
}

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

def fetch_twelvedata(symbol, interval="1d", outputsize=365):
    """Henter OHLC fra Twelvedata. Returnerer [(h,l,c), ...] eldst→nyest."""
    if not TWELVEDATA_API_KEY or symbol not in TD_FREE_SYMBOLS:
        return []
    td_sym = TWELVEDATA_MAP.get(symbol, symbol)
    td_int = TD_INTERVAL.get(interval, interval)
    url = (f"https://api.twelvedata.com/time_series"
           f"?symbol={urllib.parse.quote(td_sym)}"
           f"&interval={td_int}&outputsize={outputsize}"
           f"&apikey={TWELVEDATA_API_KEY}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read())
        if d.get("status") == "error":
            print(f"  TD {td_sym}: {d.get('message','ukjent feil')}")
            return []
        rows = []
        for v in reversed(d.get("values", [])):
            try:
                rows.append((float(v["high"]), float(v["low"]), float(v["close"])))
            except:
                continue
        time.sleep(8)  # Gratis-plan: maks 8 req/min
        return rows
    except Exception as e:
        print(f"  TD FEIL {td_sym} ({interval}): {e}")
        return []

def fetch_stooq(symbol, range_="1y"):
    """Henter daglig OHLC fra Stooq (ingen API-nøkkel, nær sanntid).
    Returnerer [(h,l,c), ...] eldst→nyest, eller [] ved feil.
    Siste element kan være dagens intradag-bar (Stooq oppdaterer live)."""
    from datetime import timedelta
    stooq_sym = STOOQ_MAP.get(symbol)
    if not stooq_sym:
        return []
    days = STOOQ_DAYS.get(range_, 400)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    d2 = datetime.now(timezone.utc).strftime("%Y%m%d")
    d1 = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    url = f"https://stooq.com/q/d/l/?s={stooq_sym}&i=d&d1={d1}&d2={d2}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            text = r.read().decode(errors="replace")
        lines = text.strip().split("\n")
        rows = []
        last_is_today = False
        for line in lines[1:]:   # hopp over header
            parts = line.strip().split(",")
            if len(parts) < 5:
                continue
            try:
                h, l, c = float(parts[2]), float(parts[3]), float(parts[4])
                if h and l and c:
                    rows.append((h, l, c))
                    last_is_today = (parts[0].strip() == today)
            except:
                continue
        # Fjern dagens intradag-bar — bruker 15m-data for dagens pris i stedet
        if last_is_today and len(rows) > 1:
            rows = rows[:-1]
        return rows
    except Exception as e:
        print(f"  Stooq FEIL {stooq_sym}: {e}")
        return []

def fetch_finnhub_quote(symbol):
    """Henter sanntidspris (h,l,c) fra Finnhub for indekser og råvarer."""
    if not FINNHUB_API_KEY:
        return None
    fh_sym = FINNHUB_QUOTE_MAP.get(symbol)
    if not fh_sym:
        return None
    url = f"https://finnhub.io/api/v1/quote?symbol={urllib.parse.quote(fh_sym)}&token={FINNHUB_API_KEY}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
        c, h, l = d.get("c", 0), d.get("h", 0), d.get("l", 0)
        if c and h and l:
            return (h, l, c)
        return None
    except Exception as e:
        print(f"  FH FEIL {fh_sym}: {e}")
        return None

def fetch_fred(series_id):
    """Henter siste daglige verdi fra FRED (Federal Reserve). Ingen API-nøkkel."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            lines = r.read().decode().strip().split("\n")
        for line in reversed(lines[1:]):
            parts = line.strip().split(",")
            if len(parts) == 2 and parts[1] not in (".", ""):
                return float(parts[1])
        return None
    except Exception as e:
        print(f"  FRED {series_id} FEIL: {e}")
        return None

def fetch_prices(symbol, interval, range_or_size):
    """Prioritet: Twelvedata (forex/gull) → Stooq (daglig) → Yahoo.
    Oppdaterer siste bar med Finnhub sanntidspris hvis tilgjengelig."""
    # Twelvedata: forex + gull på gratis-plan
    if TWELVEDATA_API_KEY and symbol in TD_FREE_SYMBOLS:
        rows = fetch_twelvedata(symbol, interval, TD_SIZE.get(range_or_size, 365))
        if rows:
            if interval == "1d":
                qt = fetch_finnhub_quote(symbol)
                if qt:
                    rows[-1] = qt
            return rows
    # Stooq: daglige data for alle symboler (ingen nøkkel)
    if interval == "1d":
        rows = fetch_stooq(symbol, range_or_size)
        if rows:
            qt = fetch_finnhub_quote(symbol)
            if qt:
                rows[-1] = qt
            return rows
    # Yahoo: fallback (intradag + alt Stooq ikke dekker)
    return fetch_yahoo(symbol, interval, range_or_size)

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

def get_adr_utilization(rows_15m, atr_d):
    """Prosentandel av daglig ATR brukt i dag (basert på 15min high/low)."""
    if not rows_15m or not atr_d or atr_d <= 0:
        return {"pct": None, "ok_for_scalp": True, "available": False}
    # rows = (high, low, close)  — bruk siste ~26 bars (ca 6.5 timer)
    today_bars = rows_15m[-26:]
    today_high = max(r[0] for r in today_bars)
    today_low  = min(r[1] for r in today_bars)
    used = today_high - today_low
    pct = round(used / atr_d * 100, 1)
    return {"pct": pct, "ok_for_scalp": pct < 70, "available": True}


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
    now_utc = datetime.now(timezone.utc)
    h = now_utc.hour
    m = now_utc.minute
    # UTC+2 (CEST) mars–oktober, UTC+1 (CET) resten av året
    year = now_utc.year
    _lsm = 31 - (datetime(year, 3, 31).weekday() + 1) % 7
    _lso = 31 - (datetime(year, 10, 31).weekday() + 1) % 7
    _dst_start = datetime(year, 3, _lsm, 1, tzinfo=timezone.utc)
    _dst_end   = datetime(year, 10, _lso, 1, tzinfo=timezone.utc)
    _tz_offset = 2 if _dst_start <= now_utc < _dst_end else 1
    cet = (h*60 + m + _tz_offset*60) % (24*60)
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
                    for k in ("zone_top", "zone_bottom"):
                        if k in lvl: m[k] = lvl[k]
                        else: m.pop(k, None)
                absorbed = True
                break
        if not absorbed:
            merged.append(dict(lvl))
    return sorted(merged, key=lambda x: abs(x["price"] - curr))[:max_n]


def make_setup_l2l(curr, atr_15m, atr_daily, sup_tagged, res_tagged, direction, klasse, min_rr=1.5, horizon="MAKRO", kat="valuta"):
    """
    Level-til-level setup — strukturbasert stop loss med horizon-differensierte mål.

    Geometri:
      LONG:  entry = støtte/demand-sone,  SL = under sone-bunn eller 0.3–0.5×ATR(D1) under nivå
      SHORT: entry = motstand/supply-sone, SL = over sone-topp  eller 0.3–0.5×ATR(D1) over nivå

    Regler:
      - SL plasseres ved STRUKTUREN, ikke mekanisk ATR fra nåpris
        · SMC demand/supply-sone: SL = zone_bottom/top + 0.15×ATR(D1) buffer
        · Linjnivå (PDH/PDL/D1/PWH/PWL): SL = nivå ± 0.3–0.5×ATR(D1)
      - Risk = faktisk avstand entry → SL (ikke fast ATR)
      - T1 må gi R:R >= min_rr basert på faktisk risk
      - Watchlist-filter: pris maks 1×ATR(D1) fra entry-nivå

    Horizon-differensiering av T1/T2:
      SCALP: T1 maks 2×ATR(D1), T2 maks 3×ATR(D1) fra entry — intradag mål
      SWING: T1 maks 5×ATR(D1), T2 maks 8×ATR(D1) fra entry — multi-dag mål
      MAKRO: Ingen cap — bruker fulle strukturelle nivåer
    """
    # Horizon-basert T1/T2 cap (i ATR(D1) fra entry) og min R:R
    HORIZON_T_CAPS = {
        "SCALP":     (2.0, 3.0),
        "SWING":     (5.0, 8.0),
        "MAKRO":     (None, None),   # Ingen cap
        "WATCHLIST": (2.0, 3.0),     # Som SCALP
    }
    HORIZON_MIN_RR = {
        "SCALP":     1.0,     # Tillat nærliggende reelle nivåer
        "SWING":     1.3,
        "MAKRO":     1.5,
        "WATCHLIST": 1.0,
    }
    t1_cap_atr, t2_cap_atr = HORIZON_T_CAPS.get(horizon, (5.0, 8.0))
    min_rr = HORIZON_MIN_RR.get(horizon, min_rr)
    if not atr_15m or atr_15m <= 0:
        return None
    if not atr_daily or atr_daily <= 0:
        atr_daily = atr_15m * 5

    def structural_sl(entry_level, entry_obj, dir):
        """
        SL basert utelukkende på reelle strukturnivåer — så tett som mulig.

        LONG:
          1. Entry sin SMC sone-bunn → SL = zone_bottom - buffer
          2. Nærmeste støtte under entry → SL = under det nivået (eller sone-bunn)
          3. Fallback: entry - 2×buffer

        SHORT: speilvendt.

        Buffer (under/over nivået) er kategori-tilpasset:
          valuta:  0.15×ATR(D1)
          ravarer: 0.25×ATR(D1)
          aksjer:  0.20×ATR(D1)
        """
        BUF_MULT = {"valuta": 0.15, "ravarer": 0.25, "aksjer": 0.20}
        buf = atr_daily * BUF_MULT.get(kat, 0.20)

        if dir == "long":
            # 1. Entry sin SMC sone-bunn
            zone_bot = entry_obj.get("zone_bottom")
            if zone_bot and zone_bot < entry_level:
                return round(zone_bot - buf, 5)

            # 2. Nærmeste reelle støtte under entry → SL under det
            for l in sup_tagged:
                if l is entry_obj:
                    continue
                if l["price"] < entry_level:
                    sl_at = l["price"]
                    nb = l.get("zone_bottom")
                    if nb and nb < sl_at:
                        sl_at = nb
                    return round(sl_at - buf, 5)

            # 3. Fallback: ingen nivåer under → tight buffer
            return round(entry_level - buf * 2, 5)
        else:
            # 1. Entry sin SMC sone-topp
            zone_top = entry_obj.get("zone_top")
            if zone_top and zone_top > entry_level:
                return round(zone_top + buf, 5)

            # 2. Nærmeste reelle motstand over entry → SL over det
            for l in res_tagged:
                if l is entry_obj:
                    continue
                if l["price"] > entry_level:
                    sl_at = l["price"]
                    nt = l.get("zone_top")
                    if nt and nt > sl_at:
                        sl_at = nt
                    return round(sl_at + buf, 5)

            # 3. Fallback
            return round(entry_level + buf * 2, 5)

    def best_t1(levels, entry, min_dist, max_dist=None, risk=None):
        """
        Beste T1: reelt nivå innenfor horizon-rekkevidde.

        Fix B — R:R-prioritert valg:
          1. Kandidater grupperes i R:R-tiers (krever risk-argument):
               tier 2 = R:R ≥ 2.0 (utmerket)
               tier 1 = R:R ≥ 1.5 (bra)
               tier 0 = R:R ≥ min_rr (akseptabelt)
          2. Innenfor samme tier: høyest weight først, deretter nærmest entry
          3. Hvis ingen innen horizon-cap: fallback til beste uansett avstand
             (kun ved ingen cap / MAKRO)

        Bevarer strukturell kvalitet (tung weight) men unngår "kort mål fordi
        tett nivå finnes" når et bedre R:R-tier er tilgjengelig.
        """
        is_long = direction == "long"
        # Filtrer: riktig side + minimum avstand
        valid = []
        for l in levels:
            p = l["price"]
            dist = (p - entry) if is_long else (entry - p)
            if dist >= min_dist:
                valid.append((l, dist))

        if not valid:
            return None

        def _rr_tier(dist: float) -> int:
            """Returnerer R:R-tier: 2 for ≥2.0, 1 for ≥1.5, 0 ellers."""
            if risk is None or risk <= 0:
                return 0
            rr = dist / risk
            if rr >= 2.0:
                return 2
            if rr >= 1.5:
                return 1
            return 0

        def _sort_key(item):
            # Sorterer: høyere tier først, så høyere weight, så kortere avstand
            l, d = item
            return (-_rr_tier(d), -l["weight"], d)

        # Del inn: innenfor og utenfor horizon-cap
        within = [(l, d) for l, d in valid if max_dist is None or d <= max_dist]
        beyond = [(l, d) for l, d in valid if max_dist is not None and d > max_dist]

        # Prioritet 1: beste reelle nivå innenfor horizon-rekkevidde
        if within:
            within.sort(key=_sort_key)
            l = within[0][0]
            q = "htf" if l["weight"] >= 3 else ("4h" if l["weight"] >= 2 else "weak")
            return dict(l, t1_quality=q)

        # Prioritet 2: hvis ingen cap (MAKRO), bruk beste uansett
        if max_dist is None and beyond:
            beyond.sort(key=_sort_key)
            l = beyond[0][0]
            q = "htf" if l["weight"] >= 3 else ("4h" if l["weight"] >= 2 else "weak")
            return dict(l, t1_quality=q)

        # Ingen reelt nivå innenfor rekkevidde
        return None

    # Horizon-basert entry-seleksjon og max avstand
    ENTRY_MAX_ATR = {"SCALP": 1.0, "SWING": 3.0, "MAKRO": 5.0, "WATCHLIST": 1.0}
    ENTRY_SEARCH_ATR = {"SCALP": 0, "SWING": 3.0, "MAKRO": 5.0, "WATCHLIST": 0}

    def _pick_entry(tagged):
        """SCALP: nærmeste (tagged[0]). SWING/MAKRO: sterkeste weight innen horizon-avstand."""
        search = ENTRY_SEARCH_ATR.get(horizon, 0)
        if search <= 0 or not atr_daily:
            return tagged[0]
        max_d = search * atr_daily
        within = [l for l in tagged if abs(l["price"] - curr) <= max_d]
        if not within:
            return tagged[0]
        # Sorter: høyest weight → nærmest pris
        within.sort(key=lambda l: (-l["weight"], abs(l["price"] - curr)))
        return within[0]

    if direction == "long":
        if not sup_tagged or not res_tagged:
            return None
        entry_obj   = _pick_entry(sup_tagged)
        entry_level = entry_obj["price"]
        entry_w     = entry_obj["weight"]

        entry_dist = curr - entry_level
        max_entry_dist = atr_daily * ENTRY_MAX_ATR.get(horizon, 1.0)
        if entry_dist < 0 or entry_dist > max_entry_dist:
            return None

        sl   = structural_sl(entry_level, entry_obj, "long")
        risk = entry_level - sl
        if risk <= 0:
            return None
        min_t1_dist = risk * min_rr

        max_t1_dist = t1_cap_atr * atr_daily if t1_cap_atr else None
        t1_obj = best_t1(res_tagged, entry_level, min_t1_dist, max_t1_dist, risk=risk)
        if t1_obj is None:
            return None  # Ingen reelt T1-nivå → ingen setup

        t1 = t1_obj["price"]

        # T2: neste reelle nivå etter T1 (innenfor cap)
        max_t2_dist = t2_cap_atr * atr_daily if t2_cap_atr else None
        res_after = [l for l in res_tagged if l["price"] > t1]
        if max_t2_dist:
            res_after = [l for l in res_after
                         if (l["price"] - entry_level) <= max_t2_dist]
        t2 = res_after[0]["price"] if res_after else t1  # Ingen T2 = T1

        rr1 = round((t1 - entry_level) / risk, 2)
        rr2 = round((t2 - entry_level) / risk, 2) if t2 != t1 else rr1

        at_level = is_at_level(curr, entry_level, atr_15m, entry_w)
        sl_src   = "zone" if entry_obj.get("zone_bottom") else "struktur"
        q        = t1_obj["t1_quality"]
        return {
            "entry":          round(entry_level, 5),
            "entry_curr":     round(curr, 5),
            "sl":             sl,
            "sl_type":        sl_src,
            "t1":             round(t1, 5),
            "t2":             round(t2, 5),
            "rr_t1": rr1,    "rr_t2": rr2,   "min_rr": min_rr,
            "risk_atr_d":     round(risk / atr_daily, 2),
            "entry_dist_atr": round(entry_dist / atr_daily, 2),
            "entry_name":     f"Støtte {round(entry_level,5)} [{entry_obj['source']}]",
            "entry_level":    round(entry_level, 5),
            "entry_weight":   entry_w,
            "t1_source":      t1_obj["source"],
            "t1_weight":      t1_obj["weight"],
            "t1_quality":     q,
            "status":         "aktiv" if at_level else "watchlist",
            "note": (f"MAKRO LONG: E={round(entry_level,4)} [{entry_obj['source']} w{entry_w}]"
                     f" SL={round(sl,4)} ({sl_src}) → T1={round(t1,4)}"
                     f" [{t1_obj['source']} w{t1_obj['weight']} {q}]"
                     f" R:R={rr1} | Risk={round(risk,4)} ({round(risk/atr_daily,2)}×ATRd)"),
            "timeframe": "D1/4H",
        }
    else:
        if not res_tagged or not sup_tagged:
            return None
        entry_obj   = _pick_entry(res_tagged)
        entry_level = entry_obj["price"]
        entry_w     = entry_obj["weight"]

        entry_dist = entry_level - curr
        max_entry_dist = atr_daily * ENTRY_MAX_ATR.get(horizon, 1.0)
        if entry_dist < 0 or entry_dist > max_entry_dist:
            return None

        sl   = structural_sl(entry_level, entry_obj, "short")
        risk = sl - entry_level
        if risk <= 0:
            return None
        min_t1_dist = risk * min_rr

        max_t1_dist = t1_cap_atr * atr_daily if t1_cap_atr else None
        t1_obj = best_t1(sup_tagged, entry_level, min_t1_dist, max_t1_dist, risk=risk)
        if t1_obj is None:
            return None  # Ingen reelt T1-nivå → ingen setup

        t1 = t1_obj["price"]

        # T2: neste reelle nivå etter T1 (innenfor cap)
        max_t2_dist = t2_cap_atr * atr_daily if t2_cap_atr else None
        sup_after = [l for l in sup_tagged if l["price"] < t1]
        if max_t2_dist:
            sup_after = [l for l in sup_after
                         if (entry_level - l["price"]) <= max_t2_dist]
        t2 = sup_after[0]["price"] if sup_after else t1  # Ingen T2 = T1

        rr1 = round((entry_level - t1) / risk, 2)
        rr2 = round((entry_level - t2) / risk, 2) if t2 != t1 else rr1

        at_level = is_at_level(curr, entry_level, atr_15m, entry_w)
        sl_src   = "zone" if entry_obj.get("zone_top") else "struktur"
        q        = t1_obj["t1_quality"]
        return {
            "entry":          round(entry_level, 5),
            "entry_curr":     round(curr, 5),
            "sl":             sl,
            "sl_type":        sl_src,
            "t1":             round(t1, 5),
            "t2":             round(t2, 5),
            "rr_t1": rr1,    "rr_t2": rr2,   "min_rr": min_rr,
            "risk_atr_d":     round(risk / atr_daily, 2),
            "entry_dist_atr": round(entry_dist / atr_daily, 2),
            "entry_name":     f"Motstand {round(entry_level,5)} [{entry_obj['source']}]",
            "entry_level":    round(entry_level, 5),
            "entry_weight":   entry_w,
            "t1_source":      t1_obj["source"],
            "t1_weight":      t1_obj["weight"],
            "t1_quality":     q,
            "status":         "aktiv" if at_level else "watchlist",
            "note": (f"MAKRO SHORT: E={round(entry_level,4)} [{entry_obj['source']} w{entry_w}]"
                     f" SL={round(sl,4)} ({sl_src}) → T1={round(t1,4)}"
                     f" [{t1_obj['source']} w{t1_obj['weight']} {q}]"
                     f" R:R={rr1} | Risk={round(risk,4)} ({round(risk/atr_daily,2)}×ATRd)"),
            "timeframe": "D1/4H",
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

def fetch_news_sentiment():
    """Henter RSS-nyheter (Google News + BBC), scorer risk-on/risk-off nøkkelord.
    Returnerer dict med score (-1..1), label, top_headlines og key_drivers.
    """
    RISK_ON = [
        "peace", "ceasefire", "deal", "agreement", "truce", "treaty",
        "stimulus", "rate cut", "rate cuts", "recovery", "trade deal",
        "tariff pause", "tariff reduction", "tariff removed", "de-escalation",
        "deescalation", "accord", "optimism", "soft landing", "talks progress",
        "diplomatic", "breakthrough", "resolved", "lifted sanctions",
    ]
    RISK_OFF = [
        "war", "attack", "invasion", "escalation", "sanctions", "default",
        "crisis", "collapse", "recession", "military strike", "nuclear",
        "terror", "conflict", "threatens", "tariff hike", "new tariffs",
        "imposed tariffs", "sell-off", "selloff", "bank run", "debt crisis",
        "banking crisis", "crash", "downgrade", "emergency", "missile",
    ]
    feeds = [
        "https://news.google.com/rss/search?q=economy+markets+geopolitics&hl=en-US&gl=US&ceid=US:en",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
    ]
    headlines = []
    for url in feeds:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=7) as r:
                txt = r.read().decode("utf-8", errors="replace")
            titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", txt)
            if not titles:
                titles = re.findall(r"<title>(.*?)</title>", txt)
            headlines.extend(titles[1:16])
        except Exception as e:
            print(f"  Nyheter FEIL ({url[:45]}): {e}")
    if not headlines:
        return None
    ro_count = roff_count = 0
    drivers = []
    for h in headlines:
        hl = h.lower()
        ro   = sum(1 for w in RISK_ON  if w in hl)
        roff = sum(1 for w in RISK_OFF if w in hl)
        if ro > roff:
            ro_count += 1
            drivers.append({"headline": h[:90], "type": "risk_on"})
        elif roff > ro:
            roff_count += 1
            drivers.append({"headline": h[:90], "type": "risk_off"})
    total = ro_count + roff_count
    if total == 0:
        label, net = "neutral", 0.0
    else:
        net   = round((ro_count - roff_count) / total, 2)
        label = "risk_on" if net >= 0.3 else "risk_off" if net <= -0.3 else "neutral"
    print(f"  Nyhetssentiment: {label} (score={net:+.2f}, ro={ro_count}, roff={roff_count}, n={len(headlines)})")
    return {
        "score":          net,
        "label":          label,
        "top_headlines":  headlines[:5],
        "key_drivers":    drivers[:6],
        "ro_count":       ro_count,
        "roff_count":     roff_count,
        "headlines_n":    len(headlines),
    }

MACRO_SYMBOLS = {
    "HYG":    "HYG",       # iShares High Yield Corp Bond ETF — kredittrisiko
    "TIP":    "TIP",       # iShares TIPS Bond ETF — inflasjonsdrevne realrenter
    "TNX":    "^TNX",      # 10-årig statsrente (USA)
    "IRX":    "^IRX",      # 3-måneds statskasseveksel
    "Copper": "HG=F",      # Kobber-futures — ledende vekstindikator
    "EEM":    "EEM",       # iShares MSCI Emerging Markets ETF — risikoappetitt
}

def fetch_macro_indicators():
    """Henter tilleggsindikatorer for makrobilde. Returnerer dict nøkkel→{price, chg5d}.
    Bruker FRED for renter (offisielle Fed-data), Twelvedata/Yahoo for ETF og råvarer.
    """
    out = {}

    # Renter fra FRED (DGS10 = 10Y, DTB3 = 3-måneds T-bill)
    print("  FRED: henter renter...")
    for key, series in [("TNX", "DGS10"), ("IRX", "DTB3")]:
        val = fetch_fred(series)
        if val:
            out[key] = {"price": round(val, 3), "chg1d": 0, "chg5d": 0}
            print(f"    {key} ({series}): {val:.3f}%")
        else:
            # Fallback til Yahoo
            daily = fetch_yahoo(MACRO_SYMBOLS[key], "1d", "30d")
            if daily and len(daily) >= 2:
                curr = daily[-1][2]
                c5   = daily[-6][2] if len(daily) >= 6 else curr
                out[key] = {"price": round(curr, 3), "chg1d": 0,
                            "chg5d": round((curr/c5-1)*100, 2)}
            else:
                out[key] = None

    # ETF og råvarer via Twelvedata (fallback Yahoo)
    for key in ["HYG", "TIP", "Copper", "EEM"]:
        sym = MACRO_SYMBOLS[key]
        daily = fetch_prices(sym, "1d", "1y")
        if not daily or len(daily) < 6:
            out[key] = None
            continue
        curr = daily[-1][2]
        c1   = daily[-2][2]  if len(daily) >= 2  else curr
        c5   = daily[-6][2]  if len(daily) >= 6  else curr
        c20  = daily[-21][2] if len(daily) >= 21 else curr
        out[key] = {
            "price":  round(curr, 4 if curr < 10 else 2),
            "chg1d":  round((curr / c1  - 1) * 100, 2),
            "chg5d":  round((curr / c5  - 1) * 100, 2),
            "chg20d": round((curr / c20 - 1) * 100, 2),
        }
    return out

def detect_conflict(vix, dxy_5d, fg, cot_usd, hy_stress=False, yield_curve=None, news_sent=None):
    conflicts = []
    if vix > 25 and dxy_5d < 0:
        conflicts.append("VIX>25 men DXY faller – risk-off uten USD-etterspørsel")
    if fg and fg["score"] < 30 and dxy_5d < 0:
        conflicts.append("Ekstrem frykt men USD svekkes – unormalt")
    if fg and fg["score"] > 70 and vix > 22:
        conflicts.append("Grådighet men VIX forhøyet – divergens")
    if cot_usd and cot_usd > 0 and dxy_5d < -1:
        conflicts.append("COT long USD men pris faller – divergens")
    if hy_stress and vix < 20:
        conflicts.append("HY-spreader øker men VIX lav – skjult kredittrisiko")
    if yield_curve is not None and yield_curve < -0.3:
        conflicts.append(f"Rentekurve invertert ({yield_curve:+.2f}%) – resesjonsrisiko")
    # Nyhetssentiment vs makro
    if news_sent and news_sent.get("label") == "risk_on" and vix > 25:
        conflicts.append("Nyheter risk-on men VIX forhøyet – sentimentskifte pågår")
    if news_sent and news_sent.get("label") == "risk_off" and fg and fg["score"] > 60:
        conflicts.append("Nyheter risk-off men Fear&Greed viser grådighet – divergens")
    if news_sent and news_sent.get("label") == "risk_on" and fg and fg["score"] < 25:
        conflicts.append("Nyheter risk-on men ekstrem frykt i markedet – potensiell bunnstemning")
    return conflicts

# ── Last fundamentals ────────────────────────────────────────
fund_data = {}
fund_file = os.path.join(BASE, "fundamentals", "latest.json")
if os.path.exists(fund_file):
    try:
        with open(fund_file) as f:
            fund_data = json.load(f)
        n = len(fund_data.get("indicators", {}))
        print(f"Fundamentals: {n} indikatorer lastet ({fund_data.get('usd_fundamental',{}).get('bias','?')} USD)")
    except Exception:
        pass

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

SPEECH_KEYWORDS = ('speak', 'speech', 'press conf', 'testim', 'statement', 'minutes', 'outlook', 'remarks')

def get_binary_risk(instrument_key, hours=4):
    now = datetime.now(timezone.utc)
    risks = []
    for ev in calendar_events:
        if ev.get('impact') != 'High': continue
        # Beregn hours_away dynamisk fra event-dato (ikke statisk verdi fra fil)
        date_str = ev.get('date', '')
        if date_str:
            try:
                ev_dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                ha = (ev_dt - now).total_seconds() / 3600.0
            except Exception:
                ha = ev.get('hours_away', 99)
        else:
            ha = ev.get('hours_away', 99)
        if ha > hours: continue  # for langt frem i tid
        # Etter hendelsen: hold risiko aktiv i 60 min for taler/pressekonf, 30 min for resten
        title_low = ev.get('title', '').lower()
        is_speech = any(w in title_low for w in SPEECH_KEYWORDS)
        expiry = -1.0 if is_speech else -0.5
        if ha < expiry: continue  # hendelsen er utløpt
        berorte = ev.get('berorte', [])
        if instrument_key in berorte or not berorte:
            risks.append({
                'title':     ev['title'],
                'cet':       ev['cet'],
                'country':   ev['country'],
                'date':      date_str,   # UTC ISO — for sanntidssjekk i nettleser
                'is_speech': is_speech,
                'past':      ha < 0,
            })
    return risks

# ── Last COT (CFTC) ───────────────────────────────────────
cot_data = {}
cot_file = os.path.join(BASE, "combined", "latest.json")
if os.path.exists(cot_file):
    with open(cot_file) as f:
        for d in json.load(f):
            cot_data[d["market"].lower()] = d

# ── Last ICE COT (primær for Brent/Gasoil/TTF) ────────────
ice_cot_data = {}
ice_cot_file = os.path.join(BASE, "ice_cot", "latest.json")
if os.path.exists(ice_cot_file):
    try:
        with open(ice_cot_file) as f:
            ice_json = json.load(f)
        for d in ice_json.get("markets", []):
            ice_cot_data[d["market"].lower()] = d
        print(f"  ICE COT lastet: {len(ice_cot_data)} markeder")
    except Exception as e:
        print(f"  ICE COT FEIL ved lasting: {e}")

# Instrumenter som bruker ICE COT som primær kilde
# (ICE er hjemmebørsen for disse — mer representativt enn CFTC)
ICE_COT_MAP = {
    "Brent": "ice brent crude",
}

# ── Fear & Greed ──────────────────────────────────────────
print("Henter Fear & Greed...")
fg = fetch_fear_greed()
if fg: print(f"  → {fg['score']} ({fg['rating']})")

# ── Nyhetssentiment ────────────────────────────────────────
print("Henter nyhetssentiment...")
news_sentiment = fetch_news_sentiment()

# ── Hent VIX termstruktur (trengs i scoring-loop) ────────────
print("Henter VIX term-struktur (^VIX9D, ^VIX3M)...")
_vix9d_rows = fetch_yahoo("^VIX9D", "1d", "5d")
_vix3m_rows = fetch_yahoo("^VIX3M", "1d", "5d")
_vix9d = round(_vix9d_rows[-1][2], 2) if _vix9d_rows else None
_vix3m = round(_vix3m_rows[-1][2], 2) if _vix3m_rows else None
vix_term_structure = None  # Beregnes etter VIX-pris er tilgjengelig

# ── Priser og setups ──────────────────────────────────────
prices, levels = {}, {}
CORR_KEYS = ["EURUSD", "Gold", "NAS100", "Brent"]
daily_closes_for_corr = {}   # key → list of closes (last 22 days)
daily_adr_cache = {}         # key → list of (h-l) for last 20 days
dxy_dir_color = None          # Settes av DXY-iterasjonen, brukes av USD-par
dxy_momentum_strength = 1.0   # Graduert DXY-penalty: 0.25–1.0 basert på |chg5d|

# USD-par der "bull" = sterkere USD. Invers = XXXUSD-par der "bull" = svakere USD
USD_QUOTE_PAIRS = {"USDJPY", "USDCHF", "USDCAD", "USDNOK"}  # bull = USD styrke
USD_BASE_PAIRS  = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"}   # bull = USD svakhet

# H8: DXY må iterere først for at dxy_dir_color / dxy_momentum_strength skal
# være satt når USD-parene treffer dxy_conflict-sjekken (fetch_all.py:1393).
# Hvis noen reorganiserer INSTRUMENTS og flytter DXY, vil alle USD-par
# stille og silent miste DXY-konflikt-penalty. Fang det her.
assert INSTRUMENTS and INSTRUMENTS[0]["key"] == "DXY", (
    "INSTRUMENTS må starte med DXY — dxy_conflict-beregningen i loopen "
    "er avhengig av at DXY-direction er satt før USD-parene iterer."
)


def _compute_gs_ratio_z(window: int = 20):
    """Rolling z-score av Gold/Silver-ratio fra bot-history.

    Brukes i metals fundamental-scoring (driver_matrix.compute_fundamental_metals):
      Z > +2  → Gold dyr vs Silver → bear Gold / bull Silver
      Z < -2  → Gold billig vs Silver → bull Gold / bear Silver
    Returnerer None hvis for lite data eller std=0 (konstante priser).
    """
    try:
        hist_path = os.path.expanduser("~/cot-explorer/data/prices/bot_history.json")
        if not os.path.exists(hist_path):
            return None
        with open(hist_path) as f:
            hist = json.load(f)
        gold   = [e["price"] for e in hist.get("Gold",   []) if e.get("price")]
        silver = [e["price"] for e in hist.get("Silver", []) if e.get("price")]
        if len(gold) < 5 or len(silver) < 5:
            return None
        n = min(len(gold), len(silver), window)
        ratios = [g / s for g, s in zip(gold[-n:], silver[-n:]) if s]
        if len(ratios) < 5:
            return None
        mean = sum(ratios) / len(ratios)
        var  = sum((r - mean) ** 2 for r in ratios) / len(ratios)
        std  = var ** 0.5
        if std <= 0:
            return None
        return round((ratios[-1] - mean) / std, 2)
    except Exception as e:
        print(f"  GS-ratio-z FEIL: {e}")
        return None


# Beregn én gang før scoring-loopen (samme verdi for Gold og Silver)
_gs_ratio_z = _compute_gs_ratio_z()
if _gs_ratio_z is not None:
    print(f"  Gold/Silver ratio z-score (20d): {_gs_ratio_z:+.2f}")

for inst in INSTRUMENTS:
    print(f"Henter {inst['navn']}...")

    daily    = fetch_prices(inst["symbol"], "1d",  "1y")
    rows_15m = fetch_prices(inst["symbol"], "15m", "5d")
    rows_1h  = fetch_prices(inst["symbol"], "60m", "60d")
    h4       = to_4h(rows_1h) if rows_1h else []

    if not daily or len(daily) < 15:
        # Fallback: bruk bot-pris hvis tilgjengelig (hindrer at instrumentet droppes)
        bp = _bot_prices.get(inst["key"])
        if bp and daily:
            # Har noen rader men < 15 — fyll opp med siste kjente pris
            while len(daily) < 15:
                daily.insert(0, (bp, bp, bp))
            print(f"  ⚠ {inst['key']}: kun {len(daily)} daglige rader, utfylt med bot-pris {bp}")
        elif bp and not daily:
            # Ingen data i det hele tatt — bygg minimal serie fra bot-pris
            daily = [(bp, bp, bp)] * 220
            print(f"  ⚠ {inst['key']}: alle priskilder feilet, bruker bot-pris {bp}")
        else:
            print(f"  ✗ {inst['key']}: ingen prisdata og ingen bot-pris — hopper over")
            continue

    # Accumulate closes for correlation matrix and ADR
    if inst["key"] in CORR_KEYS:
        daily_closes_for_corr[inst["key"]] = [r[2] for r in daily[-22:]]
    if not inst.get("prices_only") and inst["key"] != "VIX":
        daily_adr_cache[inst["key"]] = [r[0] - r[1] for r in daily[-20:] if r[0] and r[1]]

    curr     = daily[-1][2]
    # Bruk siste 15m close hvis tilgjengelig (mer oppdatert)
    # Stooq's daglige data har nå TODAY's bar fjernet (se fetch_stooq).
    # daily[-1] = gårsdagens close alltid. 15m gir dagens live-pris.
    if rows_15m and len(rows_15m) > 0:
        curr = rows_15m[-1][2]
    c1  = daily[-2][2] if len(daily)>=2  else curr
    c5  = daily[-6][2] if len(daily)>=6  else curr
    c20 = daily[-21][2] if len(daily)>=21 else curr

    atr_d    = calc_atr(daily, 14)
    atr_15m  = calc_atr(rows_15m, 14) if len(rows_15m) >= 15 else None
    atr_4h   = calc_atr(h4, 14) if len(h4) >= 15 else None
    sma200   = sum(r[2] for r in daily[-200:]) / min(200, len(daily))
    prices[inst["key"]] = {
        "price":  round(curr, 4 if curr<100 else 2),
        "chg1d":  round((curr/c1-1)*100,  2),
        "chg5d":  round((curr/c5-1)*100,  2),
        "chg20d": round((curr/c20-1)*100, 2),
    }

    if inst["key"] == "VIX":
        # Beregn termstruktur nå som VIX-pris er tilgjengelig
        _vix_spot = prices["VIX"]["price"]
        if _vix_spot and _vix9d and _vix3m:
            s9  = round((_vix9d / _vix_spot - 1) * 100, 1)
            s3m = round((_vix3m / _vix_spot - 1) * 100, 1)
            regime = ("backwardation" if _vix9d < _vix_spot * 0.98 else
                      "flat" if abs(s9) < 2 else "contango")
            vix_term_structure = {
                "spot": _vix_spot, "vix9d": _vix9d, "vix3m": _vix3m,
                "spot_to_9d_pct": s9, "spot_to_3m_pct": s3m, "regime": regime,
            }
            print(f"  VIX9D={_vix9d:.2f}  VIX3M={_vix3m:.2f}  regime={regime}")
        continue
    if inst.get("prices_only"): continue

    # ── SMC analyse (15m, 1H, 4H) ────────────────────────
    smc = None
    smc_1h = None
    smc_4h = None
    if SMC_OK and rows_15m and len(rows_15m) > 50:
        try:
            smc = run_smc(rows_15m, swing_length=5)
        except Exception as e:
            print(f"  SMC 15m FEIL: {e}")
    if SMC_OK and rows_1h and len(rows_1h) > 50:
        try:
            smc_1h = run_smc(rows_1h, swing_length=10)
        except Exception as e:
            print(f"  SMC 1H FEIL: {e}")
    if SMC_OK and h4 and len(h4) > 30:
        try:
            smc_4h = run_smc(h4, swing_length=5)
        except Exception as e:
            print(f"  SMC 4H FEIL: {e}")

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

    # SMC 1H supply/demand-soner (weight 3 — institusjonell struktur, dager)
    if smc_1h:
        for z in smc_1h.get("supply_zones", []):
            if z["poi"] > curr:
                raw_res.append({"price": z["poi"], "source": "SMC1H", "weight": 3,
                                "zone_top": z["top"], "zone_bottom": z["bottom"]})
        for z in smc_1h.get("demand_zones", []):
            if z["poi"] < curr:
                raw_sup.append({"price": z["poi"], "source": "SMC1H", "weight": 3,
                                "zone_top": z["top"], "zone_bottom": z["bottom"]})

    # SMC 4H supply/demand-soner (weight 2 — intradag struktur, timer)
    if smc_4h:
        for z in smc_4h.get("supply_zones", []):
            if z["poi"] > curr:
                raw_res.append({"price": z["poi"], "source": "SMC4H", "weight": 2,
                                "zone_top": z["top"], "zone_bottom": z["bottom"]})
        for z in smc_4h.get("demand_zones", []):
            if z["poi"] < curr:
                raw_sup.append({"price": z["poi"], "source": "SMC4H", "weight": 2,
                                "zone_top": z["top"], "zone_bottom": z["bottom"]})

    # SMC 15m supply/demand-soner (weight 1 — lokal struktur, timer)
    if smc:
        for z in smc.get("supply_zones", []):
            if z["poi"] > curr:
                raw_res.append({"price": z["poi"], "source": "SMC15m", "weight": 1,
                                "zone_top": z["top"], "zone_bottom": z["bottom"]})
        for z in smc.get("demand_zones", []):
            if z["poi"] < curr:
                raw_sup.append({"price": z["poi"], "source": "SMC15m", "weight": 1,
                                "zone_top": z["top"], "zone_bottom": z["bottom"]})

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
    closes_4h = [r[2] for r in h4] if h4 else []
    ema9_d    = calc_ema(closes_d,  9)
    ema9_15m  = calc_ema(closes_15, 9) if closes_15 else None
    ema9_4h   = calc_ema(closes_4h, 9) if len(closes_4h) >= 10 else None

    d1_bull  = curr > ema9_d   if ema9_d  else None
    h4_bull  = curr > ema9_4h  if ema9_4h else None
    m15_bull = curr > ema9_15m if ema9_15m else None
    d1_regime  = ("BULLISH" if d1_bull  else "BEARISH") if d1_bull  is not None else "NØYTRAL"
    m15_regime = ("BULLISH" if m15_bull else "BEARISH") if m15_bull is not None else "NØYTRAL"

    # D1+4H kongruens (ekte 4H, ikke 15m) — mer stabil mellom kjøringer
    if d1_bull is not None and h4_bull is not None:
        if d1_bull and h4_bull:         align = "bull"
        elif not d1_bull and not h4_bull: align = "bear"
        else:                           align = "mixed"
    elif d1_bull is not None and m15_bull is not None:
        # Fallback til 15m hvis 4H mangler
        if d1_bull and m15_bull:         align = "bull"
        elif not d1_bull and not m15_bull: align = "bear"
        else:                           align = "mixed"
    else:
        align = "mixed"

    session_now = get_session_status()

    # ── COT ───────────────────────────────────────────────
    # For Brent: kombiner ICE + CFTC med OI-vekting (samme logikk som
    # Euronext+CFTC for landbruk). ICE er hjemmebørsen, CFTC dekker
    # amerikanske WTI-relaterte Brent-kontrakter — begge er reelle signaler.
    ice_key    = ICE_COT_MAP.get(inst["key"], "")
    ice_entry  = ice_cot_data.get(ice_key, {}) if ice_key else {}
    cot_key    = COT_MAP.get(inst["key"], "")
    cftc_entry = cot_data.get(cot_key, {})

    def _fresh(entry):
        """Returner True hvis COT-data er nyere enn 14 dager."""
        d = entry.get("date", "")
        if not d:
            return False
        try:
            age = (datetime.now(timezone.utc).date() -
                   datetime.strptime(d, "%Y-%m-%d").date()).days
            return age <= 14
        except Exception:
            return bool(d)

    has_ice  = bool(ice_entry) and _fresh(ice_entry)
    has_cftc = bool(cftc_entry)

    if has_ice and has_cftc:
        # OI-vektet kombinasjon
        ice_net  = (ice_entry.get("spekulanter") or {}).get("net", 0) or 0
        ice_oi   = ice_entry.get("open_interest", 1) or 1
        ice_chg  = ice_entry.get("change_spec_net", 0) or 0
        cftc_net = (cftc_entry.get("spekulanter") or {}).get("net", 0) or 0
        cftc_oi  = cftc_entry.get("open_interest", 1) or 1
        cftc_chg = cftc_entry.get("change_spec_net", 0) or 0
        total_oi = ice_oi + cftc_oi
        cot_pct  = ((ice_net / ice_oi * ice_oi) + (cftc_net / cftc_oi * cftc_oi)) / total_oi * 100
        spec_net = ice_net + cftc_net
        oi       = total_oi
        _cot_chg = ice_chg + cftc_chg
        cot_source = "ICE+CFTC"
        cot_agrees = (ice_net > 0) == (cftc_net > 0)
    elif has_ice:
        sp       = ice_entry.get("spekulanter") or {}
        spec_net = sp.get("net", 0) or 0
        oi       = ice_entry.get("open_interest", 1) or 1
        cot_pct  = spec_net / oi * 100
        _cot_chg = ice_entry.get("change_spec_net", 0) or 0
        cot_source = "ICE"
        cot_agrees = None
    else:
        sp       = cftc_entry.get("spekulanter") or {}
        spec_net = sp.get("net", 0) or 0
        oi       = cftc_entry.get("open_interest", 1) or 1
        cot_pct  = spec_net / oi * 100
        _cot_chg = cftc_entry.get("change_spec_net", 0) or 0
        cot_source = "CFTC"
        cot_agrees = None

    cot_bias  = "LONG" if cot_pct>4 else "SHORT" if cot_pct<-4 else "NØYTRAL"
    cot_color = "bull"  if cot_pct>4 else "bear"  if cot_pct<-4 else "neutral"

    # Hvis kildene er uenige: svakere momentum-signal
    if _cot_chg == 0:
        cot_momentum = "STABIL"
    elif (_cot_chg > 0 and spec_net >= 0) or (_cot_chg < 0 and spec_net <= 0):
        cot_momentum = "ØKER"
    else:
        cot_momentum = "SNUR"
    if cot_agrees is False:
        cot_momentum = "BLANDET"

    # ── Score ─────────────────────────────────────────────
    above_sma = curr > sma200
    chg5      = prices[inst["key"]]["chg5d"]
    chg20     = prices[inst["key"]]["chg20d"]
    fg_score  = fg["score"] if fg else 50

    # Pris ved nivå — kun for display, ikke brukt i horizon/score
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
    # Bruk høyeste weight blant nivåer innenfor 2×ATR — ikke bare det fysisk nærmeste
    nearest_sup_w = max((l["weight"] for l in tagged_sup if l.get("dist_atr", 99) <= 2.0), default=0) \
                    if tagged_sup else 0
    nearest_res_w = max((l["weight"] for l in tagged_res if l.get("dist_atr", 99) <= 2.0), default=0) \
                    if tagged_res else 0
    if nearest_sup_w == 0 and tagged_sup:
        nearest_sup_w = tagged_sup[0]["weight"]
    if nearest_res_w == 0 and tagged_res:
        nearest_res_w = tagged_res[0]["weight"]
    htf_level_nearby = max(nearest_sup_w, nearest_res_w) >= 3

    # Sesjon aktiv nå
    sesjon_aktiv = session_now["active"]
    klasse = inst["klasse"]
    sesjon_riktig = (
        (klasse == "A" and "London" in session_now["label"]) or
        (klasse == "B" and ("London" in session_now["label"] or "NY" in session_now["label"])) or
        (klasse == "C" and "NY" in session_now["label"])
    )

    # ── Sammensatt retningsbestemmelse ──────────────────────
    # Flere signaler stemmer → sterkere overbevisning
    dir_score = 0.0
    # SMA200: tung faktor — definerer lang trend
    dir_score += 1.5 if above_sma else -1.5
    # 5d momentum: kort sikt, men kun sterk hvis > 0.3% for å unngå flip rundt 0
    if abs(chg5) > 0.3:
        dir_score += 1.0 if chg5 > 0 else -1.0
    elif abs(chg5) > 0.1:
        dir_score += 0.5 if chg5 > 0 else -0.5
    # 20d momentum: mellomlangt
    if abs(chg20) > 1.0:
        dir_score += 1.0 if chg20 > 0 else -1.0
    elif abs(chg20) > 0.3:
        dir_score += 0.5 if chg20 > 0 else -0.5
    # COT: store aktørers posisjonering
    if cot_bias == "LONG":
        dir_score += 1.0
    elif cot_bias == "SHORT":
        dir_score -= 1.0
    # COT momentum: ukentlig endring forsterker
    if abs(_cot_chg) > 0:
        dir_score += 0.5 if _cot_chg > 0 else -0.5
    # Momentum-divergens: kort og mellomlang sikt peker motsatt → usikker retning
    if chg5 > 0.3 and chg20 < -0.3:
        dir_score -= 0.5
    elif chg5 < -0.3 and chg20 > 0.3:
        dir_score -= 0.5

    # DXY-bias for USD-par (før dxy_conflict-penalty)
    key = inst["key"]
    if dxy_dir_color and key != "DXY":
        if key in USD_QUOTE_PAIRS:
            # USDJPY: sterk USD = bull → følg DXY
            dir_score += 0.5 if dxy_dir_color == "bull" else -0.5
        elif key in USD_BASE_PAIRS:
            # EURUSD: sterk USD = bear → invers DXY
            dir_score += -0.5 if dxy_dir_color == "bull" else 0.5

    # Hysterese: krever dir_score > 0.5 for bull, < -0.5 for bear
    # Mellom -0.5 og 0.5: fall tilbake til SMA200
    if dir_score > 0.5:
        dir_color = "bull"
    elif dir_score < -0.5:
        dir_color = "bear"
    else:
        dir_color = "bull" if above_sma else "bear"

    # ── Olje supply-disruption override ─────────────────────
    # Når Hormuz/Midtøsten har HIGH risk → olje kan ikke shortes
    # Supply-squeeze = bullish for pris, SHORT er for farlig
    if _oil_supply_disruption and key in ("Brent", "WTI"):
        if dir_color == "bear":
            dir_color = "bull"  # Tving bullish — supply-disruption trumfer teknisk
            dir_score = 0.6     # Mild bull, ikke sterk — la scoren reflektere usikkerhet

    # Lagre DXY-retning og momentum for bruk i USD-par
    if key == "DXY":
        dxy_dir_color = dir_color
        dxy_chg5d_abs = abs(chg5) if chg5 else 0
        dxy_momentum_strength = min(max(dxy_chg5d_abs / DXY_MOMENTUM_THRESHOLD, 0.25), 1.0)

    # DXY-konsistenssjekk: hvis DXY er bearish → USD-long bør ikke pushes
    # USDXXX-par: bull = sterk USD → motstridende med DXY bear
    # XXXUSD-par: bear = sterk USD → motstridende med DXY bear
    dxy_conflict = False
    if dxy_dir_color and key != "DXY":
        if key in USD_QUOTE_PAIRS:
            # USDJPY bull = USD styrke → konflikt med DXY bear
            dxy_conflict = (dir_color == "bull" and dxy_dir_color == "bear") or \
                           (dir_color == "bear" and dxy_dir_color == "bull")
        elif key in USD_BASE_PAIRS:
            # EURUSD bull = USD svakhet → konflikt med DXY bull
            dxy_conflict = (dir_color == "bull" and dxy_dir_color == "bull") or \
                           (dir_color == "bear" and dxy_dir_color == "bear")

    cot_confirms = ((cot_bias == "LONG" and dir_color == "bull") or \
                    (cot_bias == "SHORT" and dir_color == "bear")) \
                   and cot_agrees is not False   # Uenige kilder teller ikke
    cot_strong   = abs(cot_pct) > 10 and cot_agrees is not False
    no_event_risk = len(get_binary_risk(inst["key"], hours=4)) == 0

    # BOS fra 1H/4H bekrefter retning (Break of Structure)
    bos_1h_levels = (smc_1h or {}).get("bos_levels", [])
    bos_4h_levels = (smc_4h or {}).get("bos_levels", [])
    recent_bos = sorted(bos_1h_levels + bos_4h_levels, key=lambda b: b["idx"], reverse=True)[:3]
    bos_confirms = any(
        (b["type"] == "BOS_opp" and dir_color == "bull") or
        (b["type"] == "BOS_ned" and dir_color == "bear")
        for b in recent_bos
    )

    # 1H SMC markedsstruktur bekrefter retning
    smc_1h_structure = (smc_1h or {}).get("structure", "MIXED")
    smc_struct_confirms = (
        (dir_color == "bull" and smc_1h_structure in ("BULLISH", "BULLISH_SVAK")) or
        (dir_color == "bear" and smc_1h_structure in ("BEARISH", "BEARISH_SVAK"))
    )

    # Nyhetssentiment bekrefter retning?
    # Krever sterk konsensus (|score| >= 0.5) for å gi poeng — reduserer støy
    ns_label = (news_sentiment or {}).get("label", "neutral")
    ns_score = abs((news_sentiment or {}).get("score", 0))
    nc_map   = NEWS_CONFIRMS_MAP.get(inst["key"], (None, None))
    news_confirms_dir = False
    if ns_score >= 0.5:  # Kun sterk konsensus teller
        if ns_label == "risk_on" and nc_map[0]:
            news_confirms_dir = (nc_map[0] == dir_color)
        elif ns_label == "risk_off" and nc_map[1]:
            news_confirms_dir = (nc_map[1] == dir_color)
    # Nyhetsmotvindsvarsel: nyheter strider klart mot retning (sterk)
    news_headwind = False
    if ns_score >= 0.4:
        if ns_label == "risk_on" and nc_map[0] and nc_map[0] != dir_color:
            news_headwind = True
        elif ns_label == "risk_off" and nc_map[1] and nc_map[1] != dir_color:
            news_headwind = True

    # ── Fundamentals ──────────────────────────────────────────
    inst_fund       = fund_data.get("instrument_scores", {}).get(inst["key"], {})
    inst_fund_score = inst_fund.get("score", 0)
    inst_fund_bias  = inst_fund.get("bias", "neutral")
    fund_confirms   = (inst_fund_score > 0.3 and dir_color == "bull") or \
                      (inst_fund_score < -0.3 and dir_color == "bear")

    # COT momentum Δ — ukentlig endring bekrefter retning
    cot_momentum_ok = (_cot_chg > 0 and dir_color == "bull") or \
                      (_cot_chg < 0 and dir_color == "bear")

    # SMC samlet — BOS + struktur begge kreves
    smc_confirms_ok = bos_confirms and smc_struct_confirms

    # VIX termstruktur — contango alene er ikke nok (normaltilstand 80% av tiden)
    # Krever contango + lav VIX for risk assets, backwardation for safe havens
    vix_regime = (vix_term_structure or {}).get("regime")
    _vix_now = (prices.get("VIX") or {}).get("price", 20)
    SAFE_HAVENS = {"Gold", "Silver", "USDJPY", "USDCHF"}
    if key in SAFE_HAVENS:
        # Backwardation = frykt → bullish for safe havens
        vix_term_ok = (vix_regime == "backwardation" and dir_color == "bull") or \
                      (vix_regime == "contango" and dir_color == "bear" and _vix_now < 18)
    else:
        # Risk assets: contango + VIX < 20 = ekte rolig marked, ikke bare normalt
        vix_term_ok = vix_regime == "contango" and _vix_now < 20

    # ADR utilization — mest av daglig range brukt opp?
    adr = get_adr_utilization(rows_15m, atr_d)
    adr_ok = adr.get("ok_for_scalp", False)  # Ingen data = ingen gratis poeng

    # Nearest level weight (brukes for horisont-bestemmelse)
    nearest_level_weight = max(nearest_sup_w, nearest_res_w)

    # ── Driver-familie-matrise (schema 2.0) ──────────────
    # Se driver_matrix.py: 6 driver-grupper → grade krever multi-group confluens
    # (fikser C1-korrelasjons-bias).
    momentum_aligned = (chg20 > 0.5 and above_sma) or (chg20 < -0.5 and not above_sma)
    # Build macro-context fra lokal scope
    _market_rates = (fund_data.get("market_rates") or {})
    _dfii10 = _market_rates.get("dfii10") or {}

    # Fase 3: beregn alder på COT-data for aktivt asset (brukes i data-quality-gate)
    _active_cot_date = ""
    if cot_source == "ICE":
        _active_cot_date = ice_entry.get("date", "")
    elif cot_source in ("ICE+CFTC", "CFTC"):
        _active_cot_date = cftc_entry.get("date", "") or ice_entry.get("date", "")
    _cot_age_days = None
    if _active_cot_date:
        try:
            _cot_age_days = (datetime.now(timezone.utc).date() -
                             datetime.strptime(_active_cot_date, "%Y-%m-%d").date()).days
        except Exception:
            pass

    _macro_ctx = {
        "dxy_chg5d": (prices.get("DXY") or {}).get("chg5d") if key != "DXY" else chg5,
        "vix_regime": "extreme" if _vix_now >= 35
                      else "elevated" if _vix_now >= 25 else "normal",
        "geo_active": False,   # Settes av caller (push_signals) basert på nyheter
        "brl_chg5d": ((prices.get("USDBRL") or {}).get("chg5d")
                      or (prices.get("BRL") or {}).get("chg5d")),
        "oil_supply_disruption": _oil_supply_disruption,
        "term_spread": _market_rates.get("term_spread"),
        # Fase 0.1: lekk real yields, fear&greed og GS-ratio-z inn i scoringen
        "real_yield_10y":      _dfii10.get("value"),
        "real_yield_chg":      _dfii10.get("chg_5d"),
        "fear_greed":          fg["score"] if isinstance(fg, dict) and "score" in fg else None,
        "gold_silver_ratio_z": _gs_ratio_z,
        # Fase 3: COT-alder for data-quality-gate (per-asset)
        "_cot_age_days":       _cot_age_days,
    }
    _ctx_groups = dgm.build_context_for_asset(inst["key"], _DRIVER_SOURCES, _macro_ctx)
    group_result = dm.score_asset(
        direction=dir_color,
        sma200_aligned=above_sma,
        momentum_aligned=momentum_aligned,
        d1_4h_congruent=(align in ("bull", "bear")),
        cot_bias_aligns=cot_confirms,
        cot_pct=cot_pct,
        cot_momentum_aligns=cot_momentum_ok,
        nearest_level_weight=nearest_level_weight,
        smc_confirms=smc_confirms_ok,
        fibo_zone_hit=False,   # Fibo-zone ikke i dagens pipeline
        **_ctx_groups,
    )
    horizon      = group_result.horizon
    score        = round(group_result.total_score, 2)
    max_score    = 6.0   # Sum av 5 scoring-familier × vekt 1.0 på SWING
    grade        = group_result.grade
    grade_color  = ("bull" if grade in ("A+", "A") else
                    "warn" if grade == "B" else "bear")

    # DXY-konflikt: graduert penalty basert på DXY momentum styrke
    if dxy_conflict:
        base_penalty = 1.0 if horizon in ("SWING", "MAKRO") else 0.5
        penalty = round(base_penalty * dxy_momentum_strength, 2)
        score = max(0, round(score - penalty, 2))
        # Reberegn grade med redusert score
        if score < 3.5 and grade in ("A+", "A"):
            grade = "B" if score >= 2.5 else "C"
            grade_color = "warn" if grade == "B" else "bear"

    # score_details med norske display-navn per driver-gruppe (for dashboard)
    _GROUP_LABELS_NO = {
        "trend":       "Trendbildet (SMA/momentum/align)",
        "positioning": "COT-posisjonering",
        "macro":       "Makrobilde (DXY/VIX/renter)",
        "fundamental": "Fundamentalt (asset-spesifikt)",
        "risk":        "Event-risiko (kalender/geo)",
        "structure":   "Teknisk struktur (HTF/SMC)",
    }
    score_details = [
        {"kryss": _GROUP_LABELS_NO.get(group_key, group_key),
         "id":    f"group_{group_key}",
         "verdi": grp.score >= 0.3,
         "vekt":  round(grp.weight, 2),
         "poeng": round(grp.score * grp.weight, 2),
         # Drivers-liste flatet for tooltip/detaljvisning
         "drivers": grp.drivers}
        for group_key, grp in group_result.driver_groups.items()
    ]
    # Behold criteria-dict som skygge for evt. kode som leser den
    criteria = {
        "sma200":           above_sma,
        "momentum_20d":     momentum_aligned,
        "cot_confirms":     cot_confirms,
        "cot_strong":       cot_strong,
        "cot_momentum":     cot_momentum_ok,
        "htf_level_weight": htf_level_nearby,
        "d1_4h_congruent":  align in ("bull", "bear"),
        "fred_fundamental": fund_confirms,
        "smc_confirms":     smc_confirms_ok,
    }

    # ── C: Signal-stabilitet — signaler som flipper mellom kjøringer nedgraderes
    prev = _prev_signals.get(key, {})
    prev_horizon  = prev.get("horizon", "WATCHLIST")
    prev_dir      = prev.get("dir_color", "")
    stable_signal = True
    if prev_dir and prev_dir != dir_color:
        # Retning flippet siden forrige kjøring → ustabilt signal
        stable_signal = False
    elif prev_horizon not in ("", "WATCHLIST") and horizon not in ("WATCHLIST",) and prev_horizon != horizon:
        # Kun nedgradering er ustabilt — oppgradering (SCALP→SWING) er positivt
        HORIZON_RANK = {"WATCHLIST": 0, "SCALP": 1, "SWING": 2, "MAKRO": 3}
        if HORIZON_RANK.get(horizon, 0) < HORIZON_RANK.get(prev_horizon, 0):
            stable_signal = False
    if not stable_signal and horizon != "WATCHLIST":
        # Nedgrader: MAKRO→SWING, SWING→SCALP, SCALP→WATCHLIST
        if horizon == "MAKRO":    horizon = "SWING"
        elif horizon == "SWING":  horizon = "SCALP"
        else:                     horizon = "WATCHLIST"
        # Re-vei gruppe-scores med ny horisont-vekting
        if horizon != "WATCHLIST":
            new_weights = dm.HORIZON_GROUP_WEIGHTS.get(horizon,
                             dm.HORIZON_GROUP_WEIGHTS["SWING"])
            new_total = 0.0
            for fk, fs in group_result.driver_groups.items():
                if fk == "risk":
                    continue
                fs.weight = new_weights.get(fk, 1.0)
                new_total += fs.score * fs.weight
            score = round(new_total, 2)
            if dxy_conflict:
                base_penalty = 1.0 if horizon in ("SWING", "MAKRO") else 0.5
                penalty = round(base_penalty * dxy_momentum_strength, 2)
                score = max(0, round(score - penalty, 2))
            grade = dm.grade(score, group_result.active_driver_groups)
            grade_color = ("bull" if grade in ("A+", "A") else
                           "warn" if grade == "B" else "bear")
        else:
            grade, grade_color = "C", "bear"

    # ── E: Sesjon-filter — SCALP utenfor optimal sesjon → WATCHLIST
    if horizon == "SCALP" and not sesjon_riktig:
        horizon = "WATCHLIST"
        grade, grade_color = "C", "bear"

    timeframe_bias = horizon  # Bakoverkompatibilitet

    vix_price = (prices.get("VIX") or {}).get("price", 20)
    pos_size  = "Full" if vix_price<20 else "Halv" if vix_price<30 else "Kvart"

    # ── Setups med tagget nivåer ──────────────────────────
    atr_for_setup = atr_15m if atr_15m else (atr_d * 0.4)
    setup_long  = make_setup_l2l(curr, atr_for_setup, atr_d, tagged_sup, tagged_res, "long",  klasse, horizon=horizon, kat=inst["kat"])
    setup_short = make_setup_l2l(curr, atr_for_setup, atr_d, tagged_sup, tagged_res, "short", klasse, horizon=horizon, kat=inst["kat"])
    for s in [setup_long, setup_short]:
        if s: s["session"] = inst["session"]

    # ── SWING/MAKRO-persistens: bevar forrige setup hvis ny ikke fantes ──
    # SWING varer opptil 48t, MAKRO opptil 7 dager
    _PERSIST_HOURS = {"SWING": 48, "MAKRO": 168}
    prev_stab = _prev_signals.get(key, {})
    prev_setup = prev_stab.get("setup")
    if prev_setup and prev_stab.get("dir_color") == dir_color:
        prev_hz = prev_stab.get("horizon", "")
        max_age = _PERSIST_HOURS.get(prev_hz, 0)
        created = prev_stab.get("created", "")
        age_ok = True
        if created and max_age:
            try:
                from datetime import datetime as _dt
                age_h = (datetime.now(timezone.utc) - _dt.fromisoformat(created).replace(
                    tzinfo=timezone.utc if not created.endswith("Z") and "+" not in created else None
                )).total_seconds() / 3600
                age_ok = age_h < max_age
            except Exception:
                age_ok = True  # Ved feil, behold
        if age_ok:
            prev_dir = prev_stab.get("setup_dir", "long")
            # Gjenbruk hvis ny kjøring ikke fant setup i samme retning
            if prev_dir == "long" and setup_long is None:
                # Verifiser at entry-nivå fortsatt er nært nok (innen 2×ATR(D1))
                pe = prev_setup.get("entry", 0)
                if abs(curr - pe) <= atr_d * 2:
                    setup_long = prev_setup
                    setup_long["persisted"] = True
                    setup_long["persist_age_h"] = round(age_h, 1) if 'age_h' in dir() else 0
            elif prev_dir == "short" and setup_short is None:
                pe = prev_setup.get("entry", 0)
                if abs(curr - pe) <= atr_d * 2:
                    setup_short = prev_setup
                    setup_short["persisted"] = True
                    setup_short["persist_age_h"] = round(age_h, 1) if 'age_h' in dir() else 0

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
    # Velg setup strengt basert på dir_color — aldri vis motstatt retnings mål
    active_setup = setup_long if dir_color == "bull" else setup_short
    t1_s = active_setup["t1"]    if active_setup else None
    rr_s = active_setup["rr_t1"] if active_setup else None
    # Ingen aktiv setup: vis nærmeste meningsfulle mål som potensielt (~T1)
    # Filtrer bort nivåer innen 1.5×ATR (for nære til å være nyttige mål)
    if t1_s is None:
        min_dist = (atr_15m or atr_d * 0.4) * 1.5
        cands = tagged_res if dir_color == "bull" else tagged_sup
        cands = [l for l in cands if abs(l["price"] - curr) >= min_dist]
        pot = next((l for l in cands if l["weight"] >= 2), cands[0] if cands else None)
        if pot:
            p = pot["price"]
            t1_s = f"~{round(p, 5 if p < 100 else 2)}"
        else:
            t1_s = "-"
        rr_s = "-"
    st      = "🟢" if at_level_now else "🟡"
    dir_tag = "▲" if dir_color == "bull" else "▼"
    htf_tag = f"HTF:w{max(nearest_sup_w, nearest_res_w)}" if htf_level_nearby else "noHTF"
    print(f"  {st} {inst['navn']:10s} {curr:.5f}  ATR15m={atr_s}  {grade}({score}/{max_score}) {dir_tag} {htf_tag}  T1:{t1_s}  R:R:{rr_s}")

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
        "ema9_4h":       round(ema9_4h,  5) if ema9_4h  else None,
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
        "max_score":     max_score,
        "score_pct":     round(score/max_score*100) if max_score else 0,
        "score_details": score_details,
        # Nye felter fra driver_matrix (schema 2.0)
        "driver_groups":        {
            k: {"score": round(v.score, 2), "weight": round(v.weight, 2),
                "drivers": v.drivers}
            for k, v in group_result.driver_groups.items()
        },
        "active_driver_groups": group_result.active_driver_groups,
        "group_drivers":  group_result.flat_drivers(limit=8),
        "horizon":       horizon,
        "adr_utilization": adr,
        "correlation_group": CORRELATION_GROUPS.get(inst["key"]),
        "dxy_conflict":  dxy_conflict,
        "dxy_momentum_strength": round(dxy_momentum_strength, 3) if dxy_conflict else None,
        "stable_signal": stable_signal,
        "in_session":    sesjon_riktig,
        "news_headwind": news_headwind,
        "news_sentiment_label": ns_label,
        "open_interest": oi,
        "resistances":   fmt_level(tagged_res, "R", atr_15m or atr_d),
        "supports":      fmt_level(tagged_sup, "S", atr_15m or atr_d),
        "setup_long":    setup_long,
        "setup_short":   setup_short,
        "binary_risk":   get_binary_risk(inst["key"]),
        "oil_supply_disruption": _oil_supply_disruption if key in ("Brent", "WTI") else None,
        "oil_supply_reason": _oil_supply_reason if key in ("Brent", "WTI") and _oil_supply_disruption else None,
        "smc": {
            "structure":    smc["structure"]    if smc else None,
            "supply_zones": smc["supply_zones"] if smc else [],
            "demand_zones": smc["demand_zones"] if smc else [],
            "bos_levels":   smc["bos_levels"]   if smc else [],
            "last_swing_high": smc["last_swing_high"] if smc else None,
            "last_swing_low":  smc["last_swing_low"]  if smc else None,
        },
        "smc_1h": {
            "structure":    smc_1h["structure"]    if smc_1h else None,
            "supply_zones": smc_1h["supply_zones"] if smc_1h else [],
            "demand_zones": smc_1h["demand_zones"] if smc_1h else [],
            "bos_levels":   smc_1h["bos_levels"]   if smc_1h else [],
            "last_swing_high": smc_1h["last_swing_high"] if smc_1h else None,
            "last_swing_low":  smc_1h["last_swing_low"]  if smc_1h else None,
        },
        "smc_4h": {
            "structure":    smc_4h["structure"]    if smc_4h else None,
            "supply_zones": smc_4h["supply_zones"] if smc_4h else [],
            "demand_zones": smc_4h["demand_zones"] if smc_4h else [],
            "bos_levels":   smc_4h["bos_levels"]   if smc_4h else [],
            "last_swing_high": smc_4h["last_swing_high"] if smc_4h else None,
            "last_swing_low":  smc_4h["last_swing_low"]  if smc_4h else None,
        },
        "dxy_conf":      "medvind" if (inst["kat"]=="valuta" and (prices.get("DXY") or {}).get("chg5d",0)<0) else "motvind",
        "pos_size":      pos_size,
        "vix_spread_factor": 1.0 if vix_price<20 else 1.5 if vix_price<30 else 2.0,
        "cot":           {"bias": cot_bias, "color": cot_color, "net": spec_net,
                          "chg": _cot_chg, "pct": round(abs(cot_pct),1),
                          "momentum": cot_momentum,
                          "date": (ice_entry if has_ice else cftc_entry).get("date",""),
                          "report": cot_source.lower(),
                          "source": cot_source,
                          "agrees": cot_agrees},
        "combined_bias":  "LONG" if dir_color=="bull" else "SHORT",
        "timeframe_bias": timeframe_bias,
        "sentiment":      {"fear_greed": fg},
        "fundamentals": {
            "score":      inst_fund_score,
            "bias":       inst_fund_bias,
            "confirms":   fund_confirms,
            "categories": {
                cat: fund_data.get("category_scores", {}).get(cat, {})
                for cat in ("econ_growth", "inflation", "jobs")
            },
            "indicators": fund_data.get("indicators", {}),
            "usd_bias":   fund_data.get("usd_fundamental", {}).get("bias", "neutral"),
            "updated":    fund_data.get("updated", ""),
        },
    }

# ── VIX term-struktur (allerede beregnet i loopen) ───────────
# Fallback hvis VIX ble hoppet over
if vix_term_structure is None and _vix9d and _vix3m:
    _vix_spot = (prices.get("VIX") or {}).get("price")
    if _vix_spot:
        s9  = round((_vix9d / _vix_spot - 1) * 100, 1)
        s3m = round((_vix3m / _vix_spot - 1) * 100, 1)
        regime = ("backwardation" if _vix9d < _vix_spot * 0.98 else
              "flat"          if abs(s9) < 2 else "contango")
    vix_term_structure = {
        "spot": _vix_spot, "vix9d": _vix9d, "vix3m": _vix3m,
        "spot_to_9d_pct": s9, "spot_to_3m_pct": s3m, "regime": regime,
    }
    print(f"  VIX9D={_vix9d:.2f}  VIX3M={_vix3m:.2f}  regime={regime}")

# ── Korrelasjonsmatrise (20-dagers Pearson) ─────────────────
def pearson_corr(a, b, n=20):
    pairs = list(zip(a, b))[-n:]
    if len(pairs) < 5:
        return None
    ra = [pairs[i][0]/pairs[i-1][0]-1 for i in range(1, len(pairs))]
    rb = [pairs[i][1]/pairs[i-1][1]-1 for i in range(1, len(pairs))]
    if not ra or not rb:
        return None
    ma, mb = sum(ra)/len(ra), sum(rb)/len(rb)
    num  = sum((ra[i]-ma)*(rb[i]-mb) for i in range(len(ra)))
    dena = sum((x-ma)**2 for x in ra)**0.5
    denb = sum((x-mb)**2 for x in rb)**0.5
    if dena*denb == 0:
        return 0.0
    return round(num / (dena*denb), 2)

CORR_LABELS = {"EURUSD": "EUR/USD", "Gold": "XAU/USD", "NAS100": "US100", "Brent": "Brent"}
corr_matrix = {}
for k1 in CORR_KEYS:
    corr_matrix[k1] = {}
    for k2 in CORR_KEYS:
        if k1 == k2:
            corr_matrix[k1][k2] = 1.0
        else:
            c1 = daily_closes_for_corr.get(k1, [])
            c2 = daily_closes_for_corr.get(k2, [])
            corr_matrix[k1][k2] = pearson_corr(c1, c2) if c1 and c2 else None

correlations = {
    "labels":  [CORR_LABELS[k] for k in CORR_KEYS],
    "keys":    CORR_KEYS,
    "matrix":  [[corr_matrix[k1].get(k2) for k2 in CORR_KEYS] for k1 in CORR_KEYS],
    "period":  "20d",
}
print(f"  Korrelasjoner: {len(CORR_KEYS)}×{len(CORR_KEYS)} matrise")

# ── Gjennomsnittlig daglig range (ADR) per instrument ───────
session_ranges = {}
for key, ranges in daily_adr_cache.items():
    if not ranges:
        continue
    adr = sum(ranges) / len(ranges)
    lv  = levels.get(key, {})
    adr_pct = round(adr / lv.get("current", adr) * 100, 2) if lv.get("current") else None
    session_ranges[key] = {
        "name":    lv.get("name", key),
        "adr_20d": round(adr, 5 if adr < 1 else 2),
        "adr_pct": adr_pct,
        "atr14":   lv.get("atr_daily"),
    }

# ── Makro-indikatorer ──────────────────────────────────────
print("Henter makro-indikatorer (HYG, TIP, TNX, IRX, Kobber, EM)...")
macro_ind = fetch_macro_indicators()
for k, v in macro_ind.items():
    if v: print(f"  {k}: {v['price']}  5d={v['chg5d']:+.2f}%")
    else: print(f"  {k}: FEIL")

# HY kredittrisiko: HYG ned > 1.5% siste 5d = kredittpress
hyg         = macro_ind.get("HYG") or {}
hy_chg5d    = hyg.get("chg5d", 0)
hy_stress   = hy_chg5d < -1.5

# TIPS (realrenter / inflasjonsforventninger)
tip         = macro_ind.get("TIP") or {}
tip_trend_5d = tip.get("chg5d", 0)

# Rentekurve: 10Y minus 3M (invertert < 0 = resesjonsrisiko)
tnx         = macro_ind.get("TNX") or {}
irx         = macro_ind.get("IRX") or {}
yield_10y   = tnx.get("price")
yield_3m    = irx.get("price")
yield_curve = round(yield_10y - yield_3m, 2) if (yield_10y and yield_3m) else None

# Kobber (vekstindikator): trend 5d
copper      = macro_ind.get("Copper") or {}
copper_5d   = copper.get("chg5d", 0)

# Emerging Markets (risikoappetitt)
eem         = macro_ind.get("EEM") or {}
em_5d       = eem.get("chg5d", 0)

# ── Makro ──────────────────────────────────────────────────
vix_price   = (prices.get("VIX") or {}).get("price", 20)
dxy_5d      = (prices.get("DXY") or {}).get("chg5d", 0)
brent_p     = (prices.get("Brent") or {}).get("price", 80)
fg_score    = fg["score"] if fg else 50
cot_dxy     = cot_data.get("usd index",{})
cot_dxy_net = ((cot_dxy.get("spekulanter") or {}).get("net",0) or 0)
conflicts   = detect_conflict(vix_price, dxy_5d, fg, cot_dxy_net, hy_stress, yield_curve, news_sentiment)

# Dollar Smile: hy_stress eller yield_curve inversion gir risk-off bias
risk_off_signals = sum([vix_price > 25, hy_stress, (yield_curve or 0) < -0.3, (fg["score"] if fg else 50) < 35])
if conflicts:
    smile_pos,usd_bias,usd_color,smile_desc = "konflikt","UKLAR","warn","Motstridende signaler: "+" | ".join(conflicts[:2])
elif vix_price > 30 or risk_off_signals >= 2:
    smile_pos,usd_bias,usd_color,smile_desc = "venstre","STERKT","bull","Risk-off – USD trygg havn"
elif vix_price < 18 and brent_p < 85 and not hy_stress:
    smile_pos,usd_bias,usd_color,smile_desc = "midten","SVAKT","bear","Goldilocks – svak USD"
else:
    smile_pos,usd_bias,usd_color,smile_desc = "hoyre","MODERAT","bull","Vekst/inflasjon driver USD"

if vix_price > 30:
    vix_regime = {"value":vix_price,"label":"Ekstrem frykt – KVART størrelse","color":"bear","regime":"extreme"}
elif vix_price > 20:
    vix_regime = {"value":vix_price,"label":"Forhøyet – HALV størrelse","color":"warn","regime":"elevated"}
else:
    vix_regime = {"value":vix_price,"label":"Normalt – full størrelse","color":"bull","regime":"normal"}

# Kopier HYG og TIP fra macro_ind til prices slik at priser-fanen kan vise dem
for k in ("HYG", "TIP"):
    if macro_ind.get(k):
        prices[k] = macro_ind[k]

macro = {
    "date":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "cot_date": max((d.get("date","") for d in cot_data.values() if d.get("date")), default="ukjent"),
    "prices":  prices,
    "vix_regime": vix_regime,
    "sentiment": {"fear_greed": fg, "news": news_sentiment, "conflicts": conflicts},
    "dollar_smile": {
        "position":smile_pos,"usd_bias":usd_bias,"usd_color":usd_color,"desc":smile_desc,
        "conflicts": conflicts,
        "inputs": {
            "vix":          vix_price,
            "hy_stress":    hy_stress,
            "hy_chg5d":     hy_chg5d,
            "brent":        brent_p,
            "tip_trend_5d": tip_trend_5d,
            "dxy_trend_5d": dxy_5d,
            "yield_curve":  yield_curve,
            "yield_10y":    yield_10y,
            "yield_3m":     yield_3m,
            "copper_5d":    copper_5d,
            "em_5d":        em_5d,
        }
    },
    "macro_indicators":    macro_ind,
    "trading_levels":      levels,
    "calendar":            calendar_events,
    "vix_term_structure":  vix_term_structure,
    "correlations":        correlations,
    "session_ranges":      session_ranges,
}

if len(levels) == 0:
    try:
        with open(OUT) as f:
            existing = json.load(f)
        old_levels = existing.get("trading_levels", {})
        if old_levels:
            macro["trading_levels"] = old_levels
            print(f"\nADVARSEL: 0 instrumenter hentet — beholder eksisterende trading_levels ({len(old_levels)} stk)")
    except Exception:
        pass

with open(OUT,"w") as f:
    json.dump(macro, f, ensure_ascii=False, indent=2)

# Lagre stabilitetsdata for neste kjøring (inkludert aktive setups for persistens)
_new_stability = {}
for k, v in levels.items():
    active_setup = v.get("setup_long") if v.get("dir_color") == "bull" else v.get("setup_short")
    _new_stability[k] = {
        "horizon": v.get("horizon", "WATCHLIST"),
        "dir_color": v.get("dir_color", ""),
        "score": v.get("score", 0),
        "grade": v.get("grade", "C"),
        # Lagre aktiv setup for SWING/MAKRO-persistens
        "setup": active_setup if active_setup and v.get("horizon") in ("SWING", "MAKRO") else None,
        "setup_dir": "long" if v.get("dir_color") == "bull" else "short",
        "created": _prev_signals.get(k, {}).get("created") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M"),
    }
try:
    with open(STABILITY_FILE, "w") as f:
        json.dump(_new_stability, f, ensure_ascii=False, indent=2)
except Exception:
    pass

print(f"\nOK → {OUT}  ({len(macro['trading_levels'])} instruments)")
if conflicts:
    print("Konflikter:"); [print(f"  ⚠️  {c}") for c in conflicts]
