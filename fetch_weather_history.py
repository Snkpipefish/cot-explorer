#!/usr/bin/env python3
"""
fetch_weather_history.py — henter 15 års værhistorikk fra Open-Meteo Archive (ERA5).

Én gang per region. Lagrer monthly aggregates for å redusere disk-bruk:
  data/agri_history/{region_id}.json

Variables hentet (daglig) og aggregert per måned:
  temperature_2m_mean   — gjennomsnittstemp
  temperature_2m_max    — maks-temp (heat stress)
  precipitation_sum     — total nedbør
  et0_fao_evapotranspiration — fordampning (water balance)

Kan re-kjøres trygt — appender kun manglende år.
Kjøring:
  python3 fetch_weather_history.py             — alle regioner, 15 år
  python3 fetch_weather_history.py --years 20  — 20 år
  python3 fetch_weather_history.py --region us_cornbelt   — spesifikk region
"""
import json
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

BASE        = Path(__file__).parent
REGIONS_F   = BASE / "data" / "geointel" / "agri_regions.json"
OUT_DIR     = BASE / "data" / "agri_history"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_YEARS = 15
RATE_LIMIT_S  = 5.0   # Open-Meteo Archive rate-limit: bør respekteres

VARIABLES = [
    "temperature_2m_mean",
    "temperature_2m_max",
    "precipitation_sum",
    "et0_fao_evapotranspiration",
]


def _fetch_archive(lat, lon, start_date, end_date):
    params = urllib.parse.urlencode({
        "latitude":  lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date":   end_date,
        "daily":      ",".join(VARIABLES),
        "timezone":   "UTC",
    })
    url = f"https://archive-api.open-meteo.com/v1/archive?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code}: {e.reason}")
    except Exception as e:
        print(f"    FEIL: {e}")
    return None


def _monthly_aggregate(daily_data):
    """Aggreger daglig data til månedlige metrikker.

    Returnerer dict: {"YYYY-MM": {metrikk: verdi, ...}}
    """
    if not daily_data or "daily" not in daily_data:
        return {}
    d = daily_data["daily"]
    times = d.get("time", [])
    if not times:
        return {}

    months = {}
    for i, t in enumerate(times):
        # t format: "YYYY-MM-DD"
        ym = t[:7]
        if ym not in months:
            months[ym] = {
                "temp_sum": 0.0, "temp_max_max": float("-inf"),
                "precip_sum": 0.0, "et0_sum": 0.0,
                "days": 0, "hot_days": 0, "dry_days": 0, "wet_days": 0,
            }
        m = months[ym]
        temp = (d.get("temperature_2m_mean") or [None])[i]
        tmax = (d.get("temperature_2m_max")  or [None])[i]
        prec = (d.get("precipitation_sum")    or [None])[i]
        et0  = (d.get("et0_fao_evapotranspiration") or [None])[i]

        if temp is not None:
            m["temp_sum"] += temp
            m["days"] += 1
        if tmax is not None:
            m["temp_max_max"] = max(m["temp_max_max"], tmax)
            if tmax > 32:   # varme-stress-dag terskel (crop-generisk)
                m["hot_days"] += 1
        if prec is not None:
            m["precip_sum"] += prec
            if prec < 1:
                m["dry_days"] += 1
            elif prec > 10:
                m["wet_days"] += 1
        if et0 is not None:
            m["et0_sum"] += et0

    # Normaliser til per-måned-metrikker
    out = {}
    for ym, m in months.items():
        if m["days"] == 0:
            continue
        out[ym] = {
            "temp_mean":   round(m["temp_sum"] / m["days"], 2),
            "temp_max":    round(m["temp_max_max"], 1) if m["temp_max_max"] > -100 else None,
            "precip_mm":   round(m["precip_sum"], 1),
            "et0_mm":      round(m["et0_sum"], 1),
            "hot_days":    m["hot_days"],
            "dry_days":    m["dry_days"],
            "wet_days":    m["wet_days"],
            "water_bal":   round(m["precip_sum"] - m["et0_sum"], 1),  # P - ET0
            "days":        m["days"],
        }
    return out


def _fetch_region(region, years):
    rid  = region["id"]
    lat  = region["lat"]
    lon  = region["lon"]
    out_file = OUT_DIR / f"{rid}.json"

    existing = {}
    if out_file.exists():
        try:
            existing = json.loads(out_file.read_text(encoding="utf-8")).get("monthly", {})
        except Exception:
            existing = {}

    today = date.today()
    start = date(today.year - years, 1, 1)
    end   = today - timedelta(days=1)

    # Hvis vi allerede har siste 30 dager, hopp over (resten er arkiv og endres ikke)
    last_month_key = end.strftime("%Y-%m")
    if last_month_key in existing:
        # Sjekk om vi har 13+ måneder tilbake i tid
        prev_year_key = (end - timedelta(days=365)).strftime("%Y-%m")
        if prev_year_key in existing:
            print(f"  {rid}: up-to-date ({len(existing)} måneder i cache), hopper over")
            return existing

    print(f"  {rid}: henter {start} → {end} ({region['name']})")
    # Del opp i 5-års-biter (Open-Meteo Archive har grenser på størrelse)
    chunks = []
    cur = start
    while cur < end:
        chunk_end = date(min(cur.year + 5, end.year), 12, 31)
        if chunk_end > end:
            chunk_end = end
        chunks.append((cur.isoformat(), chunk_end.isoformat()))
        cur = date(chunk_end.year + 1, 1, 1)

    monthly = dict(existing)   # Start med eksisterende cache
    for s, e in chunks:
        # Hopp over hvis vi allerede har alle måneder i denne bolken
        start_m = s[:7]
        end_m   = e[:7]
        need = False
        y1, m1 = int(start_m[:4]), int(start_m[5:7])
        y2, m2 = int(end_m[:4]),   int(end_m[5:7])
        cy, cm = y1, m1
        while (cy, cm) <= (y2, m2):
            k = f"{cy:04d}-{cm:02d}"
            if k not in monthly:
                need = True
                break
            cm += 1
            if cm > 12:
                cm = 1
                cy += 1
        if not need:
            continue

        data = _fetch_archive(lat, lon, s, e)
        if data:
            new_monthly = _monthly_aggregate(data)
            monthly.update(new_monthly)
            print(f"    {s} → {e}: {len(new_monthly)} nye måneder")
        time.sleep(RATE_LIMIT_S)

    # Lagre
    output = {
        "region_id":  rid,
        "name":       region["name"],
        "lat":        lat,
        "lon":        lon,
        "updated":    datetime.now(timezone.utc).isoformat(),
        "monthly":    monthly,
    }
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    lagret {len(monthly)} måneder → {out_file.name}")
    return monthly


def main():
    years = DEFAULT_YEARS
    region_filter = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--years" and i + 1 < len(sys.argv):
            years = int(sys.argv[i + 1])
        elif arg == "--region" and i + 1 < len(sys.argv):
            region_filter = sys.argv[i + 1]

    if not REGIONS_F.exists():
        print(f"FEIL: {REGIONS_F} mangler")
        sys.exit(1)
    regions = json.loads(REGIONS_F.read_text(encoding="utf-8"))
    if region_filter:
        regions = [r for r in regions if r["id"] == region_filter]
        if not regions:
            print(f"FEIL: region '{region_filter}' ikke funnet")
            sys.exit(1)

    print(f"[Weather history] {len(regions)} regioner, {years} år")
    for region in regions:
        _fetch_region(region, years)
    print(f"Ferdig. Data i {OUT_DIR}")


if __name__ == "__main__":
    main()
