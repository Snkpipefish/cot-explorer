#!/usr/bin/env python3
"""
fetch_prices.py — Henter live priser og bygger data/macro/latest.json

Prioritet per symbol:
  1. data/prices/live_prices.json  (fra trading-boten via Skilling — oppdateres hvert 4. time)
  2. Yahoo Finance                 (fallback for symboler boten ikke har)
"""
import urllib.request, urllib.parse, json, os
from datetime import datetime, timezone
from pathlib import Path

BASE         = Path(os.path.expanduser("~/cot-explorer/data"))
OUT          = BASE / "macro" / "latest.json"
BOT_PRICES   = Path.home() / "scalp_edge" / "live_prices.json"
PRICE_HIST   = BASE / "prices" / "bot_history.json"
OUT.parent.mkdir(parents=True, exist_ok=True)
PRICE_HIST.parent.mkdir(parents=True, exist_ok=True)


def load_price_history():
    try:
        return json.loads(PRICE_HIST.read_text())
    except Exception:
        return {}


def save_price_history(hist):
    PRICE_HIST.write_text(json.dumps(hist, ensure_ascii=False))


def update_price_history(hist, key, price):
    """Legg til nåværende pris i historikk. Behold maks 500 innslag (~20 dager timesvis)."""
    now_ts = datetime.now(timezone.utc).isoformat()
    entries = hist.setdefault(key, [])
    entries.append({"price": price, "ts": now_ts})
    hist[key] = entries[-500:]


def chg_from_history(hist, key, current_price, hours_back):
    """Beregn prosentendring fra pris X timer tilbake."""
    entries = hist.get(key, [])
    if not entries:
        return 0.0
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    # Finn innslag nærmest cutoff
    best = None
    best_diff = None
    for e in entries:
        try:
            ts = datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))
            diff = abs((ts - cutoff).total_seconds())
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best = e
        except Exception:
            continue
    if best is None or best["price"] == 0:
        return 0.0
    return round((current_price - best["price"]) / best["price"] * 100, 2)

# Alle symboler vi trenger i macro/latest.json
# nøkkel → Yahoo-ticker (brukes kun som fallback)
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

# Alle nøkler boten sender i live_prices.json → nøkkel i macro prices
# None = boten har den men den brukes ikke i macro (f.eks. bare i oilgas/crypto)
BOT_KEY_MAP = {
    "EURUSD":  "EURUSD",
    "GBPUSD":  "GBPUSD",
    "USDJPY":  "USDJPY",
    "AUDUSD":  "AUDUSD",
    "USDCHF":  "USDCHF",
    "USDNOK":  "USDNOK",
    "USDCAD":  "USDCAD",
    "NZDUSD":  "NZDUSD",
    "EURGBP":  "EURGBP",
    "DXY":     "DXY",
    "Brent":   "Brent",
    "WTI":     "WTI",
    "Gold":    "Gold",
    "Silver":  "Silver",
    "NatGas":  None,       # brukes kun av fetch_oilgas
    "SPX":     "SPX",
    "NAS100":  "NAS100",
    "BTC":     "BTC",
    "ETH":     "ETH",
    "SOL":     "SOL",
    "XRP":     "XRP",
    "ADA":     "ADA",
    "DOGE":    "DOGE",
    # Jordbruksråvarer (nye fra bot)
    "Coffee":  "Coffee",
    "Cotton":  "Cotton",
    "Sugar":   "Sugar",
    "Cocoa":   "Cocoa",
    "Corn":    "Corn",
    "Soybean": "Soybean",
    "Wheat":   "Wheat",
}


def load_bot_prices():
    """Les live_prices.json fra boten. Returnerer dict med macro-nøkkel → pris-objekt.

    Støtter to formater:
      Flatt:  {KEY: {"value": 1.085, "updated": "..."}, ...}
      Nestet: {"prices": {KEY: {"value": ..., "chg1d": ...}}}
    """
    if not BOT_PRICES.exists():
        return {}
    try:
        raw = json.loads(BOT_PRICES.read_text())
        # Flatt format (bot sender direkte) eller nestet (via signal_server)
        bot = raw if isinstance(raw, dict) and "value" not in raw and "prices" not in raw \
              else raw.get("prices", raw)
        result = {}
        for bot_key, macro_key in BOT_KEY_MAP.items():
            if macro_key is None:
                continue
            p = bot.get(bot_key)
            if not p or p.get("value") is None:
                continue
            val    = float(p["value"])
            chg1d  = float(p.get("chg1d",  0.0) or 0.0)
            chg5d  = float(p.get("chg5d",  0.0) or 0.0)
            chg20d = float(p.get("chg20d", 0.0) or 0.0)
            result[macro_key] = {
                "price":  round(val, 6),
                "chg1d":  round(chg1d, 3),
                "chg5d":  round(chg5d, 3),
                "chg20d": round(chg20d, 3),
            }
        return result
    except Exception as e:
        print(f"  live_prices.json FEIL: {e}")
        return {}


def fetch_yahoo(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=1mo"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        res    = d["chart"]["result"][0]
        closes = res["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if len(closes) < 6:
            return None
        now   = closes[-1]
        day1  = closes[-2]
        day5  = closes[-6]  if len(closes) >= 6  else closes[0]
        day20 = closes[-21] if len(closes) >= 21 else closes[0]
        return {
            "price":  round(now, 4),
            "chg1d":  round((now / day1  - 1) * 100, 2),
            "chg5d":  round((now / day5  - 1) * 100, 2),
            "chg20d": round((now / day20 - 1) * 100, 2),
        }
    except Exception as e:
        print(f"  FEIL {symbol}: {e}")
        return None


# ── Last inn prishistorikk og bot-priser ─────────────────────────
price_hist = load_price_history()
bot_prices = load_bot_prices()
if bot_prices:
    print(f"  Bot-priser (Skilling): {len(bot_prices)} symboler lastet fra live_prices.json")

# ── Hent resten fra Yahoo (kun symboler boten ikke dekker) ────────
prices = {}
for key, sym in SYMBOLS.items():
    if key in bot_prices:
        new_price = bot_prices[key]["price"]
        update_price_history(price_hist, key, new_price)
        prices[key] = {
            "price":  new_price,
            "chg1d":  chg_from_history(price_hist, key, new_price, 24),
            "chg5d":  chg_from_history(price_hist, key, new_price, 120),
            "chg20d": chg_from_history(price_hist, key, new_price, 480),
            "source": "bot",
        }
        print(f"  {key:10} → {new_price} (bot, 1d={prices[key]['chg1d']:+.2f}%)")
        continue
    print(f"Henter {key} ({sym}) fra Yahoo...")
    v = fetch_yahoo(sym)
    if v:
        prices[key] = v
        print(f"  → {v['price']} ({v['chg1d']:+.2f}%)")

# Legg til krypto og jordbruksråvarer fra bot
for extra_key in ("BTC", "ETH", "SOL", "XRP", "ADA", "DOGE",
                  "Corn", "Wheat", "Soybean", "Coffee", "Cotton", "Sugar", "Cocoa"):
    if extra_key in bot_prices and extra_key not in prices:
        new_price = bot_prices[extra_key]["price"]
        update_price_history(price_hist, extra_key, new_price)
        prices[extra_key] = {
            "price":  new_price,
            "chg1d":  chg_from_history(price_hist, extra_key, new_price, 24),
            "chg5d":  chg_from_history(price_hist, extra_key, new_price, 120),
            "chg20d": chg_from_history(price_hist, extra_key, new_price, 480),
            "source": "bot",
        }
        print(f"  {extra_key:10} → {new_price} (bot)")

save_price_history(price_hist)

# ── Bygg macro-objekt ─────────────────────────────────────────────
vix    = (prices.get("VIX")   or {}).get("price", 20)
dxy_5d = (prices.get("DXY")   or {}).get("chg5d", 0)
brent  = (prices.get("Brent") or {}).get("price", 80)
hyg    = (prices.get("HYG")   or {}).get("chg5d", 0)
tip_5d = (prices.get("TIP")   or {}).get("chg5d", 0)

hy_stress = hyg < -1.0
if vix > 30:
    smile_pos, usd_bias, usd_color, smile_desc = "venstre", "STERKT",   "bull", "Risk-off – USD etterspurt som trygg havn"
elif vix < 18 and brent < 85:
    smile_pos, usd_bias, usd_color, smile_desc = "midten",  "SVAKT",    "bear", "Goldilocks – svak USD, risikoappetitt god"
else:
    smile_pos, usd_bias, usd_color, smile_desc = "hoyre",   "MODERAT",  "bull", "Vekst/inflasjon driver USD"

if vix > 30:
    vix_regime = {"value": vix, "label": "Ekstrem frykt – kvart størrelse",  "color": "bear", "regime": "extreme"}
elif vix > 20:
    vix_regime = {"value": vix, "label": "Forhøyet – halv størrelse",         "color": "warn", "regime": "elevated"}
else:
    vix_regime = {"value": vix, "label": "Normalt – full størrelse",           "color": "bull", "regime": "normal"}

macro = {
    "date":     datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "cot_date": "",
    "prices":   prices,
    "vix_regime": vix_regime,
    "dollar_smile": {
        "position":  smile_pos,
        "usd_bias":  usd_bias,
        "usd_color": usd_color,
        "desc":      smile_desc,
        "inputs": {
            "vix":          vix,
            "hy_stress":    hy_stress,
            "brent":        brent,
            "tip_trend_5d": tip_5d,
            "dxy_trend_5d": dxy_5d,
        },
    },
    "trading_levels": {},
    "calendar":       [],
}

# Bevar eksisterende data som fetch_all.py har beregnet (trading_levels, calendar, etc.)
try:
    with open(OUT) as f:
        existing = json.load(f)
    for key in ("trading_levels", "calendar", "cot_date", "macro_indicators",
                "vix_term_structure", "correlations", "session_ranges", "sentiment"):
        if existing.get(key):
            macro[key] = existing[key]
    # Bevar dollar_smile fra fetch_all.py helt uendret — VIX/DXY ikke tilgjengelig fra boten
    if existing.get("dollar_smile"):
        macro["dollar_smile"] = existing["dollar_smile"]
    # Bevar vix_regime hvis VIX ikke ble hentet nå
    if not prices.get("VIX") and existing.get("vix_regime"):
        macro["vix_regime"] = existing["vix_regime"]
except Exception:
    pass

with open(OUT, "w") as f:
    json.dump(macro, f, ensure_ascii=False, indent=2)
print(f"\nOK → {OUT}")
