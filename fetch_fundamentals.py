#!/usr/bin/env python3
"""
fetch_fundamentals.py — Henter fundamental makrodata fra FRED og scorer ±2 per indikator.
Lagrer til data/fundamentals/latest.json.

Kategorier (EdgeFinder-stil):
  - Economic Growth: GDP QoQ, Retail Sales MoM, UoM Consumer Confidence
  - Inflation:       CPI YoY, PPI YoY, PCE YoY, Fed Funds Rate
  - Jobs Market:     NFP, Unemployment Rate, Initial Claims, ADP, JOLTS

PMI hentes utelukkende fra ForexFactory-kalenderen (ISM-serier er ikke
tilgjengelige som FRED-serie; de må kjøpes direkte fra ISM).

Vekting for høy-sannsynlighets-setups:
  - Innenfor kategori: vektes per indikator (NFP/Claims/CPI/PCE veier tyngst)
  - Mellom kategorier: inflation 0.40 · jobs 0.35 · growth 0.25 (for FX/metaller)
  - Konsensus-multiplikator: ×1.4 når inflasjon+jobs peker SAMME vei,
    ×0.7 når de peker MOT hverandre → demper mixet signal
"""
import urllib.request, json, os, time
from datetime import datetime, timezone

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
if not FRED_API_KEY:
    print("FEIL: FRED_API_KEY ikke satt. Legg til i ~/.bashrc: export FRED_API_KEY='din_nøkkel'")
    print("Gratis nøkkel: https://fred.stlouisfed.org/docs/api/api_key.html")
    import sys; sys.exit(1)

def _load_previous_output():
    """Last forrige kjøring som fallback ved FRED-feil."""
    try:
        if os.path.exists(OUT):
            with open(OUT) as f:
                return json.load(f)
    except Exception:
        pass
    return None
BASE = os.path.expanduser("~/cot-explorer/data")
OUT  = os.path.join(BASE, "fundamentals", "latest.json")
os.makedirs(os.path.join(BASE, "fundamentals"), exist_ok=True)

# ── FRED-serier ───────────────────────────────────────────────────────────────
# Merk: NAPM og NMFCI (ISM PMI) gir 400-feil — ISM selger dataene, de er ikke
# gratis på FRED. PMI håndteres i try_calendar_pmi() under.
# ADPMNUSNERNSA er allerede en månedlig ENDRINGSSERIE (ikke nivåserie),
# så type = "level" — ikke "mom_abs" (som ville gitt andre derivat).

FRED_SERIES = {
    # Economic Growth & Consumer Strength
    "GDP":     {"id": "A191RL1Q225SBEA", "type": "level",   "label": "GDP Growth QoQ (%)"},
    "Retail":  {"id": "RSAFS",           "type": "mom",     "label": "Retail Sales MoM (%)"},
    "ConConf": {"id": "UMCSENT",         "type": "level",   "label": "UoM Consumer Sentiment"},
    # Inflation
    "CPI":     {"id": "CPIAUCSL",        "type": "yoy",     "label": "CPI YoY (%)"},
    "PPI":     {"id": "PPIACO",          "type": "yoy",     "label": "PPI YoY (%)"},
    "PCE":     {"id": "PCEPI",           "type": "yoy",     "label": "PCE YoY (%)"},
    "IntRate": {"id": "FEDFUNDS",        "type": "level",   "label": "Fed Funds Rate (%)"},
    # Jobs Market
    "NFP":     {"id": "PAYEMS",          "type": "mom_abs", "label": "NFP Endring (k)"},
    "Unemp":   {"id": "UNRATE",          "type": "level",   "label": "Arbeidsledighet (%)"},
    "Claims":  {"id": "ICSA",            "type": "level",   "label": "Init. Krav (k)"},
    # ADP: allerede en endringsserie → type="level" (raw = månedlig endring i tusen)
    "ADP":     {"id": "ADPMNUSNERNSA",   "type": "level",   "label": "ADP Endring (k)"},
    "JOLTS":   {"id": "JTSJOL",          "type": "level",   "label": "JOLTS Stillinger (k)"},
}

# Vekter per indikator (innenfor kategori) — høyere = viktigere markedsbeveger
INDICATOR_WEIGHTS = {
    # Growth (sum = 4)
    "GDP":     1.0,
    "mPMI":    2.0,   # fra kalender
    "sPMI":    2.0,   # fra kalender
    "Retail":  1.5,
    "ConConf": 1.5,
    # Inflation (sum = 6.5)
    "CPI":     2.0,
    "PPI":     1.0,
    "PCE":     2.0,
    "IntRate": 1.5,
    # Jobs (sum = 7)
    "NFP":     2.0,
    "Unemp":   1.5,
    "Claims":  1.5,
    "ADP":     1.0,
    "JOLTS":   1.0,
}

CATEGORIES = {
    "econ_growth": ["GDP", "mPMI", "sPMI", "Retail", "ConConf"],
    "inflation":   ["CPI", "PPI", "PCE", "IntRate"],
    "jobs":        ["NFP", "Unemp", "Claims", "ADP", "JOLTS"],
}

# Kategori-vekter per instrumenttype
CAT_WEIGHTS_FX = {"econ_growth": 0.25, "inflation": 0.40, "jobs": 0.35}
CAT_WEIGHTS_EQ = {"econ_growth": 0.50, "inflation": 0.10, "jobs": 0.40}  # aksjer/råolje

INSTRUMENT_USD_DIR = {
    "EURUSD": -1, "GBPUSD": -1, "AUDUSD": -1,
    "USDJPY": +1, "DXY":    +1,
    "Gold":   -1, "Silver": -1,
    "SPX":    +1, "NAS100": +1,
    "Brent":  +1, "WTI":    +1,
}

EQ_INSTRUMENTS = {"SPX", "NAS100", "Brent", "WTI"}

# ── FRED-henting ──────────────────────────────────────────────────────────────
def fetch_fred_api(series_id, limit=16, retries=2):
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={FRED_API_KEY}"
           f"&file_type=json&sort_order=desc&limit={limit}")
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as r:
                d = json.loads(r.read())
            obs = []
            for o in d.get("observations", []):
                if o.get("value") not in (".", "", None):
                    try:
                        obs.append((o["date"], float(o["value"])))
                    except (ValueError, KeyError):
                        pass
            return list(reversed(obs))
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"  FRED {series_id} FEIL (etter {retries+1} forsøk): {e}")
            return []

# ── Scoring per indikator ─────────────────────────────────────────────────────
def score_indicator(key, current, previous):
    """
    Returnerer -2..+2 som USD-bullish/bearish styrke.
    Positivt = USD bullish. Negativt = USD bearish.
    """
    if current is None:
        return 0

    # PMI (fra kalender) — ekspansjon > 50, kontraksjon < 50
    if key in ("mPMI", "sPMI"):
        if current > 56:   s = 2
        elif current > 52: s = 1
        elif current > 50: s = 0
        elif current > 47: s = -1
        else:              s = -2
        if previous is not None:
            delta = current - previous
            if delta > 2 and s < 2:    s += 1
            elif delta < -2 and s > -2: s -= 1
        return max(-2, min(2, s))

    # Inflasjon (CPI, PPI, PCE)
    # Høy/stigende = hawkish = USD bullish; lav/fallende = dovish = USD bearish
    if key in ("CPI", "PPI", "PCE"):
        if current > 4.5:   level_s = 2
        elif current > 2.5: level_s = 1
        elif current > 1.5: level_s = 0
        elif current > 0.5: level_s = -1
        else:               level_s = -2
        trend_s = 0
        if previous is not None:
            if current > previous + 0.2:   trend_s = 1
            elif current < previous - 0.2: trend_s = -1
        return max(-2, min(2, level_s + trend_s))

    # Rente: endring avgjørende (heving = hawkish; kutt = dovish)
    if key == "IntRate":
        if previous is None:
            return 1 if current >= 3.5 else 0
        delta = round(current - previous, 3)
        if delta > 0.1:    return 2   # aktiv heving
        elif delta > 0:    return 1   # marginalt opp
        elif delta == 0:   return 1 if current >= 4.0 else 0   # hold – høye renter = svakt USD-støtte
        elif delta > -0.1: return -1  # begynnende kutt
        else:              return -2  # aktivt kuttforløp

    # NFP — månedlig endring i tusen jobber (fra PAYEMS mom_abs)
    if key == "NFP":
        if current > 250:   s = 2
        elif current > 150: s = 1
        elif current > 50:  s = 0
        elif current > 0:   s = -1
        else:               s = -2
        if previous is not None and previous != 0:
            if current > 0 and previous > 0 and current > previous * 1.5 and s < 2:
                s += 1
            elif current < 0 and previous < 0 and s > -2:
                s -= 1
        return max(-2, min(2, s))

    # ADP — allerede månedlig endring i tusen (level-serie)
    if key == "ADP":
        # Normaliser: verdier > 5000 er sannsynligvis i antall personer, ikke tusen
        val = current / 1000 if abs(current) > 5000 else current
        if val > 250:   return 2
        elif val > 150: return 1
        elif val > 50:  return 0
        elif val > 0:   return -1
        else:           return -2

    # Arbeidsledighet — lavere = bedre for USD
    if key == "Unemp":
        if current < 3.5:   s = 2
        elif current < 4.0: s = 1
        elif current < 4.5: s = 0
        elif current < 5.0: s = -1
        else:               s = -2
        if previous is not None:
            if current < previous:   s = min(2,  s + 1)
            elif current > previous: s = max(-2, s - 1)
        return s

    # Initial Claims — lavere = bedre (FRED gir råtall; deler på 1000 internt)
    if key == "Claims":
        k = current / 1000
        if k < 200:   s = 2
        elif k < 225: s = 1
        elif k < 260: s = 0
        elif k < 300: s = -1
        else:         s = -2
        if previous is not None:
            pk = previous / 1000
            if k < pk:   s = min(2,  s + 1)
            elif k > pk: s = max(-2, s - 1)
        return s

    # JOLTS stillingsutlysninger (i tusen)
    if key == "JOLTS":
        if current > 9000:   return 2
        elif current > 7500: return 1
        elif current > 6000: return 0
        elif current > 4500: return -1
        else:                return -2

    # GDP QoQ % (annualisert)
    if key == "GDP":
        if current > 3.0:   return 2
        elif current > 1.5: return 1
        elif current > 0:   return 0
        elif current > -1:  return -1
        else:               return -2

    # Retail Sales MoM %
    if key == "Retail":
        if current > 1.0:    return 2
        elif current > 0.3:  return 1
        elif current > -0.3: return 0
        elif current > -0.8: return -1
        else:                return -2

    # Consumer Confidence (UoM 0–100; historisk gjennomsnitt ~70–80)
    if key == "ConConf":
        if current > 90:   s = 2
        elif current > 75: s = 1
        elif current > 65: s = 0
        elif current > 55: s = -1
        else:              s = -2
        if previous is not None:
            if current > previous:   s = min(2,  s + 1)
            elif current < previous: s = max(-2, s - 1)
        return max(-2, min(2, s))

    return 0

# ── Beregn indikator ──────────────────────────────────────────────────────────
def compute_indicator(key, cfg, obs):
    if not obs:
        return None
    t   = cfg["type"]
    date = obs[-1][0]
    raw_cur  = obs[-1][1]
    raw_prev = obs[-2][1] if len(obs) >= 2 else None

    if t == "level":
        current  = round(raw_cur, 3)
        previous = round(raw_prev, 3) if raw_prev is not None else None

    elif t == "yoy":
        if len(obs) < 13:
            return None
        current  = round((obs[-1][1] / obs[-13][1] - 1) * 100, 2)
        previous = round((obs[-2][1] / obs[-14][1] - 1) * 100, 2) if len(obs) >= 14 else None

    elif t == "mom":
        if len(obs) < 2:
            return None
        current  = round((obs[-1][1] / obs[-2][1] - 1) * 100, 2)
        previous = round((obs[-2][1] / obs[-3][1] - 1) * 100, 2) if len(obs) >= 3 else None

    elif t == "mom_abs":
        if len(obs) < 2:
            return None
        current  = round(obs[-1][1] - obs[-2][1], 1)
        previous = round(obs[-2][1] - obs[-3][1], 1) if len(obs) >= 3 else None

    else:
        current, previous = raw_cur, raw_prev

    score = score_indicator(key, current, previous)
    trend = ("opp" if current > previous else "ned" if current < previous else "flat") \
            if previous is not None else "ukjent"

    # Lesbare visningsverdier
    display_cur  = round(current  / 1000, 1) if key == "Claims" else current
    display_prev = round(previous / 1000, 1) if (key == "Claims" and previous is not None) else previous

    # ADP: normaliser store verdier til tusen
    if key == "ADP" and abs(current) > 5000:
        display_cur  = round(current  / 1000, 1)
        display_prev = round(previous / 1000, 1) if previous is not None else None

    return {
        "key":      key,
        "label":    cfg["label"],
        "current":  display_cur,
        "previous": display_prev,
        "date":     date,
        "score":    score,
        "trend":    trend,
    }

# ── PMI fra ForexFactory-kalenderen ──────────────────────────────────────────
def try_calendar_pmi():
    """
    Leter etter ISM Manufacturing og Services PMI-releaser med faktiske verdier
    i ForexFactory-kalenderen. Returnerer {key: {actual, forecast, score}}.
    """
    cal_path = os.path.join(BASE, "calendar", "latest.json")
    if not os.path.exists(cal_path):
        return {}
    try:
        with open(cal_path) as f:
            cal = json.load(f)
    except Exception:
        return {}

    pmi_map = {}
    for ev in cal.get("events", []):
        if ev.get("country") != "USD":
            continue
        title  = ev.get("title", "").lower()
        actual = ev.get("actual", "")
        if not actual:
            continue
        try:
            act_val = float(str(actual).replace("%", "").strip())
        except (ValueError, AttributeError):
            continue
        try:
            fore_val = float(str(ev.get("forecast", "")).replace("%", "").strip()) \
                       if ev.get("forecast") else None
        except (ValueError, AttributeError):
            fore_val = None
        try:
            prev_val = float(str(ev.get("previous", "")).replace("%", "").strip()) \
                       if ev.get("previous") else None
        except (ValueError, AttributeError):
            prev_val = None

        # Score: kombiner nivå og surprise
        base_score = score_indicator("mPMI", act_val, prev_val)
        if fore_val is not None:
            diff = act_val - fore_val
            surprise = 2 if diff > 1 else 1 if diff > 0 else -2 if diff < -1 else -1 if diff < 0 else 0
        else:
            surprise = 0
        final_score = max(-2, min(2, base_score + surprise))

        entry = {"actual": act_val, "forecast": fore_val, "previous": prev_val,
                 "surprise": surprise, "score": final_score}
        if "ism manufacturing" in title or ("manufacturing pmi" in title and "flash" not in title):
            pmi_map["mPMI"] = entry
        elif "ism services" in title or ("services pmi" in title and "flash" not in title) \
                or "non-manufacturing" in title:
            pmi_map["sPMI"] = entry

    return pmi_map

# ── Vektet kategori-gjennomsnitt ──────────────────────────────────────────────
def weighted_cat_avg(cat_keys, indicators):
    """Vektet gjennomsnitt av indikator-scorer innenfor en kategori."""
    total_score = 0.0
    total_w     = 0.0
    for k in cat_keys:
        if k in indicators:
            w = INDICATOR_WEIGHTS.get(k, 1.0)
            total_score += indicators[k]["score"] * w
            total_w     += w
    return round(total_score / total_w, 3) if total_w > 0 else 0.0

# ── Konsensus-multiplikator ───────────────────────────────────────────────────
def consensus_multiplier(cat_scores):
    """
    Beregner multiplikator basert på om inflasjon og arbeidsmarked peker
    i SAMME retning (forsterk signalet) eller MOT hverandre (demp).
    """
    THRESHOLD = 0.35
    infl_dir  = 1 if cat_scores.get("inflation",   0) >  THRESHOLD else \
               -1 if cat_scores.get("inflation",   0) < -THRESHOLD else 0
    jobs_dir  = 1 if cat_scores.get("jobs",        0) >  THRESHOLD else \
               -1 if cat_scores.get("jobs",        0) < -THRESHOLD else 0
    growth_dir= 1 if cat_scores.get("econ_growth", 0) >  THRESHOLD else \
               -1 if cat_scores.get("econ_growth", 0) < -THRESHOLD else 0

    # Tell kategori-retninger som har klar signal
    dirs = [d for d in [infl_dir, jobs_dir, growth_dir] if d != 0]

    if len(dirs) >= 2 and all(d == dirs[0] for d in dirs):
        return 1.5   # Alle klare kategorier peker SAMME vei
    elif len(dirs) == 2 and dirs[0] != dirs[1]:
        return 0.65  # To kategorier peker MOT hverandre
    elif len(dirs) == 1:
        return 1.0   # Bare én klar kategori
    else:
        return 0.5   # Ingen klar kategori-signal

# ══ HOVEDLOGIKK ══════════════════════════════════════════════════════════════
print("=== fetch_fundamentals.py ===")
print(f"FRED API-nøkkel: {'***' + FRED_API_KEY[-4:] if FRED_API_KEY else 'MANGLER'}")

indicators = {}

# 1. Hent FRED-data
for key, cfg in FRED_SERIES.items():
    print(f"  Henter {key} ({cfg['id']})...")
    limit  = 16 if cfg["type"] == "yoy" else 6
    obs    = fetch_fred_api(cfg["id"], limit=limit)
    result = compute_indicator(key, cfg, obs)
    if result:
        indicators[key] = result
        print(f"    → {result['current']} ({result['trend']:5s})  score={result['score']:+d}")
    else:
        print(f"    → FEIL eller for få datapunkter")
    time.sleep(0.15)

# Fallback: bruk forrige output hvis for få indikatorer ble hentet
if len(indicators) < 3:
    prev = _load_previous_output()
    if prev and prev.get("indicators"):
        print(f"  ADVARSEL: Kun {len(indicators)} indikatorer hentet — bruker forrige kjøring som fallback")
        for k, v in prev["indicators"].items():
            if k not in indicators:
                indicators[k] = v
                indicators[k]["_fallback"] = True
        print(f"  → {len(indicators)} indikatorer etter fallback")

# 2. Supplement PMI fra kalender
cal_pmi = try_calendar_pmi()
for k, pmi in cal_pmi.items():
    indicators[k] = {
        "key":      k,
        "label":    "ISM Manufacturing PMI" if k == "mPMI" else "ISM Services NMI",
        "current":  pmi["actual"],
        "previous": pmi.get("previous"),
        "forecast": pmi.get("forecast"),
        "surprise": pmi.get("surprise", 0),
        "score":    pmi["score"],
        "trend":    "ukjent",
        "kilde":    "kalender",
    }
    print(f"  Kalender {k}: actual={pmi['actual']}  forecast={pmi.get('forecast')}"
          f"  score={pmi['score']:+d}")

# 3. Beregn vektede kategori-gjennomsnitt
cat_avgs = {}
category_scores = {}
for cat, keys in CATEGORIES.items():
    avg   = weighted_cat_avg(keys, indicators)
    count = sum(1 for k in keys if k in indicators)
    cat_avgs[cat] = avg
    category_scores[cat] = {
        "score":    round(sum(indicators[k]["score"] for k in keys if k in indicators), 2),
        "avg":      avg,
        "count":    count,
        "bias":     "bullish" if avg >= 0.4 else "bearish" if avg <= -0.4 else "neutral",
        "keys":     keys,
    }

# 4. Konsensus-multiplikator
multiplier = consensus_multiplier(cat_avgs)

# 5. USD-samlet score (vektet, med konsensus)
usd_raw = (cat_avgs.get("econ_growth", 0) * CAT_WEIGHTS_FX["econ_growth"] +
           cat_avgs.get("inflation",   0) * CAT_WEIGHTS_FX["inflation"]   +
           cat_avgs.get("jobs",        0) * CAT_WEIGHTS_FX["jobs"])
usd_score = round(usd_raw * multiplier, 3)

if usd_score > 0.7:    usd_bias = "strong_bullish"
elif usd_score > 0.25: usd_bias = "bullish"
elif usd_score < -0.7: usd_bias = "strong_bearish"
elif usd_score < -0.25: usd_bias = "bearish"
else:                  usd_bias = "neutral"

# 6. Instrument-scorer
instrument_scores = {}
for inst_key, direction in INSTRUMENT_USD_DIR.items():
    if inst_key in EQ_INSTRUMENTS:
        cat_w = CAT_WEIGHTS_EQ
    else:
        cat_w = CAT_WEIGHTS_FX

    raw = (cat_avgs.get("econ_growth", 0) * cat_w["econ_growth"] +
           cat_avgs.get("inflation",   0) * cat_w["inflation"]   +
           cat_avgs.get("jobs",        0) * cat_w["jobs"])
    raw_with_consensus = raw * multiplier * direction
    score_inst = round(max(-2.0, min(2.0, raw_with_consensus)), 2)

    if score_inst > 0.7:    bias = "strong_bullish"
    elif score_inst > 0.25: bias = "bullish"
    elif score_inst < -0.7: bias = "strong_bearish"
    elif score_inst < -0.25: bias = "bearish"
    else:                   bias = "neutral"

    instrument_scores[inst_key] = {
        "score":     score_inst,
        "bias":      bias,
        "direction": direction,
    }

# ── Market rates: real yields + yield curve for driver_matrix.compute_macro ──
# Disse inngår IKKE i USD-scoring (FRED_SERIES over), men lagres separat slik
# at driver_matrix kan bruke dem direkte.
MARKET_RATES = {
    "dgs10":  "DGS10",   # 10-year Treasury nominal yield
    "dgs2":   "DGS2",    # 2-year Treasury yield
    "dfii10": "DFII10",  # 10-year TIPS real yield
}
market_rates = {}
for key, fred_id in MARKET_RATES.items():
    print(f"  Henter market rate {key} ({fred_id})...")
    obs = fetch_fred_api(fred_id, limit=10)
    if obs:
        curr = obs[-1][1]
        prev_week = obs[-5][1] if len(obs) >= 5 else obs[0][1]
        market_rates[key] = {
            "value":    round(curr, 3),
            "chg_5d":   round(curr - prev_week, 3),
            "date":     obs[-1][0],
        }
        print(f"    → {curr:.2f}% (5d chg {curr - prev_week:+.3f})")
    time.sleep(0.15)

# Yield curve spread
if "dgs10" in market_rates and "dgs2" in market_rates:
    market_rates["term_spread"] = round(
        market_rates["dgs10"]["value"] - market_rates["dgs2"]["value"], 3)

# 7. Lagre
output = {
    "updated":           datetime.now(timezone.utc).isoformat(),
    "consensus_multi":   multiplier,
    "usd_fundamental": {
        "score": usd_score,
        "bias":  usd_bias,
        "n":     len(indicators),
    },
    "category_scores":   category_scores,
    "indicators":        indicators,
    "instrument_scores": instrument_scores,
    "market_rates":      market_rates,
    "_meta": {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "script": "fetch_fundamentals.py",
        "has_fallback": any(v.get("_fallback") for v in indicators.values()),
    },
}
with open(OUT, "w") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# 8. Utskrift
print(f"\nLagret → {OUT}")
print(f"Konsensus-multiplikator: ×{multiplier}")
print(f"USD fundamental: {usd_bias.upper()}  (score={usd_score:+.3f})")
for cat, cs in category_scores.items():
    print(f"  {cat:14s}: {cs['bias']:14s}  (vektet avg={cs['avg']:+.2f})")
print("\nInstrument-prediksjon:")
for k, v in instrument_scores.items():
    bar = "▲" if "bullish" in v["bias"] else "▼" if "bearish" in v["bias"] else "─"
    bb = "!" if "strong" in v["bias"] else " "
    print(f"  {bar}{bb} {k:8s}: {v['score']:+.2f}  {v['bias']}")
