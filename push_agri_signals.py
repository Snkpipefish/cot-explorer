#!/usr/bin/env python3
"""
push_agri_signals.py — Generer trading-setups fra avlingsdata

Leser data/agri/latest.json og genererer signaler basert på:
  - Outlook (vær + COT + yield)
  - Yield-stress (lav yield = bullish for pris)
  - ENSO-prognose (El Niño/La Niña effekter)
  - COT-posisjonering

Skriver: data/agri_signals.json  (samme format som signals.json)
Pusher til Flask signal_server hvis SCALP_API_KEY er satt.
"""

import os
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).parent
AGRI_FILE       = BASE / "data" / "agri" / "latest.json"
MACRO_FILE      = BASE / "data" / "macro" / "latest.json"
SIGNALS_OUT     = BASE / "data" / "agri_signals.json"
FLASK_URL       = os.environ.get("FLASK_URL", "http://localhost:5000")
SCALP_API_KEY   = os.environ.get("SCALP_API_KEY", "")

if not SCALP_API_KEY:
    bashrc = Path.home() / ".bashrc"
    if bashrc.exists():
        for line in bashrc.read_text().splitlines():
            if line.startswith("export SCALP_API_KEY="):
                SCALP_API_KEY = line.split("=", 1)[1].strip().strip("\"'")
                break

# ── Crop → cTrader instrumentnavn ────────────────────────
CROP_INSTRUMENT = {
    "corn":       "Corn",
    "wheat":      "Wheat",
    "soybeans":   "Soybean",
    "canola":     "Canola",     # Ikke tradeable i cTrader — kun info
    "cotton":     "Cotton",
    "sugar":      "Sugar",
    "coffee":     "Coffee",
    "cocoa":      "Cocoa",
    "palm_oil":   None,         # Ikke tilgjengelig
    "rice":       None,         # Ikke tilgjengelig
}

# Typisk daglig ATR som prosent av pris (brukes for entry/SL/T1-beregning)
# Basert på historisk volatilitet for agri-futures
CROP_ATR_PCT = {
    "corn":       1.5,   # ~$6-7 på $450
    "wheat":      1.8,   # ~$10 på $580
    "soybeans":   1.4,   # ~$15 på $1100
    "canola":     1.5,
    "cotton":     2.0,   # Høy vol
    "sugar":      2.2,   # Veldig volatil
    "coffee":     2.5,   # Svært volatil
    "cocoa":      2.8,   # Ekstremt volatil nå
}

# Minimum outlook-score for å generere signal
MIN_OUTLOOK_SCORE = 2.0

# ── Hent data ─────────────────────────────────────────────
if not AGRI_FILE.exists():
    print(f"FEIL: {AGRI_FILE} finnes ikke — kjør fetch_agri.py først")
    sys.exit(1)

with open(AGRI_FILE) as f:
    agri = json.load(f)

# Hent makrodata for VIX-regime og geo-status
macro = {}
if MACRO_FILE.exists():
    with open(MACRO_FILE) as f:
        macro = json.load(f)

vix_obj    = macro.get("vix_regime") or {}
vix_regime = vix_obj.get("regime", "normal")

# Hent bot-priser (mest oppdaterte agri-priser)
BOT_HISTORY = BASE / "data" / "prices" / "bot_history.json"
bot_prices = {}
if BOT_HISTORY.exists():
    try:
        with open(BOT_HISTORY) as f:
            bh = json.load(f)
        for k, v in bh.items():
            if isinstance(v, dict) and "price" in v:
                bot_prices[k.lower()] = v["price"]
            elif isinstance(v, list) and v:
                bot_prices[k.lower()] = v[-1].get("price")
    except Exception:
        pass

# Geo-status fra makro
sentiment  = macro.get("sentiment") or {}
news       = sentiment.get("news") or {}
headlines  = " ".join(h.get("headline", "") for h in news.get("key_drivers", []))
WAR_WORDS  = ("iran", "israel", "attack", "war", "strike", "sanction", "invasion", "escalat")
geo_active = any(w in headlines.lower() for w in WAR_WORDS)


# ── Score og generer setups ───────────────────────────────
def score_crop(crop):
    """
    Scorer en avling for tradingpotensial.
    Returnerer (total_score, direction, confidence, drivers).

    Score-komponenter:
      - outlook.total_score (±5) — fundamentalt signal
      - yield_stress (0-3)      — lav yield = prispress opp
      - enso_risk (0-2)         — El Niño/La Niña effekt
      - weather_urgency (0-2)   — akutt værstress
    """
    outlook = crop.get("outlook", {})
    signal  = outlook.get("signal", "NØYTRAL")
    o_score = outlook.get("total_score", 0)

    # Retning: outlook bestemmer
    if "BULLISH" in signal:
        direction = "BUY"
    elif "BEARISH" in signal:
        direction = "SELL"
    else:
        return None  # Ingen handel på nøytral

    # Yield-stress: lav yield → sterkt prispress opp
    yield_score = crop.get("yield_score")
    yield_stress = 0
    if yield_score is not None:
        if yield_score < 40:
            yield_stress = 3    # Kritisk
        elif yield_score < 55:
            yield_stress = 2    # Svak
        elif yield_score < 70:
            yield_stress = 1    # Middels

    # Vær-hastighet: akutt stress gir sterkere signal
    wx_score = crop.get("avg_wx_score", 0)
    weather_urgency = 0
    if wx_score >= 3:
        weather_urgency = 2     # Tørke/flom — akutt
    elif wx_score >= 2:
        weather_urgency = 1     # Forhøyet risiko

    # ENSO risiko
    enso_risk = 0
    worst = crop.get("worst_region", {})
    if worst.get("enso_adj", 0) > 0:
        enso_risk = 1
    if worst.get("enso_adj", 0) > 0.5:
        enso_risk = 2

    # Total
    total = abs(o_score) + yield_stress + weather_urgency + enso_risk

    # Retning-flip: SELL-signaler har negativ score
    if direction == "SELL":
        # For SELL: yield_stress er IKKE bullish, men outlook er bearish
        # Kun outlook + overflod teller
        if yield_score and yield_score > 85:
            total += 1  # Høy yield = bearish prispress

    # Confidence basert på score
    if total >= 7:
        confidence = "A"
    elif total >= 5:
        confidence = "B"
    else:
        confidence = "C"

    # Drivers-tekst
    drivers = crop.get("drivers", [])

    return {
        "total":         round(total, 1),
        "direction":     direction,
        "confidence":    confidence,
        "yield_stress":  yield_stress,
        "weather_urgency": weather_urgency,
        "enso_risk":     enso_risk,
        "outlook_score": o_score,
        "drivers":       drivers,
    }


def calc_levels(price, direction, crop_key):
    """
    Beregner entry, SL, T1, T2 basert på ATR-estimat.

    BUY:  entry = pris - 0.3×ATR (pullback), SL = entry - 1.5×ATR, T1 = entry + 2×ATR
    SELL: entry = pris + 0.3×ATR (rally),   SL = entry + 1.5×ATR, T1 = entry - 2×ATR
    """
    atr_pct = CROP_ATR_PCT.get(crop_key, 1.8)
    atr = price * atr_pct / 100

    if direction == "BUY":
        entry = round(price - 0.3 * atr, 2)
        sl    = round(entry - 1.5 * atr, 2)
        t1    = round(entry + 2.0 * atr, 2)
        t2    = round(entry + 3.0 * atr, 2)
    else:
        entry = round(price + 0.3 * atr, 2)
        sl    = round(entry + 1.5 * atr, 2)
        t1    = round(entry - 2.0 * atr, 2)
        t2    = round(entry - 3.0 * atr, 2)

    risk   = abs(entry - sl)
    rr_t1  = round(abs(t1 - entry) / risk, 2) if risk > 0 else 0
    rr_t2  = round(abs(t2 - entry) / risk, 2) if risk > 0 else 0

    return {
        "entry":   entry,
        "sl":      sl,
        "t1":      t1,
        "t2":      t2,
        "rr_t1":   rr_t1,
        "rr_t2":   rr_t2,
        "atr_est": round(atr, 2),
        "sl_type": "atr_prosent",
    }


# ── Generer signaler ─────────────────────────────────────
signals = []
now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

for crop in agri.get("crop_summary", []):
    crop_key   = crop.get("crop_key", "")
    instrument = CROP_INSTRUMENT.get(crop_key)
    if not instrument:
        continue  # Ikke tradeable

    # Trenger pris — sjekk 3 kilder
    price_data = crop.get("price") or {}
    price = price_data.get("value")
    if not price:
        # Bot-priser (mest oppdaterte)
        price = bot_prices.get(instrument.lower()) or bot_prices.get(crop_key)
    if not price:
        # Macro-priser (fallback)
        macro_prices = macro.get("prices", {})
        p = macro_prices.get(instrument, {})
        price = p.get("price")
    if not price:
        continue

    # Må være i sesong for pålitelig signal
    if not crop.get("in_season", False):
        continue

    # Score
    scoring = score_crop(crop)
    if not scoring:
        continue

    # Minimum score-filter
    if scoring["total"] < MIN_OUTLOOK_SCORE:
        continue

    # Beregn nivåer
    levels = calc_levels(price, scoring["direction"], crop_key)

    # Timeframe basert på confidence
    if scoring["confidence"] == "A":
        timeframe = "MAKRO"
    elif scoring["confidence"] == "B":
        timeframe = "SWING"
    else:
        timeframe = "WATCHLIST"

    # Bygg signal
    cot = crop.get("cot") or {}

    sig = {
        "key":            instrument,
        "name":           crop.get("navn", instrument),
        "action":         scoring["direction"],
        "timeframe":      timeframe,
        "grade":          scoring["confidence"],
        "score":          scoring["total"],
        "current":        price,
        "entry":          levels["entry"],
        "sl":             levels["sl"],
        "t1":             levels["t1"],
        "t2":             levels["t2"],
        "rr_t1":          levels["rr_t1"],
        "rr_t2":          levels["rr_t2"],
        "sl_type":        levels["sl_type"],
        "atr_est":        levels["atr_est"],
        "cot_bias":       cot.get("bias"),
        "cot_pct":        cot.get("net_pct"),
        "source":         "agri_fundamental",
        # Ekstra agri-spesifikk info
        "yield_score":    crop.get("yield_score"),
        "yield_quality":  crop.get("yield_quality"),
        "weather_outlook": crop.get("worst_region", {}).get("weather_outlook"),
        "growth_stage":   crop.get("growth_stage"),
        "season_pct":     crop.get("growth_stage_pct"),
        "drivers":        scoring["drivers"][:4],  # Topp 4 drivere
    }
    signals.append(sig)

# Sorter etter score (høyest først)
signals.sort(key=lambda s: s["score"], reverse=True)

# ── Skriv agri_signals.json ──────────────────────────────
output = {
    "generated":   now_ts,
    "cot_date":    agri.get("cot_date", ""),
    "enso_phase":  agri.get("enso", {}).get("phase", "?"),
    "global_state": {
        "geo_active":  geo_active,
        "vix_regime":  vix_regime,
    },
    "rules": {
        "risk_pct_full":    1.0,
        "risk_pct_half":    0.5,
        "risk_pct_quarter": 0.25,
        "min_rr":           1.33,
        "note": "Agri-signaler bruker fundamental analyse — ATR-nivåer er estimater. Boten bør bekrefte med live ATR.",
    },
    "signals": signals,
}

SIGNALS_OUT.parent.mkdir(parents=True, exist_ok=True)
with open(SIGNALS_OUT, "w") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"agri_signals.json → {len(signals)} signaler")
for s in signals:
    arrow = "▲" if s["action"] == "BUY" else "▼"
    print(f"  {s['grade']}  {s['name']:20s} {s['action']:4s} {arrow}  "
          f"score={s['score']:.1f}  entry={s['entry']}  SL={s['sl']}  "
          f"T1={s['t1']}  R:R={s['rr_t1']}  "
          f"yield={s.get('yield_score','?')}  vær={s.get('weather_outlook','?')}")

if not signals:
    print("Ingen agri-signaler generert (alle under minimum score)")

# ── Push til Flask ────────────────────────────────────────
import urllib.request
import urllib.error


def push_flask_agri(signals_data):
    if not SCALP_API_KEY:
        print("  (SCALP_API_KEY ikke satt — skipper Flask push)")
        return
    url = f"{FLASK_URL}/push-agri-alert"
    payload = json.dumps(signals_data).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "X-API-Key": SCALP_API_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"  Flask /push-agri-alert OK ({resp.status})")
    except urllib.error.URLError as e:
        print(f"  Flask /push-agri-alert FEIL: {e} (endpoint må legges til i signal_server.py)")


push_flask_agri(output)
