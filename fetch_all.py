#!/usr/bin/env python3
import urllib.request, urllib.parse, json, os, time, re
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

# ─── VEKTER PER KRITERIUM PER HORISONT ───────────────────────────
# 14 kriterier, vektet ulikt per handelshorisont
SCORE_WEIGHTS = {
    "sma200":             {"SCALP": 1.0,  "SWING": 1.0,  "MAKRO": 1.0},
    "momentum_20d":       {"SCALP": 1.0,  "SWING": 1.0,  "MAKRO": 1.0},
    "cot_confirms":       {"SCALP": 0,    "SWING": 1.0,  "MAKRO": 1.0},
    "cot_strong":         {"SCALP": 0,    "SWING": 0.5,  "MAKRO": 1.0},
    "cot_momentum":       {"SCALP": 0,    "SWING": 1.0,  "MAKRO": 1.0},
    "price_at_level":     {"SCALP": 1.5,  "SWING": 1.5,  "MAKRO": 1.5},
    "htf_level_weight":   {"SCALP": 1.0,  "SWING": 1.0,  "MAKRO": 1.0},
    "d1_4h_congruent":    {"SCALP": 1.0,  "SWING": 1.0,  "MAKRO": 1.0},
    "no_event_risk":      {"SCALP": 1.0,  "SWING": 1.0,  "MAKRO": 1.0},
    "news_sentiment":     {"SCALP": 0.5,  "SWING": 0.5,  "MAKRO": 0.5},
    "fred_fundamental":   {"SCALP": 0,    "SWING": 0.5,  "MAKRO": 1.0},
    "smc_confirms":       {"SCALP": 1.0,  "SWING": 1.0,  "MAKRO": 1.0},
    "vix_term_structure": {"SCALP": 0,    "SWING": 0.5,  "MAKRO": 1.0},
    "adr_utilization":    {"SCALP": 1.0,  "SWING": 0,    "MAKRO": 0},
}
# MAX: SCALP=9.0, SWING=12.0, MAKRO=13.0
MAX_WEIGHTED_SCORE = {
    h: sum(w[h] for w in SCORE_WEIGHTS.values())
    for h in ("SCALP", "SWING", "MAKRO")
}

GRADE_THRESHOLDS = {
    "SCALP": {"A+": 8.0, "A": 6.5, "B": 4.5},
    "SWING": {"A+": 10.0, "A": 8.5, "B": 6.5},
    "MAKRO": {"A+": 11.5, "A": 9.5, "B": 7.5},
}

PUSH_THRESHOLDS = {
    "SCALP": 5.5,
    "SWING": 7.5,
    "MAKRO": 8.5,
}

SCORE_LABELS_NO = {
    "sma200":             "Over SMA200",
    "momentum_20d":       "Momentum 20d",
    "cot_confirms":       "COT bekrefter",
    "cot_strong":         "COT sterk (>10%)",
    "cot_momentum":       "COT momentum Δ",
    "price_at_level":     "Pris VED nivå",
    "htf_level_weight":   "HTF-nivå ≥ 3",
    "d1_4h_congruent":    "D1+4H kongruent",
    "no_event_risk":      "Ingen event-risiko",
    "news_sentiment":     "Nyhetssentiment",
    "fred_fundamental":   "Fundamental",
    "smc_confirms":       "SMC bekrefter",
    "vix_term_structure": "VIX termstruktur",
    "adr_utilization":    "ADR < 70%",
}

# ─── KORRELASJONSGRUPPER (for bot max-posisjoner) ────────────────
CORRELATION_GROUPS = {
    "EURUSD": "usd_pairs", "GBPUSD": "usd_pairs",
    "USDJPY": "usd_pairs", "AUDUSD": "usd_pairs",
    "Gold": "precious_metals", "Silver": "precious_metals",
    "Brent": "energy", "WTI": "energy",
    "SPX": "us_indices", "NAS100": "us_indices",
}
MAX_CONCURRENT = {
    "precious_metals": 2, "us_indices": 1, "energy": 1, "usd_pairs": 2,
}

# ─── HORISONT-CONFIG (sendes til boten via signal_server) ────────
HORIZON_CONFIGS = {
    "SCALP": {
        "confirmation_tf": "5min",
        "confirmation_max_candles": 6,
        "confirmation_escape_atr_factor": 0.5,
        "confirmation_min_score": 2,
        "confirmation_strict_score": 3,
        "entry_zone_margin": 0.0015,
        "exit_t1_close_pct": 0.50,
        "exit_t2_close_pct": None,
        "exit_trail_tf": "5min",
        "exit_trail_atr_mult": {"fx": 2.0, "gold": 2.5, "silver": 2.5, "oil": 2.5, "index": 2.0},
        "exit_ema_tf": "5min",
        "exit_ema_period": 9,
        "exit_timeout_partial_candles": 8,
        "exit_timeout_partial_pct": 0.50,
        "exit_timeout_full_candles": 16,
        "exit_geo_spike_atr_mult": 2.0,
        "sizing_base_risk_usd": 20,
    },
    "SWING": {
        "confirmation_tf": "15min",
        "confirmation_max_candles": 8,
        "confirmation_escape_atr_factor": 0.7,
        "confirmation_min_score": 2,
        "confirmation_strict_score": 3,
        "entry_zone_margin": 0.0025,
        "exit_t1_close_pct": 0.33,
        "exit_t2_close_pct": 0.33,
        "exit_trail_tf": "1H",
        "exit_trail_atr_mult": {"fx": 3.0, "gold": 4.0, "silver": 4.0, "oil": 3.5, "index": 3.0},
        "exit_ema_tf": "1H",
        "exit_ema_period": 9,
        "exit_be_timeout_hours": 48,
        "exit_timeout_full_hours": 120,
        "exit_event_close_hours": 2,
        "exit_geo_spike_atr_mult": 3.0,
        "sizing_base_risk_usd": 40,
    },
    "MAKRO": {
        "confirmation_tf": "1H",
        "confirmation_max_candles": 6,
        "confirmation_escape_atr_factor": 1.0,
        "confirmation_min_score": 2,
        "confirmation_strict_score": 3,
        "entry_zone_margin": 0.0040,
        "exit_t1_close_pct": 0.25,
        "exit_t2_close_pct": 0.25,
        "exit_trail_tf": "D1",
        "exit_trail_atr_mult": {"fx": 2.0, "gold": 2.5, "silver": 2.5, "oil": 2.5, "index": 2.0},
        "exit_ema_tf": "D1",
        "exit_ema_period": 9,
        "exit_timeout_days": 15,
        "exit_score_deterioration": 6.0,
        "exit_geo_spike_atr_mult": 3.0,
        "sizing_base_risk_usd": 60,
    },
}

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


def determine_horizon(criteria, nearest_level_weight):
    """Bestem horisont basert på rå bool-kriterier og nivå-vekt."""
    has_cot     = criteria.get("cot_confirms", False)
    has_level   = criteria.get("price_at_level", False)
    raw_count   = sum(1 for v in criteria.values() if v)
    if raw_count >= 8 and has_cot and nearest_level_weight >= 4:
        return "MAKRO"
    elif raw_count >= 6 and nearest_level_weight >= 3:
        return "SWING"
    elif raw_count >= 4 and has_level:
        return "SCALP"
    return "WATCHLIST"


def calculate_weighted_score(criteria, horizon):
    """Beregn vektet score. Returnerer (score, max, details_list)."""
    h = horizon if horizon != "WATCHLIST" else "SCALP"
    score = 0.0
    details = []
    for crit_id, passed in criteria.items():
        weight = SCORE_WEIGHTS.get(crit_id, {}).get(h, 0)
        earned = weight if passed else 0
        details.append({
            "kryss":  SCORE_LABELS_NO.get(crit_id, crit_id),
            "id":     crit_id,
            "verdi":  passed,
            "vekt":   weight,
            "poeng":  earned,
        })
        score += earned
    return round(score, 1), MAX_WEIGHTED_SCORE[h], details


def get_grade(score, horizon):
    if horizon == "WATCHLIST":
        return "C", "bear"
    t = GRADE_THRESHOLDS[horizon]
    if score >= t["A+"]:  return "A+", "bull"
    elif score >= t["A"]: return "A",  "bull"
    elif score >= t["B"]: return "B",  "warn"
    return "C", "bear"


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


def make_setup_l2l(curr, atr_15m, atr_daily, sup_tagged, res_tagged, direction, klasse, min_rr=1.5):
    """
    Makro level-til-level setup — strukturbasert stop loss:

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
    """
    if not atr_15m or atr_15m <= 0:
        return None
    if not atr_daily or atr_daily <= 0:
        atr_daily = atr_15m * 5

    def structural_sl(entry_level, entry_obj, dir):
        """SL ved strukturnivå — aldri mekanisk ATR fra nåpris."""
        buf = atr_daily * 0.15
        w   = entry_obj.get("weight", 1)
        if dir == "long":
            zone_bot = entry_obj.get("zone_bottom")
            if zone_bot and zone_bot < entry_level:
                return round(zone_bot - buf, 5)
            sl_buf = atr_daily * (0.5 if w >= 4 else 0.3)
            return round(entry_level - sl_buf, 5)
        else:
            zone_top = entry_obj.get("zone_top")
            if zone_top and zone_top > entry_level:
                return round(zone_top + buf, 5)
            sl_buf = atr_daily * (0.5 if w >= 4 else 0.3)
            return round(entry_level + sl_buf, 5)

    def best_t1(levels, entry, min_dist):
        """Beste T1: høyest HTF-weight → nærmest entry, minst min_dist unna."""
        cands = sorted(levels, key=lambda x: (-x["weight"], abs(x["price"] - entry)))
        for l in cands:
            p = l["price"]
            ok = (p > entry + min_dist) if direction == "long" else (p < entry - min_dist)
            if ok:
                q = "htf" if l["weight"] >= 3 else ("4h" if l["weight"] >= 2 else "weak")
                return dict(l, t1_quality=q)
        return None

    if direction == "long":
        if not sup_tagged or not res_tagged:
            return None
        entry_obj   = sup_tagged[0]
        entry_level = entry_obj["price"]
        entry_w     = entry_obj["weight"]

        entry_dist = curr - entry_level
        max_entry_dist = atr_daily * (0.3 if entry_w <= 1 else 0.7 if entry_w == 2 else 1.0)
        if entry_dist < 0 or entry_dist > max_entry_dist:
            return None

        sl   = structural_sl(entry_level, entry_obj, "long")
        risk = entry_level - sl
        if risk <= 0:
            return None
        min_t1_dist = risk * min_rr

        t1_obj = best_t1(res_tagged, entry_level, min_t1_dist)
        if t1_obj is None:
            t1_obj = {"price": round(entry_level + min_t1_dist, 5),
                      "t1_quality": "weak", "weight": 0, "source": "projected"}
        t1 = t1_obj["price"]

        res_after = [l for l in res_tagged if l["price"] > t1]
        t2 = res_after[0]["price"] if res_after else round(t1 + risk, 5)

        rr1 = round((t1 - entry_level) / risk, 2)
        rr2 = round((t2 - entry_level) / risk, 2)

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
        entry_obj   = res_tagged[0]
        entry_level = entry_obj["price"]
        entry_w     = entry_obj["weight"]

        entry_dist = entry_level - curr
        max_entry_dist = atr_daily * (0.3 if entry_w <= 1 else 0.7 if entry_w == 2 else 1.0)
        if entry_dist < 0 or entry_dist > max_entry_dist:
            return None

        sl   = structural_sl(entry_level, entry_obj, "short")
        risk = sl - entry_level
        if risk <= 0:
            return None
        min_t1_dist = risk * min_rr

        t1_obj = best_t1(sup_tagged, entry_level, min_t1_dist)
        if t1_obj is None:
            t1_obj = {"price": round(entry_level - min_t1_dist, 5),
                      "t1_quality": "weak", "weight": 0, "source": "projected"}
        t1 = t1_obj["price"]

        sup_after = [l for l in sup_tagged if l["price"] < t1]
        t2 = sup_after[0]["price"] if sup_after else round(t1 - risk, 5)

        rr1 = round((entry_level - t1) / risk, 2)
        rr2 = round((entry_level - t2) / risk, 2)

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

# USD-par der "bull" = sterkere USD. Invers = XXXUSD-par der "bull" = svakere USD
USD_QUOTE_PAIRS = {"USDJPY", "USDCHF", "USDCAD", "USDNOK"}  # bull = USD styrke
USD_BASE_PAIRS  = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"}   # bull = USD svakhet

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

    # Lagre DXY-retning for bruk i USD-par
    if key == "DXY":
        dxy_dir_color = dir_color

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
    ns_label = (news_sentiment or {}).get("label", "neutral")
    nc_map   = NEWS_CONFIRMS_MAP.get(inst["key"], (None, None))
    if ns_label == "risk_on" and nc_map[0]:
        news_confirms_dir = (nc_map[0] == dir_color)
    elif ns_label == "risk_off" and nc_map[1]:
        news_confirms_dir = (nc_map[1] == dir_color)
    else:
        news_confirms_dir = False
    # Nyhetsmotvindsvarsel: nyheter strider klart mot retning
    news_headwind = False
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

    # VIX termstruktur — contango = normalt, backwardation = frykt/volatilitet
    # Safe havens (gull, JPY, CHF) tjener på frykt → backwardation er bullish
    vix_regime = (vix_term_structure or {}).get("regime")
    SAFE_HAVENS = {"Gold", "Silver", "USDJPY", "USDCHF"}
    if key in SAFE_HAVENS:
        # Contango = rolig → nøytral for safe havens
        # Backwardation = frykt → bullish for safe havens (når dir_color == bull)
        vix_term_ok = (vix_regime == "backwardation" and dir_color == "bull") or \
                      (vix_regime == "contango" and dir_color == "bear")
    else:
        # Risk assets: contango = normalt/rolig → bullish
        vix_term_ok = vix_regime == "contango"

    # ADR utilization — mest av daglig range brukt opp?
    adr = get_adr_utilization(rows_15m, atr_d)
    adr_ok = adr.get("ok_for_scalp", True)

    # Nearest level weight (brukes for horisont-bestemmelse)
    nearest_level_weight = max(nearest_sup_w, nearest_res_w)

    # ── 14-punkt vektet scoring ──────────────────────────
    criteria = {
        "sma200":             above_sma,
        "momentum_20d":       (chg20 > 0 if dir_color == "bull" else chg20 < 0),
        "cot_confirms":       cot_confirms,
        "cot_strong":         cot_strong,
        "cot_momentum":       cot_momentum_ok,
        "price_at_level":     at_level_now,
        "htf_level_weight":   htf_level_nearby,
        "d1_4h_congruent":    align in ("bull", "bear"),
        "no_event_risk":      no_event_risk,
        "news_sentiment":     news_confirms_dir,
        "fred_fundamental":   fund_confirms,
        "smc_confirms":       smc_confirms_ok,
        "vix_term_structure": vix_term_ok,
        "adr_utilization":    adr_ok,
    }

    horizon = determine_horizon(criteria, nearest_level_weight)
    score, max_score, score_details = calculate_weighted_score(criteria, horizon)

    # DXY-konflikt er nå bakt inn i dir_score — ingen ekstra penalty
    # dxy_conflict beholdes kun som info-felt for display

    grade, grade_color = get_grade(score, horizon)
    timeframe_bias = horizon  # Bakoverkompatibilitet

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
        "horizon":       horizon,
        "adr_utilization": adr,
        "correlation_group": CORRELATION_GROUPS.get(inst["key"]),
        "dxy_conflict":  dxy_conflict,
        "news_headwind": news_headwind,
        "news_sentiment_label": ns_label,
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
print(f"\nOK → {OUT}  ({len(macro['trading_levels'])} instruments)")
if conflicts:
    print("Konflikter:"); [print(f"  ⚠️  {c}") for c in conflicts]
