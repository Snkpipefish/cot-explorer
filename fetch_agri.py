#!/usr/bin/env python3
"""
fetch_agri.py — Avlings-analyse
Henter 7-dagers værvarsling (Open-Meteo) for alle landbruksregioner,
beregner tørkestress/flomrisiko, mapper mot COT-posisjoner og lager
en samlet prisretning per avling.

Output: data/agri/latest.json
"""

import json, os, urllib.request, urllib.parse
from datetime import datetime, timezone

BASE = os.path.expanduser("~/cot-explorer/data")
OUT  = os.path.join(BASE, "agri", "latest.json")
os.makedirs(os.path.join(BASE, "agri"), exist_ok=True)

REGIONS_FILE  = os.path.join(BASE, "geointel", "agri_regions.json")
COMBINED_FILE = os.path.join(BASE, "combined", "latest.json")

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

def get_cot_for_crop(crop_key, cot_data):
    """Henter aggregert COT-info for en avling (slår sammen relaterte markeder)."""
    markets = COT_MAP.get(crop_key, [])
    matches = [e for e in cot_data
               if any(m.lower() in e.get("market","").lower() for m in markets)]
    if not matches:
        return None

    # Bruk det markedet med høyest open interest
    main = max(matches, key=lambda e: e.get("open_interest", 0) or 0)
    sp   = main.get("spekulanter") or {}
    net  = sp.get("net", 0) or 0
    chg  = main.get("change_spec_net", 0) or 0
    oi   = main.get("open_interest", 1) or 1
    hist = main.get("spec_net_history", []) or []

    # Bias
    bias = "bull" if net > 0 else "bear"

    # Momentum: siste 3 ukers trend
    if len(hist) >= 3:
        recent = hist[-3:]
        if all(x > 0 for x in recent):
            momentum = "ØKER"
        elif all(x < 0 for x in recent):
            momentum = "FALLER"
        else:
            momentum = "BLANDET"
    else:
        momentum = "ØKER" if chg > 0 else "FALLER"

    # COT-score: -2 til +2
    net_pct = (net / oi * 100) if oi else 0
    if net_pct > 15:   cot_score = 2
    elif net_pct > 5:  cot_score = 1
    elif net_pct > -5: cot_score = 0
    elif net_pct > -15:cot_score = -1
    else:              cot_score = -2

    # Juster for momentum
    if chg > 0 and cot_score >= 0:   cot_score = min(cot_score + 1, 2)
    elif chg < 0 and cot_score <= 0: cot_score = max(cot_score - 1, -2)

    return {
        "market":    main.get("market", crop_key),
        "net":       net,
        "net_pct":   round(net_pct, 1),
        "change":    chg,
        "bias":      bias,
        "momentum":  momentum,
        "cot_score": cot_score,
        "date":      main.get("date"),
    }

def combine_outlook(weather_score, cot_score, crop_key, lat):
    """
    Kombinerer vær og COT til endelig prisretning.
    Vær: positivt score = forstyrrelser = bullish for prisen
    COT: positivt score = spekulanter er long = bullish
    """
    total = weather_score + cot_score

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

# Per-avling aggregering
crop_region_data  = {}   # crop_key → liste med region-scores
crop_cot_cache    = {}   # crop_key → COT-data (hent én gang)

result_regions = []

for region in regions:
    rid   = region["id"]
    lat   = region["lat"]
    lon   = region["lon"]
    crops = REGION_CROPS.get(rid, [])

    print(f"  {region['name']} ({lat},{lon})...")
    weather_raw = fetch_weather(lat, lon)

    region_out = {
        "id":    rid,
        "name":  region["name"],
        "lat":   lat,
        "lon":   lon,
        "crops": crops,
        "crops_outlook": {},
    }

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
            cot = get_cot_for_crop(crop_key, cot_data)
            crop_cot_cache[crop_key] = cot

        cot_score = cot["cot_score"] if cot else 0
        outlook   = combine_outlook(wx["score"], cot_score, crop_key, lat)

        region_out["crops_outlook"][crop_key] = {
            "weather":  wx,
            "cot":      cot,
            "outlook":  outlook,
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
    outlook   = combine_outlook(avg_wx_score, cot_score, crop_key, 45)  # lat=45 som default

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
    })
    print(f"  {meta['ikon']} {meta['navn']:15} → {outlook['signal']:16} (vær={avg_wx_score:+.1f} COT={cot_score:+d})")

# Sorter: sterkt bullish først, deretter bullish, nøytral, bearish
order = {"STERKT BULLISH": 0, "BULLISH": 1, "NØYTRAL": 2, "BEARISH": 3, "STERKT BEARISH": 4}
crop_summary.sort(key=lambda x: order.get(x["outlook"]["signal"], 2))

output = {
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "month":     MONTH,
    "crop_summary": crop_summary,
    "regions":   result_regions,
}

with open(OUT, "w") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nOK → {OUT}  ({len(crop_summary)} avlinger, {len(result_regions)} regioner)")
