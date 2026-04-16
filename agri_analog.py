"""
agri_analog.py — historisk analog-år-matching for agri-signaler.

Gir to verdier til scoring:
  1. KORRELASJON  — Pearson-korr mellom weather-metric og pris-endring next-N-måneder,
                    beregnet én gang per crop/region/metric.
  2. ANALOG       — dagens sesongs vær sammenlignes mot historiske sesonger med K-NN;
                    topp-3 nærmeste gir forventet pris-bane (median, std).

Input:
  data/agri_history/{region_id}.json  — monthly værhistorikk (fetch_weather_history.py)
  data/prices/{crop}.json             — ukentlig close-historikk (build_price_history.py)

Output-funksjoner:
  compute_correlation_table(crop, region, months_fwd)
  find_analog_years(crop, region, current_features, k=3)
  analog_direction_score(crop, region, direction)  — driver-sum 0-1 for push_agri_signals
"""
from __future__ import annotations

import json
import math
from datetime import datetime, date
from pathlib import Path
from typing import Optional


BASE          = Path(__file__).parent
HISTORY_DIR   = BASE / "data" / "agri_history"
PRICES_DIR    = BASE / "data" / "prices"


# ─── Crop → region mapping (hvilke regioner er mest kritiske per crop) ──

CROP_REGIONS = {
    "corn":     ["us_cornbelt", "brazil_mato_grosso", "ukraine_blacksea"],
    "wheat":    ["us_great_plains", "ukraine_blacksea", "eu_northern", "canada_prairie"],
    "soybeans": ["brazil_mato_grosso", "us_cornbelt", "argentina_pampas"],
    "sugar":    ["india_punjab", "brazil_coffee"],
    "coffee":   ["brazil_coffee"],
    "cocoa":    ["west_africa_cocoa"],
    "cotton":   ["us_delta_cotton"],
}

# Crop → vekst-sesong (måneder 1-12). Samme som fetch_agri REGION_CROPS
# logikk men crop-sentrert (ikke region-sentrert).
CROP_SEASON_MONTHS = {
    "corn":     (4, 10),    # plant april → høst oktober (nordlig halvkule)
    "wheat":    (4, 8),     # vår-vekst → juli høst
    "soybeans": (5, 10),
    "sugar":    (5, 11),
    "coffee":   (9, 5),     # wrap-around Brazil: sept-mai (følgende år)
    "cocoa":    (10, 3),    # W-Afrika main crop oct-march
    "cotton":   (5, 10),
}

# Crop → fil i data/prices/
_CROP_PRICE_FILE = {
    "corn":     "corn.json",
    "wheat":    "wheat.json",
    "soybeans": "soybean.json",
    "sugar":    "sugar.json",
    "coffee":   "coffee.json",
    "cocoa":    "cocoa.json",
    "cotton":   None,   # ikke tilgjengelig
}


# ─── Hjelpere ────────────────────────────────────────────────────────────

def _load_region_weather(region_id: str) -> dict:
    """Returnerer {YYYY-MM: metrics} eller {}"""
    f = HISTORY_DIR / f"{region_id}.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("monthly", {})
    except Exception:
        return {}


def _load_crop_prices(crop_key: str) -> list[tuple[date, float]]:
    """Returnerer liste av (date, price) sortert eldst først."""
    fname = _CROP_PRICE_FILE.get(crop_key)
    if not fname:
        return []
    f = PRICES_DIR / fname
    if not f.exists():
        return []
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        out = []
        for e in d.get("data", []):
            try:
                dt = datetime.strptime(e["date"], "%Y-%m-%d").date()
                out.append((dt, float(e["price"])))
            except (ValueError, KeyError):
                continue
        out.sort(key=lambda x: x[0])
        return out
    except Exception:
        return []


def _price_at(prices: list[tuple[date, float]], target: date) -> Optional[float]:
    """Nærmeste pris på eller etter target-dato (max 7 dager frem)."""
    for dt, p in prices:
        if dt >= target:
            if (dt - target).days <= 14:
                return p
            return None
    return None


# ─── Season-features per år ──────────────────────────────────────────────

def _extract_season_features(weather_monthly: dict, year: int,
                             start_month: int, end_month: int) -> dict | None:
    """Aggreger vær-metrics over én sesong (år Y, måneder start→end).

    Returnerer dict med metrics eller None hvis data mangler."""
    # Bygg liste av (year, month) nøkler for sesongen
    months = []
    if start_month <= end_month:
        # Standard sesong (samme år)
        for m in range(start_month, end_month + 1):
            months.append(f"{year:04d}-{m:02d}")
    else:
        # Wrap-around (f.eks. coffee sept-mai)
        for m in range(start_month, 13):
            months.append(f"{year:04d}-{m:02d}")
        for m in range(1, end_month + 1):
            months.append(f"{year + 1:04d}-{m:02d}")

    available = [weather_monthly[k] for k in months if k in weather_monthly]
    if len(available) < len(months) * 0.75:
        return None  # < 75 % måneder tilgjengelig → skip

    total_precip   = sum(m["precip_mm"] for m in available)
    total_et0      = sum(m["et0_mm"] for m in available)
    mean_temp      = sum(m["temp_mean"] for m in available) / len(available)
    max_temp       = max(m["temp_max"] for m in available if m["temp_max"] is not None)
    hot_days       = sum(m["hot_days"] for m in available)
    dry_days       = sum(m["dry_days"] for m in available)
    wet_days       = sum(m["wet_days"] for m in available)
    water_bal      = total_precip - total_et0

    return {
        "year":           year,
        "months":         len(available),
        "precip_mm":      round(total_precip, 1),
        "mean_temp":      round(mean_temp, 2),
        "max_temp":       round(max_temp, 1),
        "hot_days":       hot_days,
        "dry_days":       dry_days,
        "wet_days":       wet_days,
        "water_balance":  round(water_bal, 1),
    }


# ─── Korrelasjons-analyse ────────────────────────────────────────────────

def _pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson-r. Returnerer 0 hvis < 3 par."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0 or deny == 0:
        return 0.0
    return num / (denx * deny)


def compute_correlation_table(crop_key: str, months_forward: int = 3) -> dict:
    """For hver feature: r mellom sesongs-metric og pris-endring neste N måneder.

    Returnerer dict:
      {"region_id": {"metric": {"r": -0.45, "n": 15, "interpretation": "bullish"}}}
    """
    prices = _load_crop_prices(crop_key)
    if len(prices) < 52:
        return {}
    season_start, season_end = CROP_SEASON_MONTHS.get(crop_key, (4, 10))
    regions = CROP_REGIONS.get(crop_key, [])
    if not regions:
        return {}

    out = {}
    for region in regions:
        weather = _load_region_weather(region)
        if not weather:
            continue
        # Samle features + pris-endring per år
        years = sorted({int(k[:4]) for k in weather.keys()})
        feature_rows = []
        price_changes = []

        for yr in years:
            feat = _extract_season_features(weather, yr, season_start, season_end)
            if not feat:
                continue

            # Pris ved sesong-slutt og pris N mnd frem
            end_m = season_end if season_start <= season_end else season_end
            end_y = yr + 1 if season_start > season_end else yr
            season_end_date = date(end_y, end_m, 15)
            later_month = end_m + months_forward
            later_year  = end_y
            while later_month > 12:
                later_month -= 12
                later_year += 1
            later_date = date(later_year, later_month, 15)

            p0 = _price_at(prices, season_end_date)
            p1 = _price_at(prices, later_date)
            if p0 is None or p1 is None or p0 <= 0:
                continue
            change_pct = (p1 - p0) / p0 * 100

            feature_rows.append(feat)
            price_changes.append(change_pct)

        if len(feature_rows) < 5:
            continue

        # Beregn Pearson r per feature
        metrics = ["precip_mm", "mean_temp", "max_temp", "hot_days",
                   "dry_days", "wet_days", "water_balance"]
        region_out = {}
        for m in metrics:
            xs = [r[m] for r in feature_rows]
            r = _pearson(xs, price_changes)
            interp = ("bullish" if r > 0.35 else
                      "bearish" if r < -0.35 else "nøytral")
            region_out[m] = {
                "r":             round(r, 3),
                "n":             len(xs),
                "interpretation": interp,
                # Skjæringshøyde for "høy" vs "lav" kategori (median)
                "median":        round(sorted(xs)[len(xs) // 2], 2),
            }
        region_out["_meta"] = {
            "years":          len(feature_rows),
            "price_change_mean": round(sum(price_changes) / len(price_changes), 2),
            "price_change_std":  round(
                math.sqrt(sum((c - sum(price_changes) / len(price_changes)) ** 2
                              for c in price_changes) / len(price_changes)), 2),
        }
        out[region] = region_out
    return out


# ─── Analog-matching ─────────────────────────────────────────────────────

def _normalize(values: list[float]) -> tuple[list[float], float, float]:
    """Z-score normalisering. Returnerer (normalized, mean, std)."""
    if not values:
        return [], 0.0, 0.0
    m = sum(values) / len(values)
    sd = math.sqrt(sum((v - m) ** 2 for v in values) / len(values))
    if sd == 0:
        return [0.0] * len(values), m, 0.0
    return [(v - m) / sd for v in values], m, sd


def find_analog_years(crop_key: str, region: str,
                      current_month: int, k: int = 3) -> dict:
    """Finn topp-K analog-år basert på current sesong-til-dato features.

    Returnerer:
      {
        "analogs": [
          {"year": 2012, "similarity": 0.87, "price_trajectory_30d": +12.3, "price_trajectory_90d": +34.1},
          ...
        ],
        "consensus_direction": "bullish",
        "consensus_median_90d_pct": 13.2,
        "consensus_range_90d_pct": [4.0, 34.1],
      }
    """
    weather = _load_region_weather(region)
    prices  = _load_crop_prices(crop_key)
    if not weather or not prices:
        return {}

    season_start, season_end = CROP_SEASON_MONTHS.get(crop_key, (4, 10))

    # Bestem sesongens "partial"-slutt — nåværende måned (dekker det vi har så langt)
    today_year = date.today().year
    # Hvis vi er i sesongen nå, bruk current_month; ellers forrige sesong
    partial_end = current_month
    if season_start <= season_end:
        # Standard sesong
        if current_month < season_start:
            # Pre-sesong — return tom
            return {}
        if current_month > season_end:
            partial_end = season_end
    else:
        # Wrap-around — mer kompleks, forenklet: bruk hele siste sesong
        partial_end = season_end

    # Current-sesongens features (fra season_start til current_month inneværende år)
    current_year = today_year
    if season_start > season_end and current_month <= season_end:
        # Vi er i andre del av wrap-around-sesong
        current_year = today_year - 1
    current_feat = _extract_season_features(weather, current_year,
                                            season_start, partial_end)
    if not current_feat:
        return {}

    # Finn alle historiske år med komplette sesonger
    years = sorted({int(k[:4]) for k in weather.keys()})
    historical_feats = []
    for yr in years:
        if yr == current_year:
            continue
        feat = _extract_season_features(weather, yr, season_start, partial_end)
        if feat:
            historical_feats.append(feat)

    if len(historical_feats) < 3:
        return {}

    # Bygg feature-vektor — fokuser på akkumulerte metrics over partial-sesongen
    metrics = ["precip_mm", "mean_temp", "hot_days", "dry_days", "water_balance"]
    # Normaliser hver metric over alle historiske år
    per_metric_norm = {}
    for m in metrics:
        hist_vals = [f[m] for f in historical_feats]
        _, mean, std = _normalize(hist_vals)
        per_metric_norm[m] = (mean, std)

    def _vec(feat):
        return [((feat[m] - per_metric_norm[m][0]) /
                 per_metric_norm[m][1]) if per_metric_norm[m][1] > 0 else 0
                for m in metrics]

    current_vec = _vec(current_feat)

    # K-NN: Euklidsk avstand
    distances = []
    for f in historical_feats:
        v = _vec(f)
        d = math.sqrt(sum((a - b) ** 2 for a, b in zip(current_vec, v)))
        distances.append((f["year"], d))
    distances.sort(key=lambda x: x[1])
    top_k = distances[:k]

    # For hver analog: beregn pris-bane
    analogs = []
    season_end_m = season_end
    for yr, dist in top_k:
        # Bruk pris ved current_month (slutt på partial-sesong) som basis
        end_y = yr + 1 if season_start > season_end else yr
        ref_date = date(end_y, partial_end, 15)
        p0 = _price_at(prices, ref_date)
        if p0 is None:
            continue
        # 30 og 90 dager frem
        def _change(delta_days):
            target = date.fromordinal(ref_date.toordinal() + delta_days)
            p = _price_at(prices, target)
            if p is None or p0 <= 0:
                return None
            return round((p - p0) / p0 * 100, 2)

        traj_30 = _change(30)
        traj_60 = _change(60)
        traj_90 = _change(90)

        # Similarity = 1 / (1 + distance) — 1.0 = perfekt match
        similarity = round(1 / (1 + dist), 3)
        analogs.append({
            "year":                 yr,
            "similarity":           similarity,
            "price_trajectory_30d": traj_30,
            "price_trajectory_60d": traj_60,
            "price_trajectory_90d": traj_90,
        })

    # Konsensus basert på 90d (lengst lookout)
    valid = [a["price_trajectory_90d"] for a in analogs
             if a["price_trajectory_90d"] is not None]
    if not valid:
        return {"analogs": analogs}

    median = sorted(valid)[len(valid) // 2]
    direction = ("bullish" if median > 3 else
                 "bearish" if median < -3 else "nøytral")
    return {
        "analogs":                   analogs,
        "consensus_direction":       direction,
        "consensus_median_90d_pct":  round(median, 1),
        "consensus_range_90d_pct":   [round(min(valid), 1), round(max(valid), 1)],
        "n_valid_analogs":           len(valid),
    }


# ─── Score-produsent for push_agri_signals ───────────────────────────────

def analog_direction_score(crop_key: str, direction: str,
                           current_month: int) -> tuple[float, list[str]]:
    """Returnerer (score 0-1, drivers-tekster) for analog-komponent.

    - Finner analoger i PRIMÆR region for crop
    - Hvis konsensus matcher direction → positiv score
    - Hvis konsensus motsier direction → 0 (eller negativt, men vi kapper på 0)
    """
    regions = CROP_REGIONS.get(crop_key, [])
    if not regions:
        return 0.0, []

    # Prøv primær region først, fallback til sekundære hvis ingen treff
    result = {}
    primary = regions[0]
    for r in regions:
        result = find_analog_years(crop_key, r, current_month, k=3)
        if result.get("analogs"):
            primary = r
            break
    if not result.get("analogs"):
        return 0.0, []

    cons_dir   = result.get("consensus_direction", "nøytral")
    cons_pct   = result.get("consensus_median_90d_pct", 0)
    n_valid    = result.get("n_valid_analogs", 0)
    rng        = result.get("consensus_range_90d_pct", [0, 0])

    buy_dir  = direction in ("BUY", "buy", "bull", "long")
    sell_dir = direction in ("SELL", "sell", "bear", "short")

    score = 0.0
    drivers = []
    if cons_dir == "bullish" and buy_dir:
        score = min(abs(cons_pct) / 20.0, 1.0)   # 20 % 90d = full styrke
    elif cons_dir == "bearish" and sell_dir:
        score = min(abs(cons_pct) / 20.0, 1.0)
    else:
        return 0.0, []

    # Bygg driver-tekst med topp-3 analoger
    analogs = result["analogs"][:3]
    analog_str = ", ".join(
        f"{a['year']}({a['price_trajectory_90d']:+.1f}%)"
        for a in analogs if a['price_trajectory_90d'] is not None
    )
    drivers.append(
        f"Analog: {cons_dir} {cons_pct:+.1f}% 90d (n={n_valid}, "
        f"range {rng[0]:+.1f}..{rng[1]:+.1f}%, år: {analog_str})"
    )
    return score, drivers
