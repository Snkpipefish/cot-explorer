#!/usr/bin/env python3
"""
fetch_fundamentals.py — Henter fundamental makrodata fra FRED og scorer ±2 per indikator.
Lagrer til data/fundamentals/latest.json.

Dekker alle EdgeFinder-kategorier:
  - Economic Growth & Consumer Strength: GDP, mPMI, sPMI, Retail Sales, Consumer Confidence
  - Inflation: CPI YoY, PPI YoY, PCE YoY, Interest Rates
  - Jobs Market: NFP, Unemployment, Initial Claims, ADP, JOLTS
"""
import urllib.request, json, os, time
from datetime import datetime, timezone

FRED_API_KEY = os.environ.get("FRED_API_KEY", "ab5d635becd9ba4c89e67959d9dc07ab")
BASE = os.path.expanduser("~/cot-explorer/data")
OUT  = os.path.join(BASE, "fundamentals", "latest.json")
os.makedirs(os.path.join(BASE, "fundamentals"), exist_ok=True)

# ── FRED-serier ────────────────────────────────────────────────────────────────
# type:
#   "level"   = bruk råverdien direkte
#   "yoy"     = beregn YoY% (trenger 13+ obs)
#   "mom"     = beregn MoM% (trenger 2+ obs)
#   "mom_abs" = beregn absolutt MoM-endring (trenger 2+ obs)
# higher_good:
#   True  = høyere verdi → bullish USD
#   False = lavere verdi → bullish USD
#   None  = kontekstavhengig (inflasjon)

FRED_SERIES = {
    # Economic Growth & Consumer Strength
    "GDP":     {"id": "A191RL1Q225SBEA", "type": "level",   "higher_good": True,  "label": "GDP Growth QoQ (%)"},
    "mPMI":    {"id": "NAPM",            "type": "level",   "higher_good": True,  "label": "ISM Manufacturing PMI"},
    "sPMI":    {"id": "NMFCI",           "type": "level",   "higher_good": True,  "label": "ISM Services NMI"},
    "Retail":  {"id": "RSAFS",           "type": "mom",     "higher_good": True,  "label": "Retail Sales MoM (%)"},
    "ConConf": {"id": "UMCSENT",         "type": "level",   "higher_good": True,  "label": "UoM Consumer Sentiment"},
    # Inflation
    "CPI":     {"id": "CPIAUCSL",        "type": "yoy",     "higher_good": None,  "label": "CPI YoY (%)"},
    "PPI":     {"id": "PPIACO",          "type": "yoy",     "higher_good": None,  "label": "PPI YoY (%)"},
    "PCE":     {"id": "PCEPI",           "type": "yoy",     "higher_good": None,  "label": "PCE YoY (%)"},
    "IntRate": {"id": "FEDFUNDS",        "type": "level",   "higher_good": True,  "label": "Fed Funds Rate (%)"},
    # Jobs Market
    "NFP":     {"id": "PAYEMS",          "type": "mom_abs", "higher_good": True,  "label": "NFP Endring (k)"},
    "Unemp":   {"id": "UNRATE",          "type": "level",   "higher_good": False, "label": "Arbeidsledighet (%)"},
    "Claims":  {"id": "ICSA",            "type": "level",   "higher_good": False, "label": "Init. Krav (k)"},
    "ADP":     {"id": "ADPMNUSNERNSA",   "type": "mom_abs", "higher_good": True,  "label": "ADP Endring (k)"},
    "JOLTS":   {"id": "JTSJOL",          "type": "level",   "higher_good": True,  "label": "JOLTS Stillinger (k)"},
}

CATEGORIES = {
    "econ_growth": ["GDP", "mPMI", "sPMI", "Retail", "ConConf"],
    "inflation":   ["CPI", "PPI", "PCE", "IntRate"],
    "jobs":        ["NFP", "Unemp", "Claims", "ADP", "JOLTS"],
}

# Kart: instrument → hvilken retning USD-fundamental score virker
# +1 = sterk USD = bullish for instrumentet
# -1 = sterk USD = bearish for instrumentet
INSTRUMENT_USD_DIR = {
    "EURUSD": -1, "GBPUSD": -1, "AUDUSD": -1,
    "USDJPY": +1, "DXY":    +1,
    "Gold":   -1, "Silver": -1,
    "SPX":    +1, "NAS100": +1,  # vekst-data er bullish for aksjer
    "Brent":  +1, "WTI":    +1,  # vekst-data er bullish for råolje
}

# ── FRED API-henting ───────────────────────────────────────────────────────────
def fetch_fred_api(series_id, limit=25):
    """Henter FRED-serie via JSON API. Returnerer [(dato, float), ...] eldst→nyest."""
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={FRED_API_KEY}"
           f"&file_type=json&sort_order=desc&limit={limit}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read())
        obs = []
        for o in d.get("observations", []):
            if o.get("value") not in (".", "", None):
                try:
                    obs.append((o["date"], float(o["value"])))
                except (ValueError, KeyError):
                    pass
        return list(reversed(obs))   # eldst→nyest
    except Exception as e:
        print(f"  FRED {series_id} FEIL: {e}")
        return []

# ── Scoringsfunksjoner per indikator ──────────────────────────────────────────
def score_indicator(key, current, previous):
    """
    Returnerer heltall fra -2 til +2 som representerer USD-bullish/bearish styrke.
    Positiv = USD bullish. Negativ = USD bearish.
    """
    if current is None:
        return 0

    # PMI (Manufacturing og Services) — ekspansjon/kontraksjon vs 50
    if key in ("mPMI", "sPMI"):
        if current > 56:   s = 2
        elif current > 52: s = 1
        elif current > 50: s = 0
        elif current > 47: s = -1
        else:              s = -2
        # Trendbonus: sterk oppgang/nedgang
        if previous is not None:
            delta = current - previous
            if delta > 2 and s < 2:  s += 1
            elif delta < -2 and s > -2: s -= 1
        return max(-2, min(2, s))

    # Inflasjon — scoring basert på YoY-nivå og retning
    # Høy og stigende inflasjon = mer renteheving → USD bullish
    # Lav og fallende inflasjon = kutting forventet → USD bearish
    if key in ("CPI", "PPI", "PCE"):
        if current > 4.0:   level_s = 2
        elif current > 2.5: level_s = 1
        elif current > 1.5: level_s = 0
        elif current > 0.5: level_s = -1
        else:               level_s = -2
        trend_s = 0
        if previous is not None:
            if current > previous + 0.2:  trend_s = 1
            elif current < previous - 0.2: trend_s = -1
        return max(-2, min(2, level_s + trend_s))

    # Rente — stiger = hawkish = USD bullish, faller = dovish = USD bearish
    if key == "IntRate":
        if previous is None:
            return 1 if current >= 3.5 else 0
        delta = current - previous
        if delta > 0.1:   return 2
        elif delta > 0:   return 1
        elif delta == 0:
            return 1 if current >= 3.5 else 0
        elif delta > -0.1: return -1
        else:              return -2

    # NFP og ADP — monthly change i tusen jobber
    if key in ("NFP", "ADP"):
        if current > 250:   s = 2
        elif current > 150: s = 1
        elif current > 50:  s = 0
        elif current > 0:   s = -1
        else:               s = -2
        # Trendbonus: signifikant forbedring vs forrige periode
        if previous is not None:
            if current > previous * 1.5 and s < 2:  s += 1
            elif current < previous * 0.5 and s > -2: s -= 1
        return max(-2, min(2, s))

    # Arbeidsledighet — lavere = bedre (inverted)
    if key == "Unemp":
        if current < 3.5:   s = 2
        elif current < 4.0: s = 1
        elif current < 4.5: s = 0
        elif current < 5.0: s = -1
        else:               s = -2
        if previous is not None:
            if current < previous:   s = min(2,  s + 1)   # fallende ledighet = bra
            elif current > previous: s = max(-2, s - 1)
        return s

    # Initial Claims — lavere = bedre (i tusen, mottatt som råtall fra FRED)
    if key == "Claims":
        k = current / 1000   # konverter fra individuelle krav til tusen
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

    # JOLTS — stillingsutlysninger i tusen
    if key == "JOLTS":
        if current > 9000:   return 2
        elif current > 7500: return 1
        elif current > 6000: return 0
        elif current > 4500: return -1
        else:                return -2

    # GDP — kvartalsvekst i prosent (annualisert)
    if key == "GDP":
        if current > 3.0:   return 2
        elif current > 1.5: return 1
        elif current > 0:   return 0
        elif current > -1:  return -1
        else:               return -2

    # Retail Sales MoM %
    if key == "Retail":
        if current > 1.0:   return 2
        elif current > 0.3: return 1
        elif current > -0.3: return 0
        elif current > -0.8: return -1
        else:               return -2

    # Consumer Confidence (UoM Sentiment, skala 0–100)
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

    # Generisk fallback
    if previous is None:
        return 0
    delta = current - previous
    if key in (k for k, c in FRED_SERIES.items() if c.get("higher_good") is False):
        return 1 if delta < 0 else -1 if delta > 0 else 0
    return 1 if delta > 0 else -1 if delta < 0 else 0


# ── Beregn indikator ───────────────────────────────────────────────────────────
def compute_indicator(key, cfg, obs):
    """Beregner aktuell verdi, forrige og score fra rå FRED-observasjoner."""
    if not obs:
        return None

    t   = cfg["type"]
    raw_current  = obs[-1][1]
    raw_previous = obs[-2][1] if len(obs) >= 2 else None
    date         = obs[-1][0]

    if t == "level":
        current  = round(raw_current,  3)
        previous = round(raw_previous, 3) if raw_previous is not None else None

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
        current, previous = raw_current, raw_previous

    score = score_indicator(key, current, previous)
    trend = ("opp" if current > previous else "ned" if current < previous else "flat") \
            if previous is not None else "ukjent"

    # Lesbar Claims-verdi i tusen
    display = current
    if key == "Claims":
        display = round(current / 1000, 1)

    return {
        "key":      key,
        "label":    cfg["label"],
        "current":  display if key == "Claims" else current,
        "previous": round(previous / 1000, 1) if (key == "Claims" and previous) else previous,
        "date":     date,
        "score":    score,
        "trend":    trend,
    }


# ── Prøv å hente PMI fra ForexFactory-kalenderen (supplement til FRED) ────────
def try_calendar_pmi():
    """
    Returnerer {key: {"actual": float, "forecast": float, "surprise": int}} for PMI
    fra denne ukens ForexFactory-kalender, hvis tilgjengelig.
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
            act_val = float(actual.replace("%", "").replace("K", "").strip())
        except (ValueError, AttributeError):
            continue
        try:
            fore_val = float(ev.get("forecast", "").replace("%", "").strip()) \
                       if ev.get("forecast") else None
        except (ValueError, AttributeError):
            fore_val = None

        surprise = 0
        if fore_val is not None:
            diff = act_val - fore_val
            if diff > 1:   surprise = 2
            elif diff > 0: surprise = 1
            elif diff < -1: surprise = -2
            elif diff < 0: surprise = -1

        if "manufacturing pmi" in title or "ism manufacturing" in title:
            pmi_map["mPMI"] = {"actual": act_val, "forecast": fore_val, "surprise": surprise}
        elif "services pmi" in title or "non-manufacturing" in title or "ism services" in title:
            pmi_map["sPMI"] = {"actual": act_val, "forecast": fore_val, "surprise": surprise}

    return pmi_map


# ── Hovedlogikk ───────────────────────────────────────────────────────────────
print("=== fetch_fundamentals.py ===")
print(f"FRED API-nøkkel: {'***' + FRED_API_KEY[-4:] if FRED_API_KEY else 'MANGLER'}")

indicators = {}
for key, cfg in FRED_SERIES.items():
    print(f"  Henter {key} ({cfg['id']})...")
    # YoY trenger 14 obs (1 år + 1 ekstra for forrige YoY)
    limit = 16 if cfg["type"] == "yoy" else 6
    obs   = fetch_fred_api(cfg["id"], limit=limit)
    result = compute_indicator(key, cfg, obs)
    if result:
        indicators[key] = result
        print(f"    → {result['current']} ({result['trend']:5s})  score={result['score']:+d}")
    else:
        print(f"    → FEIL eller for få datapunkter")
    time.sleep(0.2)   # Respekter FRED rate limit

# Supplement: oppdater PMI fra kalender hvis vi har faktiske verdier
cal_pmi = try_calendar_pmi()
for k, pmi in cal_pmi.items():
    if k in indicators and pmi.get("actual"):
        # Kalender-actual overskriver FRED-verdien (ferskere)
        indicators[k]["current"]   = pmi["actual"]
        indicators[k]["forecast"]  = pmi.get("forecast")
        indicators[k]["surprise"]  = pmi.get("surprise", 0)
        # Juster score med surprise hvis signifikant
        indicators[k]["score"] = max(-2, min(2,
            indicators[k]["score"] + pmi.get("surprise", 0)))
        print(f"  Kalender PMI {k}: actual={pmi['actual']}"
              f"  forecast={pmi.get('forecast')}  surprise={pmi.get('surprise',0):+d}")

# ── Kategoriskårer ────────────────────────────────────────────────────────────
category_scores = {}
for cat, keys in CATEGORIES.items():
    vals  = [indicators[k]["score"] for k in keys if k in indicators]
    total = sum(vals)
    avg   = round(total / len(vals), 2) if vals else 0
    category_scores[cat] = {
        "score":    total,
        "avg":      avg,
        "count":    len(vals),
        "bias":     "bullish" if avg >= 0.5 else "bearish" if avg <= -0.5 else "neutral",
        "keys":     keys,
    }

# ── Samlet USD-fundamental score ─────────────────────────────────────────────
all_scores = [v["score"] for v in indicators.values()]
usd_total  = sum(all_scores)
usd_avg    = round(usd_total / len(all_scores), 2) if all_scores else 0
usd_bias   = "bullish" if usd_avg >= 0.5 else "bearish" if usd_avg <= -0.5 else "neutral"

# ── Beregn retningsvisende score per instrument ───────────────────────────────
instrument_scores = {}
for inst_key, direction in INSTRUMENT_USD_DIR.items():
    # Alle kategorier brukes; for aksjer/råvarer vektlegges econ_growth mer
    if inst_key in ("SPX", "NAS100", "Brent", "WTI"):
        growth = category_scores.get("econ_growth", {}).get("avg", 0)
        jobs   = category_scores.get("jobs",        {}).get("avg", 0)
        raw    = (growth * 0.6 + jobs * 0.4) * direction
    else:
        # Valuta og metaller: alle tre kategorier
        growth = category_scores.get("econ_growth", {}).get("avg", 0)
        infl   = category_scores.get("inflation",   {}).get("avg", 0)
        jobs   = category_scores.get("jobs",        {}).get("avg", 0)
        raw    = (growth * 0.3 + infl * 0.35 + jobs * 0.35) * direction

    score_inst = max(-2, min(2, round(raw, 1)))
    instrument_scores[inst_key] = {
        "score":     score_inst,
        "bias":      "bullish" if score_inst > 0.3 else "bearish" if score_inst < -0.3 else "neutral",
        "direction": direction,
    }

# ── Lagre output ─────────────────────────────────────────────────────────────
output = {
    "updated":            datetime.now(timezone.utc).isoformat(),
    "usd_fundamental": {
        "score":    usd_total,
        "avg":      usd_avg,
        "bias":     usd_bias,
        "n":        len(all_scores),
    },
    "category_scores":    category_scores,
    "indicators":         indicators,
    "instrument_scores":  instrument_scores,
}

with open(OUT, "w") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nLagret → {OUT}")
print(f"USD fundamental: {usd_bias.upper()} (avg score={usd_avg:+.2f})")
for cat, cs in category_scores.items():
    print(f"  {cat:14s}: {cs['bias']:8s}  (sum={cs['score']:+d})")
print("\nInstrument-prediksjon:")
for k, v in instrument_scores.items():
    bar = "▲" if v["bias"] == "bullish" else "▼" if v["bias"] == "bearish" else "─"
    print(f"  {bar} {k:8s}: {v['score']:+.1f}  {v['bias']}")
