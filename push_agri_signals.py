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
from datetime import datetime, timezone, timedelta

BASE = Path(__file__).parent
AGRI_FILE       = BASE / "data" / "agri" / "latest.json"
MACRO_FILE      = BASE / "data" / "macro" / "latest.json"
USDA_CAL_FILE   = BASE / "data" / "agri" / "usda_calendar.json"
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

# ATR14 som prosent av pris — kalibrert mot bot (H1 timeframe, ikke D1).
# Boten trader med ATR14 fra H1-candles, som typisk er ~1/7 av D1 ATR.
# Observerte ratios (live/est) ved D1-kalibrering: Corn 0.14, Soybean 0.11,
# Sugar 0.17 → ~7× for høyt. Disse verdiene matcher nå boten slik at
# SL/T1 på nettsiden reflekterer det boten faktisk trader med.
CROP_ATR_PCT = {
    "corn":       0.21,  # ~$0.96 på $458 (observert live)
    "wheat":      0.26,  # skalert fra D1 1.8% ÷ 7
    "soybeans":   0.15,  # ~$1.79 på $1179 (observert live)
    "canola":     0.21,
    "cotton":     0.29,
    "sugar":      0.38,  # ~$0.052 på $13.77 (observert live)
    "coffee":     0.36,
    "cocoa":      0.40,
}

# Minimum outlook-score for å generere signal
MIN_OUTLOOK_SCORE = 5.0

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

# Yahoo Finance fallback for agri-priser når bot-priser mangler
YAHOO_AGRI_MAP = {
    "corn": "ZC=F", "wheat": "ZW=F", "soybeans": "ZS=F",
    "cotton": "CT=F", "sugar": "SB=F", "coffee": "KC=F", "cocoa": "CC=F",
}
if not bot_prices:
    import urllib.request
    print("  Bot-priser mangler — prøver Yahoo Finance fallback for agri...")
    for crop_key, yahoo_sym in YAHOO_AGRI_MAP.items():
        if crop_key in bot_prices:
            continue
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}?interval=1d&range=5d"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            valid = [c for c in closes if c is not None]
            if valid:
                bot_prices[crop_key] = valid[-1]
                print(f"    {crop_key}: {valid[-1]} (Yahoo)")
        except Exception as e:
            print(f"    {crop_key}: Yahoo FEIL — {e}")

# Geo-status fra makro
sentiment  = macro.get("sentiment") or {}
news       = sentiment.get("news") or {}
headlines  = " ".join(h.get("headline", "") for h in news.get("key_drivers", []))
WAR_WORDS  = ("iran", "israel", "attack", "war", "strike", "sanction", "invasion", "escalat")
geo_active = any(w in headlines.lower() for w in WAR_WORDS)

# ── Valuta-penalty (DXY + BRL) ──────────────────────────────
# Sterkende dollar er motvind for råvarer (prises i USD)
# Svak BRL → Brasil dumper eksport → prispress ned for kaffe/sukker/soya
macro_prices = macro.get("prices", {})

dxy_chg5d = (macro_prices.get("DXY") or {}).get("chg5d", 0) or 0
# USDBRL: prøv fra macro_prices eller bot_prices
usdbrl_chg5d = (macro_prices.get("USDBRL") or macro_prices.get("BRL") or {}).get("chg5d", 0) or 0

BRL_CROPS = {"coffee", "sugar", "soybeans"}  # Avlinger påvirket av BRL


def currency_penalty(crop_key, direction):
    """Returnerer negativ penalty (trekkes fra score) basert på valutabevegelser.
    Kun for BUY — sterk dollar/svak BRL = motvind for long agri."""
    if direction != "BUY":
        return 0, []
    penalty = 0
    drivers = []
    # DXY-motstand: sterk dollar presser alle råvarer
    if dxy_chg5d > 3:
        penalty = -1.5
        drivers.append(f"DXY-motvind: dollar +{dxy_chg5d:.1f}% siste 5d")
    elif dxy_chg5d > 2:
        penalty = -1.0
        drivers.append(f"DXY-motvind: dollar +{dxy_chg5d:.1f}% siste 5d")
    # BRL-motvind: svak real → dumping-eksport fra Brasil
    if crop_key in BRL_CROPS and usdbrl_chg5d > 5:
        penalty -= 2.0
        drivers.append(f"BRL-krise: USDBRL +{usdbrl_chg5d:.1f}% — eksportdumping-risiko")
    elif crop_key in BRL_CROPS and usdbrl_chg5d > 3:
        penalty -= 1.0
        drivers.append(f"BRL-svak: USDBRL +{usdbrl_chg5d:.1f}% — eksportpress")
    return penalty, drivers


# ── USDA Event Blackout ──────────────────────────────────────
# Blokkerer agri-signaler ±3 timer fra kritiske USDA-rapporter
usda_blackout = {}   # instrument → {"report", "time_utc", "hours_away"}

def _load_usda_blackout():
    """Sjekker om noe instrument er i blackout-vindu nå."""
    if not USDA_CAL_FILE.exists():
        return
    try:
        with open(USDA_CAL_FILE) as f:
            cal = json.load(f)
    except Exception:
        return
    now = datetime.now(timezone.utc)
    blackout_h = cal.get("blackout_hours", 3)

    for report in cal.get("reports", []):
        affected = report.get("affected", [])
        report_type = report.get("type", "?")

        # Faste datoer
        for date_str in report.get("dates", []):
            try:
                ev_dt = datetime.fromisoformat(date_str)
                hours_away = (ev_dt - now).total_seconds() / 3600.0
                if -1 < hours_away < blackout_h:
                    for instr in affected:
                        usda_blackout[instr] = {
                            "report": report_type,
                            "time_utc": ev_dt.strftime("%Y-%m-%d %H:%M UTC"),
                            "hours_away": round(hours_away, 1),
                        }
            except Exception:
                continue

        # Recurring (Crop Progress mandager, Export Sales torsdager)
        rec = report.get("recurring")
        if rec:
            day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                       "friday": 4, "saturday": 5, "sunday": 6}
            target_day = day_map.get(rec.get("day", "").lower())
            if target_day is not None and now.month in rec.get("months", []):
                # Finn neste/forrige forekomst av denne ukedagen
                for delta in range(-1, 2):  # sjekk i går, i dag, i morgen
                    check = now + timedelta(days=delta)
                    if check.weekday() == target_day:
                        time_parts = rec.get("time_utc", "20:00").split(":")
                        ev_dt = check.replace(hour=int(time_parts[0]),
                                              minute=int(time_parts[1]) if len(time_parts) > 1 else 0,
                                              second=0, microsecond=0)
                        hours_away = (ev_dt - now).total_seconds() / 3600.0
                        if -1 < hours_away < blackout_h:
                            for instr in affected:
                                # Kun overstyr med høyere impact
                                if instr not in usda_blackout or report.get("impact") == "kritisk":
                                    usda_blackout[instr] = {
                                        "report": report_type,
                                        "time_utc": ev_dt.strftime("%Y-%m-%d %H:%M UTC"),
                                        "hours_away": round(hours_away, 1),
                                    }

_load_usda_blackout()
if usda_blackout:
    items = [f"{k} ({v['report']})" for k, v in usda_blackout.items()]
    print(f"  USDA BLACKOUT aktiv: {', '.join(items)}")


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


def calc_levels(price, direction, crop_key, instrument=None):
    """
    Beregner entry, SL, T1, T2 basert på ATR.

    Prioritet: live ATR fra macro/latest.json → estimert ATR fra CROP_ATR_PCT.
    BUY:  entry = pris - 0.3×ATR (pullback), SL = entry - 1.5×ATR, T1 = entry + 2×ATR
    SELL: entry = pris + 0.3×ATR (rally),   SL = entry + 1.5×ATR, T1 = entry - 2×ATR
    """
    # Prøv live ATR fra macro/latest.json (satt av fetch_all.py fra bot-priser)
    atr = None
    atr_source = "estimated"
    if instrument:
        live_atr = (macro_prices.get(instrument) or {}).get("atr_d1")
        if live_atr and live_atr > 0:
            atr = live_atr
            atr_source = "live"
    if atr is None:
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
        "entry":      entry,
        "sl":         sl,
        "t1":         t1,
        "t2":         t2,
        "rr_t1":      rr_t1,
        "rr_t2":      rr_t2,
        "atr_est":    round(atr, 2),
        "atr_source": atr_source,
        "sl_type":    "atr_prosent",
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
        p = macro_prices.get(instrument, {})
        price = p.get("price")
    if not price:
        continue

    # Må være i sesong for pålitelig signal
    if not crop.get("in_season", False):
        continue

    # USDA blackout-sjekk: ikke generer signal hvis rapport er nær
    if instrument in usda_blackout:
        bo = usda_blackout[instrument]
        print(f"  ⚠️  {instrument} BLACKOUT — {bo['report']} om {bo['hours_away']:.1f}t ({bo['time_utc']})")
        continue

    # Score
    scoring = score_crop(crop)
    if not scoring:
        continue

    # Valuta-penalty (DXY/BRL motvind)
    fx_penalty, fx_drivers = currency_penalty(crop_key, scoring["direction"])
    if fx_penalty:
        scoring["total"] = round(scoring["total"] + fx_penalty, 1)
        scoring["drivers"] = scoring["drivers"] + fx_drivers

    # Minimum score-filter
    if scoring["total"] < MIN_OUTLOOK_SCORE:
        continue

    # Beregn nivåer (bruk live ATR hvis tilgjengelig)
    levels = calc_levels(price, scoring["direction"], crop_key, instrument=instrument)

    # Timeframe basert på confidence — C-grade sendes ikke til boten
    if scoring["confidence"] == "A":
        timeframe = "MAKRO"
    elif scoring["confidence"] == "B":
        timeframe = "SWING"
    else:
        continue  # Grade C = ikke tradeable, hopp over

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
        "atr_source":     levels.get("atr_source", "estimated"),
        "cot_bias":       cot.get("bias"),
        "cot_pct":        cot.get("net_pct"),
        "cot_zscore":     cot.get("cot_zscore"),
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
        "geo_active":      geo_active,
        "vix_regime":      vix_regime,
        "usda_blackout":   usda_blackout if usda_blackout else None,
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

# Agri-signaler pushes nå via push_signals.py (merget inn i signals.json)
# Ingen separat Flask-push nødvendig
