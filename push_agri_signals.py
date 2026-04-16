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

# Analog-matching (K-NN mot 15-år ERA5 vær-historikk)
try:
    import agri_analog
    _ANALOG_OK = True
except Exception as _exc:
    _ANALOG_OK = False
AGRI_FILE       = BASE / "data" / "agri" / "latest.json"
MACRO_FILE      = BASE / "data" / "macro" / "latest.json"
USDA_CAL_FILE   = BASE / "data" / "agri" / "usda_calendar.json"
CONAB_FILE      = BASE / "data" / "conab" / "latest.json"
UNICA_FILE      = BASE / "data" / "unica" / "latest.json"
SIGNALS_OUT     = BASE / "data" / "agri_signals.json"
FLASK_URL       = os.environ.get("FLASK_URL", "http://localhost:5000")
SCALP_API_KEY   = os.environ.get("SCALP_API_KEY", "")

# Max alder på Conab/UNICA-data før vi ignorerer dem (graceful degradation).
# Conab er månedlig → 45 dager er romslig. UNICA er halvmånedlig → 30 dager.
CONAB_STALE_DAYS = 45
UNICA_STALE_DAYS = 30

# Shock-terskel for Conab m/m-revisjon (prosentpoeng)
CONAB_SHOCK_THRESHOLD_LOW  = 1.0   # ≥1% m/m = shock=1
CONAB_SHOCK_THRESHOLD_HIGH = 2.5   # ≥2.5% m/m = shock=2

# crop_key → Conab data-nøkkel (None for crops uten Conab-dekning)
CONAB_KEYS = {
    "soybeans": "soja",
    "corn":     "milho",
    "cotton":   "algodao",
    "wheat":    "trigo",
    "coffee":   "cafe_total",   # Vi bruker total; arabica+conilon tilgjengelig hvis vi trenger split
    # sugar dekkes primært av UNICA, ikke Conab (Conab har egen cana-rapport vi ikke leser)
}

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


# ── Conab / UNICA — last med stale-gate og graceful degradation ──────────────
def _safe_load_json(path: Path, stale_days: int) -> dict | None:
    """Last JSON hvis fila finnes og ikke er eldre enn stale_days.
    Returnerer None ved manglende/korrupt/stale data — kalleren skal
    tolerere None ved å hoppe over relevant scoring."""
    if not path.exists():
        return None
    try:
        age_s = (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime)
        if age_s > stale_days * 86400:
            print(f"  {path.name}: stale ({age_s/86400:.1f}d > {stale_days}d) — ignorert")
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"  {path.name}: kunne ikke laste ({exc}) — ignorert")
        return None


conab_data = _safe_load_json(CONAB_FILE, CONAB_STALE_DAYS)
unica_data = _safe_load_json(UNICA_FILE, UNICA_STALE_DAYS)
if conab_data:
    _n = len(conab_data.get("crops", {}))
    print(f"  Conab lastet: {_n} crops, lev={conab_data.get('grains_levantamento')}")
if unica_data:
    print(f"  UNICA lastet: {unica_data.get('period')} "
          f"mix_sukker={unica_data.get('mix_sugar_pct')}%")

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


# ── Conab shock: m/m-revisjon av avlings-estimat ─────────
def _conab_shock(crop_key: str, direction: str) -> tuple[int, list[str]]:
    """Returner (shock_score, driver_text_list) basert på Conab m/m-change.

    Retning:
      - Produksjon-revisjon NED  (mom < 0) → BULLISH for pris  → BUY får +score
      - Produksjon-revisjon OPP  (mom > 0) → BEARISH for pris  → SELL får +score
    Shock-nivå:
      - 0  : ingen revisjon eller < ±1%
      - 1  : 1–2.5% revisjon
      - 2  : ≥ 2.5% revisjon (kritisk)
    Hvis Conab-data mangler eller crop ikke dekkes: (0, []).
    """
    if not conab_data:
        return 0, []
    conab_key = CONAB_KEYS.get(crop_key)
    if not conab_key:
        return 0, []
    crop_data = (conab_data.get("crops") or {}).get(conab_key)
    if not crop_data:
        return 0, []
    mom = crop_data.get("mom_change_pct")
    if mom is None:
        return 0, []
    abs_mom = abs(mom)
    # Retnings-filter: revisjon ned = bull; revisjon opp = bear
    revision_bull = mom < 0
    if direction == "BUY" and not revision_bull:
        return 0, []
    if direction == "SELL" and revision_bull:
        return 0, []
    if abs_mom < CONAB_SHOCK_THRESHOLD_LOW:
        return 0, []
    score = 2 if abs_mom >= CONAB_SHOCK_THRESHOLD_HIGH else 1
    lev = conab_data.get("grains_levantamento") or conab_data.get("cafe_levantamento") or "?"
    arrow = "↓" if revision_bull else "↑"
    txt = f"Conab {lev}: {conab_key} {arrow}{abs_mom:.1f}% m/m ({'bull' if revision_bull else 'bear'})"
    return score, [txt]


# ── UNICA sugar-mix driver (kun for sugar) ────────────────
def _unica_mix_driver(direction: str) -> tuple[int, list[str]]:
    """Returner (score, driver_text_list) basert på UNICA sukker/etanol-mix.

    Logikk:
      - mix_sugar_pct > 50 AND QoQ-økning ≥ +1pp → bearish sukker (+SELL)
      - mix_sugar_pct < 48 AND QoQ-nedgang ≤ -1pp → bullish sukker (+BUY)
      - Crush akkumulativ YoY ≤ -5% → +1 bull (supply-press)
      - Crush akkumulativ YoY ≥ +5% → +1 bear (supply-rikelig)
    Uten data eller ingen retningsmatch: (0, []).
    """
    if not unica_data:
        return 0, []
    score = 0
    drivers = []
    mix = unica_data.get("mix_sugar_pct")
    mix_qoq = unica_data.get("mix_sugar_change_pct_qoq")
    if mix is not None and mix_qoq is not None:
        if mix > 50 and mix_qoq >= 1.0 and direction == "SELL":
            score += 1
            drivers.append(f"UNICA: mix sukker {mix:.1f}% (+{mix_qoq:.1f}pp) → prispress ned")
        elif mix < 48 and mix_qoq <= -1.0 and direction == "BUY":
            score += 1
            drivers.append(f"UNICA: mix sukker {mix:.1f}% ({mix_qoq:+.1f}pp) → tight supply")
    yoy = unica_data.get("crush_accumulated_yoy_pct")
    if yoy is not None:
        if yoy <= -5.0 and direction == "BUY":
            score += 1
            drivers.append(f"UNICA: crush YoY {yoy:.1f}% → supply-press")
        elif yoy >= 5.0 and direction == "SELL":
            score += 1
            drivers.append(f"UNICA: crush YoY +{yoy:.1f}% → supply rikelig")
    return score, drivers


# ── Krysssjekk mellom kilder (Open-Meteo + Conab + UNICA + ENSO) ──────────
def _cross_confirm(crop: dict, crop_key: str, direction: str) -> tuple[int, list[str]]:
    """Ekstra poeng når to uavhengige kilder peker samme vei.
    Graceful: returnerer (0, []) hvis noen av kildene mangler.

    Bekreftelses-typer (max +2 totalt):

    A. YIELD-CROSS (grains + café):
       Open-Meteo yield_score < 55  AND  Conab yoy_change_pct < -3
       → feltbasert avlingsnedgang bekreftes av agrometeorologisk stress
       → +1 for BUY-retning (tight supply)

    B. CRUSH-CROSS (kun sugar):
       UNICA crush YoY < -3  AND  agri-region wx_score >= 2
       → mindre crush enn ifjor + akutt værstress i sukkerregion
       → +1 for BUY-retning (supply press fortsetter)

    C. STRUCTURAL-TREND (grains + café):
       Conab yoy_change_pct >= +10  OR  <= -10
       → strukturell supply-endring på 10%+ vs forrige safra-år
       → +1 for SELL hvis YoY >= +10 (overflod), +1 for BUY hvis <= -10 (knapphet)
       NB: dette er strukturelt, ikke shock. Lavere vekt enn shock-signaler.
    """
    score = 0
    drivers = []

    # A. YIELD-CROSS — Open-Meteo yield_score + Conab YoY
    conab_key = CONAB_KEYS.get(crop_key or "")
    conab_crop = None
    if conab_data and conab_key:
        conab_crop = (conab_data.get("crops") or {}).get(conab_key)
    yield_score = crop.get("yield_score")
    if (conab_crop is not None
            and yield_score is not None
            and direction == "BUY"):
        conab_yoy = conab_crop.get("yoy_change_pct")
        if (conab_yoy is not None
                and yield_score < 55
                and conab_yoy < -3):
            score += 1
            drivers.append(
                f"Krysssjekk: yield_score {yield_score} + Conab YoY "
                f"{conab_yoy:+.1f}% → supply-stress bekreftet"
            )

    # B. CRUSH-CROSS — UNICA crush YoY + akutt vær i sukker-region
    if (crop_key == "sugar"
            and unica_data
            and direction == "BUY"):
        crush_yoy = unica_data.get("crush_accumulated_yoy_pct")
        wx_score = crop.get("avg_wx_score", 0) or 0
        if (crush_yoy is not None
                and crush_yoy < -3
                and wx_score >= 2):
            score += 1
            drivers.append(
                f"Krysssjekk: UNICA crush {crush_yoy:+.1f}% YoY + vær-stress "
                f"(wx_score={wx_score}) → supply-press fortsetter"
            )

    # C. STRUCTURAL-TREND — Conab YoY som strukturell bias (ikke shock)
    #    Dette er vekst/nedgang vs forrige safra-år — priset inn av markedet,
    #    men styrker multi-måneders retningsbias for MAKRO-horisont.
    if conab_crop is not None:
        conab_yoy = conab_crop.get("yoy_change_pct")
        if conab_yoy is not None:
            if conab_yoy >= 10 and direction == "SELL":
                score += 1
                drivers.append(
                    f"Struktur: Conab YoY +{conab_yoy:.1f}% "
                    f"({conab_key}) → overflod vs forrige safra"
                )
            elif conab_yoy <= -10 and direction == "BUY":
                score += 1
                drivers.append(
                    f"Struktur: Conab YoY {conab_yoy:.1f}% "
                    f"({conab_key}) → knapphet vs forrige safra"
                )

    # D. ANALOG-ÅR — K-NN mot 15-år ERA5 vær-historikk
    #    Hvis historiske analog-år med ligende vær-mønster ga prispress i
    #    retning av signalet → bekreftelse. Kappet til 1 poeng per signal.
    if _ANALOG_OK:
        try:
            analog_score, analog_drivers = agri_analog.analog_direction_score(
                crop_key, direction,
                current_month=datetime.now().month,
            )
            if analog_score >= 0.15:
                # Skala analog-score til cross_confirm. 1.0 analog = full 1.0 bidrag.
                score += round(analog_score, 2)
                drivers += analog_drivers
        except Exception:
            pass   # Graceful degradation

    # Cap bonus til +2 slik at krysssjekk ikke dominerer over shock-drivere
    if score > 2:
        score = 2
        drivers = drivers[:3]   # Beholde topp-3 inkl. analog

    return score, drivers


# ── Score og generer setups ───────────────────────────────
def score_crop(crop, crop_key: str | None = None):
    """
    Scorer en avling for tradingpotensial.
    Returnerer (total_score, direction, confidence, drivers).

    Score-komponenter:
      - outlook.total_score (±5) — fundamentalt signal
      - yield_stress (0-3)      — lav yield = prispress opp
      - enso_risk (0-2)         — El Niño/La Niña effekt
      - weather_urgency (0-2)   — akutt værstress
      - conab_shock (0-2)       — Conab m/m-revisjon (hvis crop_key dekkes)
      - unica_mix (0-2)         — UNICA sugar-mix / crush YoY (kun crop_key=sugar)
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

    # Conab shock-komponent (m/m-revisjon i Brasil-estimat)
    conab_score, conab_drivers_txt = _conab_shock(crop_key or "", direction)
    total += conab_score

    # UNICA mix-driver (kun sugar)
    unica_score, unica_drivers_txt = ((0, []) if crop_key != "sugar"
                                      else _unica_mix_driver(direction))
    total += unica_score

    # Krysssjekk mellom kilder (graceful hvis data mangler)
    cross_score, cross_drivers_txt = _cross_confirm(crop, crop_key or "", direction)
    total += cross_score

    # Confidence basert på score
    if total >= 7:
        confidence = "A"
    elif total >= 5:
        confidence = "B"
    else:
        confidence = "C"

    # Drivers-tekst — Conab/UNICA/krysssjekk først (mest informativt), deretter
    # crop drivers. Boten og UI trunkerer til topp-N — prioritet = synlighet.
    drivers = (list(conab_drivers_txt)
               + list(unica_drivers_txt)
               + list(cross_drivers_txt))
    drivers += crop.get("drivers", [])

    return {
        "total":         round(total, 1),
        "direction":     direction,
        "confidence":    confidence,
        "yield_stress":  yield_stress,
        "weather_urgency": weather_urgency,
        "enso_risk":     enso_risk,
        "conab_shock":   conab_score,
        "unica_mix":     unica_score,
        "cross_confirm": cross_score,
        "outlook_score": o_score,
        "drivers":       drivers,
    }


# ─── Strukturell nivå-detektering for agri ───────────────────────────────
# Leser 15-års ukentlig close-historikk fra data/prices/{crop}.json og
# utleder swing high/low + round-numbers som reelle nivåer. Erstatter
# mekanisk ATR-T1 der vi finner struktur innen rimelig avstand.

_CROP_TO_PRICE_FILE = {
    "corn":     "corn.json",
    "wheat":    "wheat.json",
    "soybeans": "soybean.json",
    "sugar":    "sugar.json",
    "coffee":    "coffee.json",
    "cocoa":    "cocoa.json",
    # cotton: ikke i build_price_history — fallback til ATR
}

# Round-number-skritt per crop (for psykologiske nivåer)
_CROP_ROUND_STEP = {
    "corn":      10.0,    # ~2% av pris
    "wheat":     10.0,
    "soybeans":  25.0,    # pris ~1100-1400
    "sugar":     0.5,     # pris ~15-25
    "coffee":    10.0,    # pris ~200-350
    "cocoa":     250.0,   # pris ~3000-11000
    "cotton":    2.0,
}


def _load_crop_history(crop_key: str) -> list[float]:
    """Returnerer liste av close-priser (eldst først) eller tom liste."""
    fname = _CROP_TO_PRICE_FILE.get(crop_key)
    if not fname:
        return []
    p = BASE / "data" / "prices" / fname
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return [e["price"] for e in d.get("data", []) if "price" in e]
    except Exception:
        return []


def _extract_agri_levels(crop_key: str, current_price: float) -> tuple[list, list]:
    """Utled reelle støtte/motstand-nivåer fra ukentlig close-historikk.

    Nivå-typer og vekter:
      w5 — 52-ukers high/low (sterkest strukturelt, årlig/swing)
      w4 — 26-ukers high/low (halvår)
      w3 — 12-ukers high/low (kvartal)
      w2 — 4-ukers high/low  (måned)
      w1 — round-numbers innen ±15% av nåpris (psykologiske)

    Returnerer (supports, resistances) sortert etter nærmest entry først.
    Hver entry: {"price": float, "weight": int, "source": str}.
    """
    history = _load_crop_history(crop_key)
    if len(history) < 52:
        return [], []

    levels: list[dict] = []

    # Swing high/low over ulike vinduer
    for weeks, weight, label in [
        (4,  2, "4w"),
        (12, 3, "12w"),
        (26, 4, "26w"),
        (52, 5, "52w"),
    ]:
        window = history[-weeks:] if len(history) >= weeks else history
        hi = max(window)
        lo = min(window)
        # Unngå duplikater (f.eks. 4w high == 12w high)
        def _add_if_new(price: float, src: str):
            for ex in levels:
                if abs(ex["price"] - price) / current_price < 0.003:  # <0.3% = samme nivå
                    # Behold høyeste weight
                    if weight > ex["weight"]:
                        ex["weight"] = weight
                        ex["source"] = src
                    return
            levels.append({"price": price, "weight": weight, "source": src})
        _add_if_new(hi, f"{label}_high")
        _add_if_new(lo, f"{label}_low")

    # Round numbers innen ±15% av nåpris
    step = _CROP_ROUND_STEP.get(crop_key, current_price * 0.02)
    lo_bound = current_price * 0.85
    hi_bound = current_price * 1.15
    n_start = int(lo_bound / step)
    n_end   = int(hi_bound / step) + 1
    for n in range(n_start, n_end + 1):
        rn = round(n * step, 2)
        if lo_bound <= rn <= hi_bound:
            # Samme dedup-logikk
            duplicate = False
            for ex in levels:
                if abs(ex["price"] - rn) / current_price < 0.003:
                    duplicate = True
                    break
            if not duplicate:
                levels.append({"price": rn, "weight": 1, "source": f"rn{rn:g}"})

    # Del i supports (under) og resistances (over)
    supports = [l for l in levels if l["price"] < current_price]
    resistances = [l for l in levels if l["price"] > current_price]

    # Sorter: nærmest current først
    supports.sort(key=lambda l: current_price - l["price"])
    resistances.sort(key=lambda l: l["price"] - current_price)
    return supports, resistances


def _best_agri_t1(levels: list[dict], entry: float, risk: float,
                  direction: str, max_dist: float,
                  min_rr: float = 1.5) -> dict | None:
    """R:R-tier-prioritert T1-valg for agri — speiler make_setup_l2l.best_t1.

    Sortering: høyere R:R-tier først, så høyere weight, så kortere avstand.
    Tier: 2 hvis R:R ≥ 2.0, 1 hvis R:R ≥ 1.5, 0 ellers.
    """
    is_buy = direction == "BUY"
    min_t1_dist = risk * min_rr
    valid = []
    for l in levels:
        p = l["price"]
        dist = (p - entry) if is_buy else (entry - p)
        if dist < min_t1_dist:
            continue
        if dist > max_dist:
            continue
        valid.append((l, dist))
    if not valid:
        return None

    def _tier(dist: float) -> int:
        if risk <= 0:
            return 0
        rr = dist / risk
        if rr >= 2.0:
            return 2
        if rr >= 1.5:
            return 1
        return 0

    valid.sort(key=lambda x: (-_tier(x[1]), -x[0]["weight"], x[1]))
    l, d = valid[0]
    return dict(l, distance=d, rr=round(d / risk, 2) if risk > 0 else 0)


def calc_levels(price, direction, crop_key, instrument=None):
    """
    Beregner entry, SL, T1, T2.

    Prioritet:
      1. Entry + SL = ATR-basert (som før — struktur for SL krever intraday data)
      2. T1/T2 = reelle swing-nivåer + round numbers hvis innen rekkevidde
      3. Fallback: mekanisk 2.5×ATR hvis ingen reelle nivåer nær

    ATR-kilde: live ATR fra macro/latest.json → estimert ATR fra CROP_ATR_PCT.
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

    # Entry + SL: ATR-basert (struktur for SL krever intraday — ikke tilgjengelig)
    if direction == "BUY":
        entry = round(price - 0.3 * atr, 2)
        sl    = round(entry - 1.5 * atr, 2)
    else:
        entry = round(price + 0.3 * atr, 2)
        sl    = round(entry + 1.5 * atr, 2)

    risk = abs(entry - sl)

    # T1/T2: reelle nivåer hvis innen rekkevidde, ellers mekanisk ATR-fallback.
    # Agri har lav ATR men store swing-nivåer; bruk max(ATR-multipler, %-cap)
    # slik at vi når reelle nivåer (4w/12w/52w high-low + round numbers).
    max_t1_dist = max(5.0 * atr, price * 0.06)    # 6% av pris for SWING-agri
    max_t2_dist = max(8.0 * atr, price * 0.10)    # 10% av pris
    supports, resistances = _extract_agri_levels(crop_key, price)
    t1_levels = resistances if direction == "BUY" else supports

    t1_obj = _best_agri_t1(t1_levels, entry, risk, direction, max_t1_dist)
    t1_source = "atr_fallback"
    if t1_obj is not None:
        t1 = round(t1_obj["price"], 2)
        t1_source = t1_obj["source"]
    else:
        # Fallback: mekanisk 2.5×ATR (R:R 1.67)
        if direction == "BUY":
            t1 = round(entry + 2.5 * atr, 2)
        else:
            t1 = round(entry - 2.5 * atr, 2)

    # T2: neste reelle nivå etter T1, ellers ATR-fallback
    t2_levels = [l for l in t1_levels if (
        (direction == "BUY" and l["price"] > t1) or
        (direction == "SELL" and l["price"] < t1)
    )]
    # Sorter nærmest entry først
    t2_levels.sort(key=lambda l: abs(l["price"] - entry))
    t2_obj = None
    for l in t2_levels:
        d = abs(l["price"] - entry)
        if d <= max_t2_dist:
            t2_obj = l
            break
    if t2_obj is not None:
        t2 = round(t2_obj["price"], 2)
    else:
        if direction == "BUY":
            t2 = round(entry + 3.5 * atr, 2)
        else:
            t2 = round(entry - 3.5 * atr, 2)

    rr_t1 = round(abs(t1 - entry) / risk, 2) if risk > 0 else 0
    rr_t2 = round(abs(t2 - entry) / risk, 2) if risk > 0 else 0

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
        "t1_source":  t1_source,       # "52w_high" / "rn475.0" / "atr_fallback" etc.
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
    scoring = score_crop(crop, crop_key=crop_key)
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

    # ── Schema 2.0: bygg families-dict fra agri-scoring-komponenter ──
    # Agri har sin egen domene-scoring (outlook+yield+weather+enso+conab+unica)
    # som mapper naturlig til 5 av 6 families (ingen strukturell pris-trend).
    _agri_direction_bull = scoring["direction"] in ("BUY", "bull", "buy", "long")
    _fam_trend = {
        # Trend-proxy fra outlook-signal (BULLISH/BEARISH fra fetch_agri)
        "score":   1.0 if _agri_direction_bull else (0.5 if scoring["outlook_score"] > 0 else 0.0),
        "weight":  0.8,   # trend vektes lavere for agri-fundamentals
        "drivers": []
    }
    _fam_pos = {
        "score":   1.0 if cot.get("bias") and (
                       (cot["bias"] == "LONG" and _agri_direction_bull) or
                       (cot["bias"] == "SHORT" and not _agri_direction_bull)) else 0.0,
        "weight":  1.0,
        "drivers": [f"COT {cot.get('bias','?')} {cot.get('net_pct','?')}%"] if cot.get("bias") else []
    }
    _fam_macro = {
        "score":   min(abs(fx_penalty) / 2.0, 1.0) if fx_penalty else 0.0,
        "weight":  1.0,
        "drivers": fx_drivers
    }
    _fam_fund = {
        # Yield-stress + weather + enso + conab/unica samlet
        "score":   min((scoring.get("yield_stress", 0) / 3.0
                        + scoring.get("weather_urgency", 0) / 2.0
                        + scoring.get("enso_risk", 0) / 2.0
                        + scoring.get("conab_shock", 0) / 2.0
                        + scoring.get("unica_mix", 0) / 2.0
                        + scoring.get("cross_confirm", 0) / 2.0) / 6.0 * 1.5, 1.0),
        "weight":  1.3,
        "drivers": scoring.get("drivers", [])[:3]
    }
    _fam_risk = {
        "score":   0.5 if instrument in usda_blackout else 0.0,
        "weight":  1.0,
        "drivers": [f"USDA {usda_blackout[instrument].get('report')}"] if instrument in usda_blackout else []
    }
    _fam_struct = {"score": 0.0, "weight": 0.5, "drivers": []}   # N/A for agri-fundamental

    _families_dict = {
        "trend":       _fam_trend,
        "positioning": _fam_pos,
        "macro":       _fam_macro,
        "fundamental": _fam_fund,
        "risk":        _fam_risk,
        "structure":   _fam_struct,
    }
    _active_families = sum(1 for f in _families_dict.values() if f["score"] >= 0.3)
    # Normalisert score 0-6 (for schema 2.0-kompat)
    _score_06 = round(sum(f["score"] * f["weight"] for fk, f in _families_dict.items() if fk != "risk"), 2)

    sig = {
        "key":            instrument,
        "name":           crop.get("navn", instrument),
        "action":         scoring["direction"],
        "timeframe":      timeframe,
        "grade":          scoring["confidence"],
        "score":          scoring["total"],   # Behold gammel score for agri-intern bruk
        "current":        price,
        "entry":          levels["entry"],
        "sl":             levels["sl"],
        "t1":             levels["t1"],
        "t2":             levels["t2"],
        "rr_t1":          levels["rr_t1"],
        "rr_t2":          levels["rr_t2"],
        "sl_type":        levels["sl_type"],
        "t1_source":      levels.get("t1_source", "atr_fallback"),
        "atr_est":        levels["atr_est"],
        # Schema 2.0-felt
        "families":        _families_dict,
        "active_families": _active_families,
        "family_drivers":  scoring.get("drivers", [])[:8],
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
