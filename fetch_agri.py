#!/usr/bin/env python3
"""
fetch_agri.py — Avlings-analyse
Henter 7-dagers værvarsling (Open-Meteo) for alle landbruksregioner,
beregner tørkestress/flomrisiko, mapper mot COT-posisjoner og lager
en samlet prisretning per avling.

Output: data/agri/latest.json
"""

import json, os, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

BASE = os.path.expanduser("~/cot-explorer/data")
OUT  = os.path.join(BASE, "agri", "latest.json")
CACHE_FILE = os.path.join(BASE, "agri", "season_cache.json")
os.makedirs(os.path.join(BASE, "agri"), exist_ok=True)

REGIONS_FILE      = os.path.join(BASE, "geointel", "agri_regions.json")
COMBINED_FILE     = os.path.join(BASE, "combined", "latest.json")
EURONEXT_COT_FILE = os.path.join(BASE, "euronext_cot", "latest.json")

# Avlinger der Euronext er primær COT-kilde (europeisk hjemmebørs)
EURONEXT_PRIMARY = {"wheat", "canola", "corn"}

# ── Sesong: kritiske måneder per avling og hemisfære ──────────────
# score-multiplikator for værpåvirkning (1.0 = normal, 1.5 = kritisk sesong)
MONTH = datetime.now(timezone.utc).month
def season_mult(crop_key, lat):
    """Returner 1.0–1.5 avhengig av om det er kritisk sesong for avlingen."""
    north = lat > 0
    spring_north = MONTH in (4, 5, 6)    # planting/vekst nordlig halvkule
    summer_north  = MONTH in (7, 8)
    harvest_north = MONTH in (9, 10)
    spring_south  = MONTH in (10, 11, 12)
    summer_south  = MONTH in (1, 2, 3)   # vekstsesong sørlig halvkule

    if crop_key in ("corn", "soybeans", "cotton"):
        if north  and spring_north:  return 1.5   # planting = kritisk
        if not north and summer_south: return 1.5
    if crop_key in ("wheat", "canola"):
        if north  and (MONTH in (3,4,5)):  return 1.5
        if not north and (MONTH in (10,11)): return 1.5
    if crop_key in ("coffee", "cocoa", "sugar", "palm"):
        if not north and (MONTH in (2,3,4,5)): return 1.5
    return 1.0

# ── COT-markeder → avlings-nøkkel ────────────────────────────────
COT_MAP = {
    "corn":     ["Corn"],
    "wheat":    ["Wheat", "Kc Hrd Red Winter Wht", "Wheat-Srs 2-Chi",
                 "Minneapolis Hard Red Spring Wheat"],
    "soybeans": ["Soybeans", "Soybean Meal", "Soybean Oil"],
    "canola":   ["Canola"],
    "cotton":   ["Cotton No. 2"],
    "sugar":    ["Sugar No. 11", "Sugar No. 16"],
    "coffee":   ["Coffee C"],
    "cocoa":    ["Cocoa"],
    "palm":     [],   # ikke på CFTC
    "rice":     ["Rough Rice"],
    "oats":     ["Oats"],
    "cattle":   ["Live Cattle", "Feeder Cattle"],
}

# Avlings-nøkkel → norsk navn + ikon
CROP_META = {
    "corn":     {"navn": "Mais",        "ikon": "🌽"},
    "wheat":    {"navn": "Hvete",       "ikon": "🌾"},
    "soybeans": {"navn": "Soyabønner",  "ikon": "🫘"},
    "canola":   {"navn": "Canola/Raps", "ikon": "🌿"},
    "cotton":   {"navn": "Bomull",      "ikon": "☁️"},
    "sugar":    {"navn": "Sukker",      "ikon": "🍬"},
    "coffee":   {"navn": "Kaffe",       "ikon": "☕"},
    "cocoa":    {"navn": "Kakao",       "ikon": "🍫"},
    "palm":     {"navn": "Palmeolje",   "ikon": "🌴"},
    "rice":     {"navn": "Ris",         "ikon": "🍚"},
}

# ── Fenologi-data per avling (GDD, nedbør, temperaturbase) ──────
CROP_PHENOLOGY = {
    "corn":     {"tbase": 10, "gdd_maturity": 2700, "ideal_precip_mm": 500},
    "wheat":    {"tbase": 0,  "gdd_maturity": 2000, "ideal_precip_mm": 450},
    "soybeans": {"tbase": 10, "gdd_maturity": 2500, "ideal_precip_mm": 500},
    "canola":   {"tbase": 5,  "gdd_maturity": 1500, "ideal_precip_mm": 400},
    "cotton":   {"tbase": 15, "gdd_maturity": 2200, "ideal_precip_mm": 600},
    "sugar":    {"tbase": 15, "gdd_maturity": 3500, "ideal_precip_mm": 1500},
    "coffee":   {"tbase": 10, "gdd_maturity": 3000, "ideal_precip_mm": 1400},
    "cocoa":    {"tbase": 18, "gdd_maturity": 2500, "ideal_precip_mm": 1500},
    "rice":     {"tbase": 10, "gdd_maturity": 2500, "ideal_precip_mm": 1000},
    "palm":     {"tbase": 18, "gdd_maturity": None, "ideal_precip_mm": 2000},
}

# Norsk avlingsnavn → crop_key mapping
CROP_NAME_MAP = {
    "Mais": "corn", "Soyabønner": "soybeans", "Hvete": "wheat",
    "Vinterhvete": "wheat", "Myk hvete": "wheat", "Bomull": "cotton",
    "Raps": "canola", "Canola": "canola", "Sukker": "sugar",
    "Kaffe": "coffee", "Kakao": "cocoa", "Ris": "rice",
    "Palmeolje": "palm", "Sorghum": "corn", "Solsikke": "soybeans",
    "Bygg": "wheat",  # bruker hvete-parametere som tilnærming
}

# Kanoniske stadienavn og norsk oversettelse
STAGE_LABELS = {
    "dormancy": "Hvilefase", "dormancy-end": "Hvilefase",
    "pre-plant": "Forberedelse", "sowing": "Såing", "planting": "Såing",
    "emergence": "Spiring", "early-growth": "Tidlig vekst",
    "growing": "Vegetativ vekst", "flowering": "Blomstring",
    "heading": "Aksing", "ripening": "Modning",
    "harvest": "Høsting", "post-harvest": "Etter høst",
    "low-prod": "Lav produksjon", "recovering": "Oppgang",
    "moderate": "Moderat", "peak": "Topp-produksjon",
}
STAGE_ICONS = {
    "Hvilefase": "💤", "Forberedelse": "🔧", "Såing": "🌱",
    "Spiring": "🌱", "Tidlig vekst": "🌱", "Vegetativ vekst": "🌿",
    "Blomstring": "🌸", "Aksing": "🌾", "Modning": "🌾",
    "Høsting": "🚜", "Etter høst": "📦",
    "Lav produksjon": "📉", "Oppgang": "📈",
    "Moderat": "🌴", "Topp-produksjon": "🌴",
}

# Aktive stadier (de som teller som "i sesong" for arkiv-henting)
ACTIVE_STAGES = {"pre-plant", "sowing", "planting", "emergence", "early-growth",
                 "growing", "flowering", "heading", "ripening", "harvest",
                 "low-prod", "recovering", "moderate", "peak"}

# ── ENSO-impakt per region ─────────────────────────────────────
ENSO_IMPACTS = {
    # El Niño-effekter
    ("El Niño", "australia_wheat"):  {"impact": "Tørkerisiko", "adj": 0.5},
    ("El Niño", "india_punjab"):     {"impact": "Tørkerisiko", "adj": 0.5},
    ("El Niño", "sea_palm"):         {"impact": "Tørkerisiko", "adj": 0.5},
    ("El Niño", "west_africa_cocoa"):{"impact": "Tørrere enn normalt", "adj": 0.3},
    ("El Niño", "brazil_mato_grosso"):{"impact": "Gunstig regn", "adj": -0.3},
    ("El Niño", "argentina_pampas"):  {"impact": "Gunstig regn", "adj": -0.3},
    # La Niña-effekter
    ("La Niña", "us_cornbelt"):      {"impact": "Tørkerisiko", "adj": 0.5},
    ("La Niña", "us_great_plains"):  {"impact": "Tørkerisiko", "adj": 0.5},
    ("La Niña", "us_delta_cotton"):  {"impact": "Tørkerisiko", "adj": 0.3},
    ("La Niña", "argentina_pampas"): {"impact": "Tørkerisiko", "adj": 0.5},
    ("La Niña", "brazil_mato_grosso"):{"impact": "Tørkerisiko", "adj": 0.3},
    ("La Niña", "australia_wheat"):   {"impact": "Gunstig regn", "adj": -0.3},
    ("La Niña", "india_punjab"):      {"impact": "Gunstig monsun", "adj": -0.3},
}

# Avlings-nøkkel per region ──────────────────────────────────────
REGION_CROPS = {
    "us_cornbelt":       ["corn", "soybeans"],
    "us_great_plains":   ["wheat"],
    "brazil_mato_grosso":["soybeans", "corn", "cotton", "sugar"],
    "argentina_pampas":  ["soybeans", "wheat", "corn"],
    "ukraine_blacksea":  ["wheat", "corn"],
    "eu_northern":       ["wheat", "canola"],
    "canada_prairie":    ["wheat", "canola"],
    "australia_wheat":   ["wheat", "canola"],
    "india_punjab":      ["wheat", "rice", "sugar"],
    "sea_palm":          ["palm"],
    "west_africa_cocoa": ["cocoa", "coffee"],
    "brazil_coffee":     ["coffee"],
    "us_delta_cotton":   ["cotton", "rice"],
    "china_wheat":       ["wheat", "corn"],
}

def fetch_weather(lat, lon):
    """Henter 7-dagers daglig prognose fra Open-Meteo."""
    params = urllib.parse.urlencode({
        "latitude":  lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "current": "temperature_2m,precipitation,wind_speed_10m,relative_humidity_2m",
        "forecast_days": 7,
        "timezone": "auto",
    })
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  Open-Meteo FEIL ({lat},{lon}): {e}")
        return None

def fetch_archive_weather(lat, lon, start_date, end_date):
    """Henter historisk daglig vær fra Open-Meteo Archive API."""
    params = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "start_date": start_date, "end_date": end_date,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "auto",
    })
    url = f"https://archive-api.open-meteo.com/v1/archive?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"    Arkiv FEIL ({lat},{lon}): {e}")
        return None


def detect_growth_stage(stages_array, month):
    """
    Returnerer vekststadium og % gjennom vekstsesong basert på stages-array.
    stages_array: 12 elementer, index 0=jan, 11=des.
    """
    if not stages_array or month < 1 or month > 12:
        return {"stage": "ukjent", "stage_no": "Ukjent", "icon": "❓",
                "season_pct": 0, "in_season": False, "season_months": None}

    raw_stage = stages_array[month - 1]
    stage_no = STAGE_LABELS.get(raw_stage, raw_stage.replace("-", " ").title())
    icon = STAGE_ICONS.get(stage_no, "🌱")
    in_season = raw_stage in ACTIVE_STAGES

    # Finn sesongvindu (start og slutt-måned)
    season_start = None
    season_end = None
    for i in range(12):
        if stages_array[i] in ACTIVE_STAGES:
            if season_start is None:
                season_start = i + 1
            season_end = i + 1

    # Håndter wrap-around (f.eks. sørlig halvkule: okt-mar)
    if season_start is not None:
        # Sjekk om sesongen wrapper rundt årsskiftet
        first_inactive = None
        for i in range(12):
            if stages_array[i] not in ACTIVE_STAGES:
                if first_inactive is None:
                    first_inactive = i
            elif first_inactive is not None:
                # Fant aktiv etter inaktiv → mulig wrap
                break

        if season_start is not None and season_end is not None:
            if season_end >= season_start:
                total_months = season_end - season_start + 1
                if in_season:
                    elapsed = month - season_start
                    season_pct = round(elapsed / total_months * 100)
                else:
                    season_pct = 0
            else:
                # Wrap-around
                total_months = (12 - season_start + 1) + season_end
                if in_season:
                    if month >= season_start:
                        elapsed = month - season_start
                    else:
                        elapsed = (12 - season_start) + month
                    season_pct = round(elapsed / total_months * 100)
                else:
                    season_pct = 0
        else:
            total_months = 0
            season_pct = 0

        MND = ["jan","feb","mar","apr","mai","jun","jul","aug","sep","okt","nov","des"]
        season_label = f"{MND[season_start-1]}–{MND[season_end-1]}" if season_start and season_end else None
    else:
        season_pct = 0
        season_label = None

    # Finn forventet høstmåned
    harvest_months = [i+1 for i in range(12) if stages_array[i] in ("harvest", "ripening")]
    harvest_label = None
    if harvest_months:
        MND = ["jan","feb","mar","apr","mai","jun","jul","aug","sep","okt","nov","des"]
        harvest_label = f"{MND[harvest_months[0]-1]}–{MND[harvest_months[-1]-1]}" if len(harvest_months) > 1 else MND[harvest_months[0]-1]

    return {
        "stage": raw_stage,
        "stage_no": stage_no,
        "icon": icon,
        "season_pct": max(0, min(100, season_pct)),
        "in_season": in_season,
        "season_months": season_label,
        "harvest_window": harvest_label,
        "season_start_month": season_start,
        "season_end_month": season_end,
    }


def calculate_season_metrics(archive_data, crop_key):
    """Beregner sesong-metrikker fra arkivdata: GDD, nedbør, stressdager."""
    pheno = CROP_PHENOLOGY.get(crop_key, {})
    tbase = pheno.get("tbase", 10)
    gdd_maturity = pheno.get("gdd_maturity")
    ideal_precip = pheno.get("ideal_precip_mm", 500)

    if not archive_data or "daily" not in archive_data:
        return None

    daily = archive_data["daily"]
    tmax_arr = daily.get("temperature_2m_max", [])
    tmin_arr = daily.get("temperature_2m_min", [])
    precip_arr = daily.get("precipitation_sum", [])
    n = min(len(tmax_arr), len(tmin_arr), len(precip_arr))
    if n == 0:
        return None

    gdd_total = 0
    precip_total = 0
    stress_days = 0
    for i in range(n):
        tx = tmax_arr[i] if tmax_arr[i] is not None else 20
        tn = tmin_arr[i] if tmin_arr[i] is not None else 10
        pr = precip_arr[i] if precip_arr[i] is not None else 0
        gdd_total += max(0, (tx + tn) / 2 - tbase)
        precip_total += pr
        if tx > 35 or tn < (tbase - 5) or pr > 50:
            stress_days += 1

    gdd_pct = round(gdd_total / gdd_maturity * 100, 1) if gdd_maturity else None
    precip_pct = round(precip_total / ideal_precip * 100, 1) if ideal_precip else None

    return {
        "gdd_accumulated": round(gdd_total),
        "gdd_required": gdd_maturity,
        "gdd_pct": gdd_pct,
        "season_precip_mm": round(precip_total),
        "ideal_precip_mm": ideal_precip,
        "precip_pct": precip_pct,
        "stress_days": stress_days,
        "days_measured": n,
    }


def estimate_yield_quality(metrics, season_pct):
    """
    Estimerer yield-kvalitet basert på sesongmetrikker.
    Returnerer score (0-100) og norsk rating-tekst.
    """
    if not metrics:
        return None, None, None

    score = 100
    gdd_pct = metrics.get("gdd_pct")
    precip_pct = metrics.get("precip_pct")
    stress = metrics.get("stress_days", 0)

    # Tidlig-i-sesong demping: GDD akkumuleres eksponentielt (lite om våren,
    # mye om sommeren), så lineær sammenligning er misvisende tidlig.
    early = season_pct < 40

    # GDD-faktor: er vi på skjema?
    # Bruk en ikke-lineær forventning: tidlig sesong → forvent mindre GDD
    if gdd_pct is not None and season_pct > 10:
        # Kvadratisk kurve: forventet GDD% ≈ (season_pct/100)^1.5 * 100
        expected_gdd_pct = (season_pct / 100) ** 1.5 * 100
        gdd_ratio = gdd_pct / max(expected_gdd_pct, 1)
        if gdd_ratio < 0.4:
            score -= 20 if not early else 5
        elif gdd_ratio < 0.7:
            score -= 10 if not early else 3
        elif gdd_ratio > 1.3:
            score += 5  # litt forsprang

    # Nedbør-faktor: tidlig i sesong er lav nedbør normalt
    if precip_pct is not None and season_pct > 10:
        expected_precip_pct = season_pct  # lineær er OK for nedbør
        precip_ratio = precip_pct / max(expected_precip_pct, 1)
        if precip_ratio < 0.3:
            score -= 20 if not early else 5
        elif precip_ratio < 0.5:
            score -= 10 if not early else 3
        elif precip_ratio > 2.5:
            score -= 15 if not early else 3
        elif precip_ratio > 1.8:
            score -= 8 if not early else 2

    # Stress-faktor
    score -= stress * (2 if not early else 1)

    score = max(0, min(100, score))

    if score >= 85:
        rating, price_hint = "Utmerket", "H��y produksjon → stabilt prisnivå"
    elif score >= 70:
        rating, price_hint = "God", "Normal produksjon → moderate priser"
    elif score >= 55:
        rating, price_hint = "Middels", "Noen utfordringer → mulig prispress oppover"
    elif score >= 40:
        rating, price_hint = "Svak", "Dårlige forhold → potensielt høyere priser"
    else:
        rating, price_hint = "Kritisk", "Alvorlige problemer → forvent prisøkning"

    if early:
        rating = f"{rating} (tidlig)"
        price_hint = f"Tidlig i sesongen — {price_hint.lower()}"

    return score, rating, price_hint


def fetch_enso():
    """Henter ENSO-fase (El Niño/La Niña) fra NOAA CPC."""
    url = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            lines = r.read().decode("utf-8", errors="replace").strip().split("\n")
        # Siste rad med data
        for line in reversed(lines):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    oni = float(parts[-1])
                    period = parts[0] + " " + parts[1] if len(parts) >= 2 else "?"
                    if oni > 0.5:
                        phase = "El Niño"
                    elif oni < -0.5:
                        phase = "La Niña"
                    else:
                        phase = "Nøytral"
                    return {"oni_value": oni, "phase": phase, "period": period}
                except ValueError:
                    continue
        return None
    except Exception as e:
        print(f"  ENSO FEIL: {e}")
        return None


def score_weather(w, crop_key, lat):
    """
    Returnerer:
      score: -2 (veldig godt vær) → +3 (alvorlig risiko)
      outlook: 'utmerket'|'normalt'|'tørt'|'tørke'|'vått'|'flom'
      precip_7d, temp_max_avg, summary
    """
    if not w:
        return {"score": 0, "outlook": "ukjent", "precip_7d": None,
                "temp_max_avg": None, "summary": "Ingen værdata"}
    daily = w.get("daily", {})
    precip = daily.get("precipitation_sum", [])
    tmax   = daily.get("temperature_2m_max", [])
    tmin   = daily.get("temperature_2m_min", [])

    precip_7d  = sum(p for p in precip if p is not None)
    temp_max   = sum(t for t in tmax if t is not None) / max(len([t for t in tmax if t is not None]), 1)
    temp_min   = sum(t for t in tmin if t is not None) / max(len([t for t in tmin if t is not None]), 1)

    mult = season_mult(crop_key, lat)

    # Tørkestress: lite nedbør + høy temperatur
    if precip_7d < 3 and temp_max > 30:
        score, outlook = 3, "tørke"
        summary = f"Alvorlig tørke: {precip_7d:.0f}mm / {temp_max:.0f}°C maks"
    elif precip_7d < 8 and temp_max > 25:
        score, outlook = 2, "tørt"
        summary = f"Tørt og varmt: {precip_7d:.0f}mm / {temp_max:.0f}°C maks"
    elif precip_7d < 15 and temp_max > 28:
        score, outlook = 1, "tørt"
        summary = f"Noe tørt: {precip_7d:.0f}mm nedbør"
    # Flomrisiko: mye nedbør
    elif precip_7d > 120:
        score, outlook = 3, "flom"
        summary = f"Flomrisiko: {precip_7d:.0f}mm på 7 dager"
    elif precip_7d > 70:
        score, outlook = 2, "vått"
        summary = f"Mye nedbør: {precip_7d:.0f}mm på 7 dager"
    elif precip_7d > 40:
        score, outlook = 1, "vått"
        summary = f"Over normalt nedbør: {precip_7d:.0f}mm"
    # Kalde temperaturer (frost-risiko i plantetid)
    elif temp_min < -2 and MONTH in (3, 4, 5) and lat > 30:
        score, outlook = 2, "frost"
        summary = f"Frostrisiko: {temp_min:.0f}°C min"
    # Normalt
    else:
        score, outlook = 0, "normalt"
        summary = f"Normalt: {precip_7d:.0f}mm nedbør, {temp_max:.0f}°C maks"

    # Skaler med sesongmultiplikator (kritisk sesong = mer påvirkning)
    final_score = round(score * mult)

    return {
        "score":       final_score,
        "raw_score":   score,
        "season_mult": mult,
        "outlook":     outlook,
        "precip_7d":   round(precip_7d, 1),
        "temp_max_avg": round(temp_max, 1),
        "temp_min_avg": round(temp_min, 1),
        "summary":     summary,
    }

def load_euronext_cot():
    """Last inn Euronext COT-data. Returnerer dict crop_key → data, eller {}."""
    if not os.path.exists(EURONEXT_COT_FILE):
        return {}
    try:
        with open(EURONEXT_COT_FILE) as f:
            raw = json.load(f)
        markets = raw.get("markets", {})
        # Sjekk at dataene ikke er for gamle (maks 14 dager — Euronext publiserer ukentlig)
        result = {}
        today = datetime.now(timezone.utc).date()
        for crop, d in markets.items():
            date_str = d.get("date", "")
            try:
                age = (today - datetime.strptime(date_str, "%Y-%m-%d").date()).days
                if age > 14:
                    print(f"  Euronext {crop}: data er {age} dager gammel — bruker CFTC fallback")
                    continue
            except Exception:
                pass
            result[crop] = d
        return result
    except Exception as e:
        print(f"  Euronext COT FEIL ved lasting: {e}")
        return {}


def get_cot_for_crop(crop_key, cot_data, euronext_data=None):
    """
    Henter COT-info for en avling.

    For hvete/raps/mais: kombinerer Euronext + CFTC med OI-vekting.
    Euronext dekker europeiske futures (Paris), CFTC dekker amerikanske (Chicago).
    Begge er reelle signaler om global spekulant-sentiment — OI-vektet snitt
    gir et mer komplett bilde enn å velge én kilde.

    For andre avlinger: kun CFTC.
    Fallback til det som finnes hvis bare én kilde er tilgjengelig.
    """
    euronext_data = euronext_data or {}

    # ── Hent CFTC-data ───────────────────────────────────────────
    cftc_net = cftc_oi = cftc_chg = 0
    cftc_hist = []
    cftc_market = crop_key
    cftc_date   = ""
    has_cftc    = False

    markets = COT_MAP.get(crop_key, [])
    matches = [e for e in cot_data
               if any(m.lower() in e.get("market","").lower() for m in markets)]
    if matches:
        main     = max(matches, key=lambda e: e.get("open_interest", 0) or 0)
        sp       = main.get("spekulanter") or {}
        cftc_net  = sp.get("net", 0) or 0
        cftc_chg  = main.get("change_spec_net", 0) or 0
        cftc_oi   = main.get("open_interest", 1) or 1
        cftc_hist = main.get("spec_net_history", []) or []
        cftc_market = main.get("market", crop_key)
        cftc_date   = main.get("date", "")
        has_cftc    = True

    # ── Hent Euronext-data (kun for EU-primær-avlinger) ──────────
    eu_net = eu_oi = eu_chg = 0
    eu_hist = []
    eu_market = ""
    eu_date   = ""
    has_eu    = False

    if crop_key in EURONEXT_PRIMARY and crop_key in euronext_data:
        eu        = euronext_data[crop_key]
        sp_eu     = eu.get("spekulanter") or {}
        eu_net    = sp_eu.get("net", 0) or 0
        eu_chg    = eu.get("change_spec_net", 0) or 0
        eu_oi     = eu.get("open_interest", 1) or 1
        eu_hist   = eu.get("spec_net_history", []) or []
        eu_market = eu.get("display", f"Euronext {crop_key.title()}")
        eu_date   = eu.get("date", "")
        has_eu    = True

    if not has_cftc and not has_eu:
        return None

    # ── Kombiner med OI-vekting ───────────────────────────────────
    if has_cftc and has_eu:
        total_oi  = cftc_oi + eu_oi
        # OI-vektet netto-% er det meningsfulle målet på global posisjonering
        net_pct   = ((cftc_net / cftc_oi * cftc_oi) + (eu_net / eu_oi * eu_oi)) / total_oi * 100
        # Absolutt netto for visning (summer begge markeder)
        net       = cftc_net + eu_net
        chg       = cftc_chg + eu_chg
        oi        = total_oi
        # Historikk: kombiner hvis begge finnes (summer per uke)
        hist_len  = min(len(cftc_hist), len(eu_hist))
        hist      = [cftc_hist[-(hist_len-i)] + eu_hist[-(hist_len-i)]
                     for i in range(hist_len, 0, -1)] if hist_len > 1 else cftc_hist or eu_hist
        source    = "Euronext+CFTC"
        market_label = f"{eu_market} + {cftc_market}"
        date_val  = eu_date or cftc_date
        # Enighet mellom kildene
        agrees    = (eu_net > 0) == (cftc_net > 0)
    elif has_eu:
        net_pct   = eu_net / eu_oi * 100
        net, chg, oi, hist = eu_net, eu_chg, eu_oi, eu_hist
        source    = "Euronext"
        market_label = eu_market
        date_val  = eu_date
        agrees    = None
    else:
        net_pct   = cftc_net / cftc_oi * 100
        net, chg, oi, hist = cftc_net, cftc_chg, cftc_oi, cftc_hist
        source    = "CFTC"
        market_label = cftc_market
        date_val  = cftc_date
        agrees    = None

    # ── Bias ─────────────────────────────────────────────────────
    bias = "bull" if net_pct > 0 else "bear"

    # ── Momentum: siste 3 ukers trend ────────────────────────────
    if len(hist) >= 3:
        recent = hist[-3:]
        if all(x > 0 for x in recent):    momentum = "ØKER"
        elif all(x < 0 for x in recent):  momentum = "FALLER"
        else:                              momentum = "BLANDET"
    else:
        momentum = "ØKER" if chg > 0 else "FALLER"

    # Hvis kildene er uenige: signal er svakere
    if agrees is False:
        momentum = "BLANDET"

    # ── COT-score: -2 til +2 (basert på vektet net_pct) ──────────
    if net_pct > 15:    cot_score = 2
    elif net_pct > 5:   cot_score = 1
    elif net_pct > -5:  cot_score = 0
    elif net_pct > -15: cot_score = -1
    else:               cot_score = -2

    # Juster for momentum
    if chg > 0 and cot_score >= 0:   cot_score = min(cot_score + 1, 2)
    elif chg < 0 and cot_score <= 0: cot_score = max(cot_score - 1, -2)

    # Hvis kildene er uenige: reduser score ett steg (usikkerhet)
    if agrees is False:
        cot_score = max(-2, min(2, cot_score - 1 if cot_score > 0 else cot_score + 1))

    result = {
        "market":    market_label,
        "net":       net,
        "net_pct":   round(net_pct, 1),
        "change":    chg,
        "bias":      bias,
        "momentum":  momentum,
        "cot_score": cot_score,
        "date":      date_val,
        "source":    source,
    }

    # Legg ved per-kilde-detaljer når begge er tilgjengelige
    if has_cftc and has_eu:
        result["sources_detail"] = {
            "euronext": {"net": eu_net, "net_pct": round(eu_net/eu_oi*100,1),
                         "oi": eu_oi, "date": eu_date, "agrees": agrees},
            "cftc":     {"net": cftc_net, "net_pct": round(cftc_net/cftc_oi*100,1),
                         "oi": cftc_oi, "date": cftc_date, "agrees": agrees},
        }
        result["agrees"] = agrees

    return result

def combine_outlook(weather_score, cot_score, crop_key, lat,
                    yield_score=None, enso_adj=0):
    """
    Kombinerer vær, COT, yield og ENSO til endelig prisretning.
    Vær: positivt score = forstyrrelser = bullish for prisen
    COT: positivt score = spekulanter er long = bullish
    Yield: lav yield = bullish for pris (knapphet)
    ENSO: kjent negativ impakt = bullish for pris
    """
    total = weather_score + cot_score + enso_adj

    # Yield-justering: svak yield → bullish for pris
    if yield_score is not None:
        if yield_score < 40:
            total += 1.5
        elif yield_score < 55:
            total += 1
        elif yield_score < 70:
            total += 0.5
        elif yield_score >= 85:
            total -= 0.5

    total = round(total, 1)

    if total >= 3:
        signal, color = "STERKT BULLISH", "bull"
    elif total >= 1:
        signal, color = "BULLISH", "bull"
    elif total <= -3:
        signal, color = "STERKT BEARISH", "bear"
    elif total <= -1:
        signal, color = "BEARISH", "bear"
    else:
        signal, color = "NØYTRAL", "neutral"

    return {"signal": signal, "color": color, "total_score": total}

# ── Hoved-logikk ─────────────────────────────────────────────────
print("Henter landbruksdata...")

with open(REGIONS_FILE) as f:
    regions = json.load(f)

with open(COMBINED_FILE) as f:
    cot_data = json.load(f)

euronext_data = load_euronext_cot()
if euronext_data:
    print(f"  Euronext COT lastet: {', '.join(euronext_data.keys())}")
else:
    print("  Euronext COT: ikke tilgjengelig — bruker CFTC for alle avlinger")

today = datetime.now(timezone.utc)
today_str = today.strftime("%Y-%m-%d")

# ── Sesong-cache: arkivvær + ENSO hentes maks 1× per dag ─────────
# Historisk vær og ENSO endres ikke i løpet av en dag, så vi cacher
# resultatene og hopper over arkiv-kall hvis cachen er fra i dag.
season_cache = {}
cache_hit = False
today_date = today.strftime("%Y-%m-%d")
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE) as f:
            season_cache = json.load(f)
        if season_cache.get("date") == today_date:
            cache_hit = True
            print(f"  Sesong-cache: bruker dagens cache ({today_date})")
    except Exception:
        season_cache = {}

# Hent ENSO-data (fra cache eller nett)
if cache_hit and "enso" in season_cache:
    enso_data = season_cache["enso"]
    print(f"  ENSO (cache): {enso_data['phase']} (ONI={enso_data['oni_value']:+.2f})")
else:
    print("  Henter ENSO-data...")
    enso_data = fetch_enso()
    if enso_data:
        print(f"  ENSO: {enso_data['phase']} (ONI={enso_data['oni_value']:+.2f}, {enso_data['period']})")
    else:
        print("  ENSO: ikke tilgjengelig")

# Per-avling aggregering
crop_region_data  = {}   # crop_key → liste med region-scores
crop_cot_cache    = {}   # crop_key → COT-data (hent én gang)
archive_cache     = {}   # region_id → arkiv-data (én gang per region)

result_regions = []

for region in regions:
    rid   = region["id"]
    lat   = region["lat"]
    lon   = region["lon"]
    crops = REGION_CROPS.get(rid, [])
    stages_array = region.get("stages", [])

    print(f"  {region['name']} ({lat},{lon})...")
    weather_raw = fetch_weather(lat, lon)

    # Sjekk om noen avling i regionen er i aktiv sesong
    growth_info = detect_growth_stage(stages_array, MONTH)
    any_active = growth_info["in_season"]

    # Hent arkivvær for sesongen (kun hvis aktiv sesong)
    # Bruker cache hvis tilgjengelig fra i dag
    archive_data = None
    if any_active and growth_info.get("season_start_month"):
        if cache_hit and rid in season_cache.get("archives", {}):
            archive_data = season_cache["archives"][rid]
        else:
            start_m = growth_info["season_start_month"]
            year = today.year
            if start_m > MONTH:
                year -= 1  # Sesongen startet forrige år
            start_date = f"{year}-{start_m:02d}-01"
            end_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
            if start_date < end_date:
                archive_data = fetch_archive_weather(lat, lon, start_date, end_date)
                time.sleep(0.3)  # Rate-limiting
        archive_cache[rid] = archive_data

    region_out = {
        "id":    rid,
        "name":  region["name"],
        "lat":   lat,
        "lon":   lon,
        "crops": crops,
        "growth_stage": growth_info,
        "crops_outlook": {},
    }

    # ENSO-impakt for denne regionen
    enso_impact = None
    enso_adj = 0
    if enso_data and enso_data["phase"] != "Nøytral":
        eff = ENSO_IMPACTS.get((enso_data["phase"], rid))
        if eff:
            enso_impact = f"{enso_data['phase']}: {eff['impact']}"
            enso_adj = eff["adj"]
    region_out["enso_impact"] = enso_impact

    # Lagre current weather summary (felles for alle avlinger i regionen)
    if weather_raw:
        curr = weather_raw.get("current", {})
        region_out["current_weather"] = {
            "temp":     curr.get("temperature_2m"),
            "precip":   curr.get("precipitation"),
            "wind":     curr.get("wind_speed_10m"),
            "humidity": curr.get("relative_humidity_2m"),
        }
    else:
        region_out["current_weather"] = None

    for crop_key in crops:
        wx    = score_weather(weather_raw, crop_key, lat)
        cot   = crop_cot_cache.get(crop_key)
        if cot is None:
            cot = get_cot_for_crop(crop_key, cot_data, euronext_data)
            crop_cot_cache[crop_key] = cot

        # Sesongmetrikker og yield-estimat
        season_metrics = None
        yield_score_val = None
        yield_rating = None
        yield_hint = None
        if archive_data and growth_info["in_season"]:
            season_metrics = calculate_season_metrics(archive_data, crop_key)
            if season_metrics:
                yield_score_val, yield_rating, yield_hint = estimate_yield_quality(
                    season_metrics, growth_info["season_pct"])

        cot_score = cot["cot_score"] if cot else 0
        outlook = combine_outlook(wx["score"], cot_score, crop_key, lat,
                                  yield_score=yield_score_val, enso_adj=enso_adj)

        region_out["crops_outlook"][crop_key] = {
            "weather":  wx,
            "cot":      cot,
            "outlook":  outlook,
            "season_metrics": season_metrics,
            "yield_quality": yield_rating,
            "yield_score": yield_score_val,
            "yield_hint": yield_hint,
        }

        # Legg til for aggregering
        if crop_key not in crop_region_data:
            crop_region_data[crop_key] = []
        crop_region_data[crop_key].append({
            "region":        rid,
            "region_name":   region["name"],
            "weather_score": wx["score"],
            "weather_outlook": wx["outlook"],
            "weather_summary": wx["summary"],
            "precip_7d":     wx["precip_7d"],
            "temp_max_avg":  wx["temp_max_avg"],
            "season_mult":   wx["season_mult"],
            "growth_stage":  growth_info,
            "season_metrics": season_metrics,
            "yield_score":   yield_score_val,
            "yield_rating":  yield_rating,
            "yield_hint":    yield_hint,
            "enso_impact":   enso_impact,
            "enso_adj":      enso_adj,
        })

    result_regions.append(region_out)

# ── Per-avling sammendrag ─────────────────────────────────────────
crop_summary = []

for crop_key, meta in CROP_META.items():
    region_list = crop_region_data.get(crop_key, [])
    cot         = crop_cot_cache.get(crop_key)

    if not region_list and not cot:
        continue

    # Vekt-snitt av vær-score (sesongmultiplikator teller allerede)
    if region_list:
        avg_wx_score = round(sum(r["weather_score"] for r in region_list) / len(region_list), 1)
        risk_regions = [r for r in region_list if r["weather_score"] >= 2]
        worst_region = max(region_list, key=lambda r: r["weather_score"]) if region_list else None
    else:
        avg_wx_score = 0
        risk_regions = []
        worst_region = None

    cot_score = cot["cot_score"] if cot else 0

    # Aggreger vekststadium og yield på tvers av regioner (bruk verste/mest representative)
    active_regions = [r for r in region_list if r.get("growth_stage", {}).get("in_season")]
    best_growth = None
    best_metrics = None
    avg_yield = None
    avg_enso_adj = 0

    if active_regions:
        # Bruk regionen med mest data som representativ
        best_r = max(active_regions, key=lambda r: (r.get("season_metrics") or {}).get("days_measured", 0))
        best_growth = best_r.get("growth_stage")
        best_metrics = best_r.get("season_metrics")
        # Snitt av yield-score og enso-adj
        yield_scores = [r["yield_score"] for r in active_regions if r.get("yield_score") is not None]
        avg_yield = round(sum(yield_scores) / len(yield_scores)) if yield_scores else None
        enso_adjs = [r.get("enso_adj", 0) for r in active_regions]
        avg_enso_adj = sum(enso_adjs) / len(enso_adjs) if enso_adjs else 0
    elif region_list:
        # Alle i av-sesong — bruk første region sin growth_stage
        best_growth = region_list[0].get("growth_stage")

    outlook = combine_outlook(avg_wx_score, cot_score, crop_key, 45,
                              yield_score=avg_yield, enso_adj=avg_enso_adj)

    # Yield-rating basert på gjennomsnittlig score
    yield_rating = None
    yield_hint = None
    if avg_yield is not None:
        if avg_yield >= 85:
            yield_rating, yield_hint = "Utmerket", "Høy produksjon → stabilt prisnivå"
        elif avg_yield >= 70:
            yield_rating, yield_hint = "God", "Normal produksjon → moderate priser"
        elif avg_yield >= 55:
            yield_rating, yield_hint = "Middels", "Noen utfordringer → mulig prispress oppover"
        elif avg_yield >= 40:
            yield_rating, yield_hint = "Svak", "Dårlige forhold → potensielt høyere priser"
        else:
            yield_rating, yield_hint = "Kritisk", "Alvorlige problemer → forvent prisøkning"
        if best_growth and best_growth.get("season_pct", 0) < 20:
            yield_rating = f"{yield_rating} (tidlig)"

    # Bygg prisdriver-tekst
    drivers = []
    if worst_region and worst_region["weather_score"] >= 2:
        drivers.append(f"Værstress i {worst_region['region_name']} ({worst_region['weather_outlook']})")
    if len(risk_regions) >= 2:
        drivers.append(f"{len(risk_regions)} risiko-regioner")
    if cot and cot["bias"] == "bull" and cot["momentum"] == "ØKER":
        drivers.append(f"COT: spekulanter øker long (net {cot['net_pct']:+.0f}% av OI)")
    elif cot and cot["bias"] == "bear" and cot["momentum"] == "FALLER":
        drivers.append(f"COT: spekulanter øker short (net {cot['net_pct']:+.0f}% av OI)")
    elif cot:
        drivers.append(f"COT: {cot['bias']} {cot['momentum']} (net {cot['net_pct']:+.0f}%)")
    # Yield-driver
    if yield_rating and "Svak" in yield_rating or yield_rating and "Kritisk" in yield_rating:
        drivers.append(f"Yield {yield_rating.lower()} — risiko for lav produksjon")
    elif yield_rating and "Utmerket" in yield_rating:
        drivers.append(f"Yield {yield_rating.lower()} — god produksjon holder prisene nede")
    # ENSO-driver
    enso_impacts_crop = [r.get("enso_impact") for r in region_list if r.get("enso_impact")]
    if enso_impacts_crop:
        drivers.append(enso_impacts_crop[0])  # bruk første match

    crop_summary.append({
        "crop_key":       crop_key,
        "navn":           meta["navn"],
        "ikon":           meta["ikon"],
        "outlook":        outlook,
        "avg_wx_score":   avg_wx_score,
        "cot_score":      cot_score,
        "risk_regions":   len(risk_regions),
        "total_regions":  len(region_list),
        "cot":            cot,
        "drivers":        drivers,
        "worst_region":   worst_region,
        # Nye felter
        "growth_stage":       best_growth.get("stage_no") if best_growth else None,
        "growth_stage_icon":  best_growth.get("icon") if best_growth else None,
        "growth_stage_pct":   best_growth.get("season_pct") if best_growth else None,
        "in_season":          best_growth.get("in_season") if best_growth else False,
        "season_months":      best_growth.get("season_months") if best_growth else None,
        "harvest_window":     best_growth.get("harvest_window") if best_growth else None,
        "gdd_accumulated":    best_metrics.get("gdd_accumulated") if best_metrics else None,
        "gdd_required":       best_metrics.get("gdd_required") if best_metrics else None,
        "gdd_pct":            best_metrics.get("gdd_pct") if best_metrics else None,
        "season_precip_mm":   best_metrics.get("season_precip_mm") if best_metrics else None,
        "ideal_precip_mm":    best_metrics.get("ideal_precip_mm") if best_metrics else None,
        "precip_pct":         best_metrics.get("precip_pct") if best_metrics else None,
        "stress_days":        best_metrics.get("stress_days") if best_metrics else None,
        "yield_quality":      yield_rating,
        "yield_score":        avg_yield,
        "yield_hint":         yield_hint,
    })
    print(f"  {meta['ikon']} {meta['navn']:15} → {outlook['signal']:16} (vær={avg_wx_score:+.1f} COT={cot_score:+d} yield={avg_yield or '?'})")

# Sorter: sterkt bullish først, deretter bullish, nøytral, bearish
order = {"STERKT BULLISH": 0, "BULLISH": 1, "NØYTRAL": 2, "BEARISH": 3, "STERKT BEARISH": 4}
crop_summary.sort(key=lambda x: order.get(x["outlook"]["signal"], 2))

_cot_dates = [(c.get("cot") or {}).get("date") for c in crop_summary if (c.get("cot") or {}).get("date")]
_cot_date  = max(_cot_dates) if _cot_dates else None

output = {
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "cot_date":  _cot_date,
    "source":    "CFTC · Euronext · Open-Meteo · NOAA ENSO",
    "month":     MONTH,
    "enso":      enso_data,
    "crop_summary": crop_summary,
    "regions":   result_regions,
}

with open(OUT, "w") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# Lagre sesong-cache (arkivvær + ENSO) for gjenbruk resten av dagen
if not cache_hit:
    try:
        cache_out = {
            "date": today_date,
            "enso": enso_data,
            "archives": {rid: data for rid, data in archive_cache.items() if data},
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(cache_out, f, ensure_ascii=False)
        print(f"  Sesong-cache lagret ({len(cache_out['archives'])} regioner)")
    except Exception as e:
        print(f"  Cache-lagring feilet: {e}")

print(f"\nOK → {OUT}  ({len(crop_summary)} avlinger, {len(result_regions)} regioner)")
