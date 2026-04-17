"""
cot_analytics.py — disaggregated COT-analytics for POSITIONING-familien

Ren statistikk + cache-bygger. Ingen I/O i kjernen (rank_percentile, rolling_z,
oi_regime, build_asset_analytics tar dict/list-input). I/O er isolert i
load_history / build_cache / load_cache / save_cache.

Kjøres én gang per ny COT-release (ukentlig) fra fetch_all.py og cachres
i data/cot_analytics/latest.json. Scoring-hot-path leser kun fra cache.

Terminologi:
  MM   = Managed Money (spekulanter i disaggregated/TFF)
  Comm = Commercial hedgers (produsenter/kommersielle)
  OI   = Open Interest (åpne kontrakter)

Minimum historikk for pålitelig percentile: 26 uker (6 måneder). Under dette
returnerer funksjonene None og sub-signalet aktiveres ikke i scoring.
"""
from __future__ import annotations

import json
import os
import glob
from pathlib import Path
from typing import Optional


# ─── Asset → COT-marked mapping (case-normalisert) ────────────────────────

# Scoring-key → (COT-market-navn, primær rapport-type, supplemental-rapport eller None)
# Rapport-typer matcher mappestrukturen under data/<report_type>/.
ASSET_COT_MAP: list[tuple[str, str, str, Optional[str]]] = [
    # FX — TFF-rapporten (Leveraged Funds = spekulanter i TFF)
    ("EURUSD",  "euro fx",               "tff", None),
    ("GBPUSD",  "british pound",         "tff", None),
    ("USDJPY",  "japanese yen",          "tff", None),
    ("AUDUSD",  "australian dollar",     "tff", None),
    # Metaller
    ("Gold",    "gold",                  "disaggregated", None),
    ("Silver",  "silver",                "disaggregated", None),
    # Energi — NYMEX WTI for WTI, ICE Brent håndteres separat i fetch_all
    ("WTI",     "crude oil, light sweet", "disaggregated", None),
    ("Brent",   "crude oil, light sweet", "disaggregated", None),
    # Indekser
    ("SPX",     "s&p 500 consolidated",  "disaggregated", None),
    ("NAS100",  "nasdaq mini",           "disaggregated", None),
    # Grains — supplemental for Index Investor-flow
    ("Corn",    "corn",                  "disaggregated", "supplemental"),
    ("Wheat",   "wheat",                 "disaggregated", "supplemental"),
    ("Soybean", "soybeans",              "disaggregated", "supplemental"),
    ("Cotton",  "cotton",                "disaggregated", "supplemental"),
    # Softs
    ("Sugar",   "sugar",                 "disaggregated", "supplemental"),
    ("Coffee",  "coffee",                "disaggregated", None),
    ("Cocoa",   "cocoa",                 "disaggregated", None),
]

MIN_WEEKS_FOR_PCTILE = 26
DEFAULT_LOOKBACK_WEEKS = 52


# ─── Rene statistikk-funksjoner (testbare uten I/O) ────────────────────────

def rank_percentile(current: float, history: list[float]) -> Optional[float]:
    """Rank-basert percentile 0-100 (rank av `current` blant `history`).

    Returnerer None hvis færre enn MIN_WEEKS_FOR_PCTILE datapunkter.
    """
    if current is None or history is None:
        return None
    # Filtrer ut None-verdier fra historikk
    clean = [v for v in history if v is not None]
    if len(clean) < MIN_WEEKS_FOR_PCTILE:
        return None
    below_or_equal = sum(1 for v in clean if v <= current)
    return round(100 * below_or_equal / len(clean), 1)


def rolling_z(current: float, history: list[float]) -> Optional[float]:
    """Robust z-score basert på median og MAD (ikke mean/std).

    Tåler fat-tails og outliers bedre enn vanlig z-score.
    Returnerer None hvis <26 datapunkter eller MAD=0 (konstante verdier).
    """
    if current is None or history is None:
        return None
    clean = [v for v in history if v is not None]
    if len(clean) < MIN_WEEKS_FOR_PCTILE:
        return None
    s = sorted(clean)
    n = len(s)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    devs = sorted(abs(v - median) for v in clean)
    mad = devs[n // 2] if n % 2 else (devs[n // 2 - 1] + devs[n // 2]) / 2
    if mad == 0:
        return None
    # 1.4826 skalerer MAD til std-ekvivalent under normalfordeling
    return round((current - median) / (1.4826 * mad), 2)


def oi_regime(change_oi_current: float,
              change_oi_history_4w: list[float],
              direction: str) -> tuple[str, float]:
    """Klassifiser OI-trend mot handelsretning.

    Returnerer (label, avg_4w_change):
      "confirmation"  — stigende OI i retningsretning (nye penger inn)
      "warning"       — stigende OI mot retning (motstand bygges)
      "liquidation"   — tydelig fallende OI (posisjonslukking)
      "stable"        — flat OI

    `change_oi_history_4w` er opptil 4 siste ukers change_oi-verdier
    (inkluderer gjerne gjeldende uke).
    """
    hist = [v for v in (change_oi_history_4w or []) if v is not None]
    if not hist:
        hist = [change_oi_current or 0]
    avg4w = sum(hist) / len(hist)
    is_rising = avg4w > 0
    is_bull = direction in ("buy", "bull", "long")

    if is_rising:
        return ("confirmation", round(avg4w, 0)) if is_bull else ("warning", round(avg4w, 0))
    # Kun "liquidation" hvis tydelig fallende, ikke bare støy rundt 0
    cur = change_oi_current or 0
    if avg4w < 0 and abs(avg4w) > abs(cur) * 0.3:
        return ("liquidation", round(avg4w, 0))
    return ("stable", round(avg4w, 0))


def index_investor_bias(idx_net: Optional[float],
                        open_interest: Optional[float]) -> Optional[str]:
    """Returner "structural_long" / "structural_short" / None basert på indeksfond-
    posisjonering som andel av OI. Krever > 5 % net-of-OI og positivt OI.
    """
    if not idx_net or not open_interest or open_interest <= 0:
        return None
    pct = idx_net / open_interest * 100
    if pct > 5:
        return "structural_long"
    if pct < -5:
        return "structural_short"
    return None


def build_asset_analytics(asset_key: str,
                          report_type: str,
                          latest_entry: dict,
                          history_entries: list[dict],
                          supplemental_entry: Optional[dict] = None,
                          lookback_weeks: int = DEFAULT_LOOKBACK_WEEKS) -> dict:
    """Bygg analytics-dict for én asset. Tar forhåndslastede entries — ingen I/O.

    `history_entries` må være sortert kronologisk (eldste først).
    `supplemental_entry` er valgfritt (kun for grains/sugar — for Index-flow).
    """
    # Begrens til lookback-vinduet (de N siste entries)
    hist = history_entries[-lookback_weeks:] if len(history_entries) > lookback_weeks \
           else history_entries

    # MM-historikk (spekulanter-feltet finnes i både disaggregated og TFF)
    mm_hist = [(e.get("spekulanter") or {}).get("net") for e in hist]

    # Commercial-historikk: "produsenter" i disaggregated, "kommersielle" i legacy/supp.
    comm_hist = []
    for e in hist:
        prod = (e.get("produsenter") or {}).get("net")
        if prod is None:
            prod = (e.get("kommersielle") or {}).get("net")
        comm_hist.append(prod)

    # Spread for divergens-z
    spread_hist = []
    for mm, c in zip(mm_hist, comm_hist):
        if mm is not None and c is not None:
            spread_hist.append(mm - c)

    # OI endring-historikk (siste 4 uker for regime-vurdering)
    oi_change_hist_4w = [(e.get("change_oi") or 0) for e in hist[-4:]]

    # Gjeldende verdier
    mm_now = (latest_entry.get("spekulanter") or {}).get("net")
    comm_now = (latest_entry.get("produsenter") or {}).get("net")
    if comm_now is None:
        comm_now = (latest_entry.get("kommersielle") or {}).get("net")
    oi_now = latest_entry.get("open_interest")
    change_oi_now = latest_entry.get("change_oi") or 0

    mm_comm_spread_now = None
    if mm_now is not None and comm_now is not None:
        mm_comm_spread_now = mm_now - comm_now

    # Index investor-bias fra supplemental (hvis tilgjengelig)
    idx_bias = None
    if supplemental_entry:
        idx_net = (supplemental_entry.get("indeksfond") or {}).get("net")
        idx_oi = supplemental_entry.get("open_interest")
        idx_bias = index_investor_bias(idx_net, idx_oi)

    result = {
        "cot_date":               latest_entry.get("date"),
        "report_type":            report_type,
        "mm_net":                 mm_now,
        "mm_net_pctile_52w":      rank_percentile(mm_now, mm_hist),
        "mm_comm_divergence_z":   (rolling_z(mm_comm_spread_now, spread_hist)
                                   if mm_comm_spread_now is not None else None),
        "oi_now":                 oi_now,
        "change_oi_current":      change_oi_now,
        "oi_change_4w_avg":       round(sum(oi_change_hist_4w) / max(len(oi_change_hist_4w), 1), 0)
                                  if oi_change_hist_4w else 0,
        "index_investor_bias":    idx_bias,
        "history_weeks":          len(hist),
        "data_quality":           "fresh" if len(hist) >= MIN_WEEKS_FOR_PCTILE else
                                  "insufficient_history",
    }
    return result


# ─── I/O-lag (isolert fra rene funksjoner) ─────────────────────────────────

def _safe_json_load(path: str) -> Optional[dict | list]:
    """Les JSON-fil, returnér None ved feil (matcher mønsteret i
    driver_group_mapping._safe_json)."""
    try:
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def load_history(market_name: str,
                 report_type: str,
                 base_dir: str,
                 current_year: int = 2026,
                 min_year: int = 2010) -> list[dict]:
    """Last og slå sammen ukentlig + årlig-historikk for ett market-navn.

    Leser:
      - data/<report_type>/<YYYY-MM-DD>.json  (ukentlige snapshots, listof entries)
      - data/history/<report_type>/<YYYY>.json (årlig arkiv, listof entries)

    Dedupliserer på (date, market) og sorterer kronologisk (eldste først).
    Market-navnet matches case-insensitivt.
    """
    market_lc = market_name.strip().lower()
    seen: set[tuple[str, str]] = set()
    collected: list[dict] = []

    # Årlige arkiver først (~52 × N år = hoveddel av historikken)
    history_dir = os.path.join(base_dir, "data", "history", report_type)
    if os.path.isdir(history_dir):
        for year in range(min_year, current_year + 1):
            path = os.path.join(history_dir, f"{year}.json")
            data = _safe_json_load(path)
            if not isinstance(data, list):
                continue
            for entry in data:
                m = (entry.get("market") or "").strip().lower()
                if m != market_lc:
                    continue
                key = (entry.get("date", ""), m)
                if key in seen:
                    continue
                seen.add(key)
                collected.append(entry)

    # Ukentlig katalog (inneværende år, ofte nyere data enn history/YYYY.json)
    weekly_dir = os.path.join(base_dir, "data", report_type)
    if os.path.isdir(weekly_dir):
        for path in sorted(glob.glob(os.path.join(weekly_dir, "*.json"))):
            if path.endswith("latest.json"):
                continue
            data = _safe_json_load(path)
            if not isinstance(data, list):
                continue
            for entry in data:
                m = (entry.get("market") or "").strip().lower()
                if m != market_lc:
                    continue
                key = (entry.get("date", ""), m)
                if key in seen:
                    continue
                seen.add(key)
                collected.append(entry)

    # Sortér kronologisk (eldste først)
    collected.sort(key=lambda e: e.get("date", ""))
    return collected


def _load_latest_entry(market_name: str, report_type: str, base_dir: str) -> Optional[dict]:
    """Hent nyeste entry for et market fra data/<report_type>/latest.json."""
    path = os.path.join(base_dir, "data", report_type, "latest.json")
    data = _safe_json_load(path)
    if not isinstance(data, list):
        return None
    market_lc = market_name.strip().lower()
    for entry in data:
        if (entry.get("market") or "").strip().lower() == market_lc:
            return entry
    return None


def build_cache(base_dir: str, now_iso: str) -> dict:
    """Bygg analytics-cache for alle assets i ASSET_COT_MAP.

    Returnerer struktur klar for json.dump til data/cot_analytics/latest.json.
    Assets uten tilstrekkelig historikk får likevel en entry med
    data_quality='insufficient_history' og None på percentile/z.
    """
    import datetime as _dt
    current_year = _dt.datetime.utcnow().year

    assets: dict[str, dict] = {}
    max_cot_date = ""

    for scoring_key, market_name, report_type, supp_report in ASSET_COT_MAP:
        latest = _load_latest_entry(market_name, report_type, base_dir)
        if not latest:
            assets[scoring_key] = {
                "cot_date":            None,
                "report_type":         report_type,
                "data_quality":        "missing",
                "reason":              f"No latest entry for '{market_name}' in {report_type}",
            }
            continue

        history = load_history(market_name, report_type, base_dir,
                               current_year=current_year)
        supp_entry = None
        if supp_report:
            supp_entry = _load_latest_entry(market_name, supp_report, base_dir)

        analytics = build_asset_analytics(scoring_key, report_type, latest,
                                          history, supplemental_entry=supp_entry)
        # Post-prosess: beregn oi_regime (krever retning, så dette settes av caller
        # basert på asset-direction i scoring-loopen. Cachen leverer avg_4w.)
        assets[scoring_key] = analytics

        if analytics.get("cot_date") and analytics["cot_date"] > max_cot_date:
            max_cot_date = analytics["cot_date"]

    return {
        "generated": now_iso,
        "cot_date":  max_cot_date or None,
        "assets":    assets,
    }


def load_cache(path: str) -> Optional[dict]:
    """Last eksisterende cache-fil. Returnerer None hvis fil mangler eller er korrupt."""
    return _safe_json_load(path)


def save_cache(cache: dict, path: str) -> None:
    """Skriv cache til disk. Oppretter katalog ved behov."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
