"""
cot_interpreter.py — Tolker COT-data per instrument, ikke bare rådata.

Leser eksisterende COT-historikk og pris-historikk og produserer per instrument:
  - flow-dekomponering (uke-Δ med attribusjon)
  - regime-klassifisering (Akkumulasjon / Markup / Distribusjon / Markdown / ...)
  - konviksjons-score (long / short 0-10)
  - divergens-flags
  - analog-lookup med fremoverkast
  - prædiktivt utfall (retning + tidsvindu + sannsynlighet + median beveg.)
  - narrative-setning på norsk

Output: data/cot_interpretation/latest.json — én entry per instrument.

Bruker eksisterende cot_analytics.load_history for å laste rik historikk
(15+ år for major instrumenter) fra data/history/<report>/YYYY.json +
data/<report>/<date>.json.

Pris-historikk leses fra data/prices/<key>.json (ukentlig, 15 år).
"""
from __future__ import annotations

import json
import os
import datetime as _dt
import statistics
from pathlib import Path
from typing import Optional

from cot_analytics import (
    MIN_WEEKS_FOR_PCTILE,
    DEFAULT_LOOKBACK_WEEKS,
    load_history,
    rank_percentile,
    _safe_json_load,
    _load_latest_entry,
)

# Egen utvidet mapping — fikser navnefeil i upstream ASSET_COT_MAP
# (sugar→sugar no. 11, coffee→coffee c, cotton→cotton no. 2) og legger til
# Platinum, Copper, NatGas. SPX/NAS100/BTC/ETH har ingen disagg/legacy/tff-rapport
# men håndteres med "ingen_cot" state i UI.
EXTENDED_ASSET_MAP: list[tuple[str, str, str, Optional[str]]] = [
    # FX (TFF)
    ("EURUSD",   "euro fx",                "tff", None),
    ("GBPUSD",   "british pound",          "tff", None),
    ("USDJPY",   "japanese yen",           "tff", None),
    ("AUDUSD",   "australian dollar",      "tff", None),
    # Metaller (disagg)
    ("Gold",     "gold",                   "disaggregated", None),
    ("Silver",   "silver",                 "disaggregated", None),
    ("Platinum", "platinum",               "disaggregated", None),
    ("Copper",   "copper",                 "disaggregated", None),
    # Energi
    ("WTI",      "crude oil, light sweet", "disaggregated", None),
    ("Brent",    "brent last day",         "disaggregated", None),
    ("NatGas",   "nat gas nyme",           "disaggregated", None),
    # Korn
    ("Corn",     "corn",                   "disaggregated", None),
    ("Wheat",    "wheat",                  "disaggregated", None),
    ("Soybean",  "soybeans",               "disaggregated", None),
    # Softs (korrigerte navn)
    ("Cotton",   "cotton no. 2",           "disaggregated", None),
    ("Sugar",    "sugar no. 11",           "disaggregated", None),
    ("Coffee",   "coffee c",               "disaggregated", None),
    ("Cocoa",   "cocoa",                   "disaggregated", None),
    # Krypto (TFF — hedge funds som "spekulanter")
    ("BTC",      "bitcoin",                "tff", None),
    ("ETH",      "ether cash settled",     "tff", None),
]

# Instrumenter uten COT-rapport — vises med data_quality="ingen_cot"
NO_COT_ASSETS = ["SPX", "NAS100"]

# ─── Instrumenter som har egen pris-historikk-fil i data/prices/ ───────────
# Mappes scoring_key → filnavn-stem (lowercase).
PRICE_HISTORY_FILE: dict[str, str] = {
    "EURUSD": "eurusd", "GBPUSD": "gbpusd", "USDJPY": "usdjpy", "AUDUSD": "audusd",
    "Gold": "gold", "Silver": "silver",
    "WTI": "wti", "Brent": "brent",
    "SPX": "spx", "NAS100": "nas100",
    "Corn": "corn", "Wheat": "wheat", "Soybean": "soybean",
    "Cotton": "cotton", "Sugar": "sugar", "Coffee": "coffee", "Cocoa": "cocoa",
}

# Norske navn brukt i UI og narrative-setninger
INSTRUMENT_NAVN_NO: dict[str, str] = {
    "EURUSD": "Euro/Dollar", "GBPUSD": "Pund/Dollar",
    "USDJPY": "Dollar/Yen", "AUDUSD": "Aussie/Dollar",
    "Gold": "Gull", "Silver": "Sølv", "Platinum": "Platina", "Copper": "Kobber",
    "WTI": "WTI råolje", "Brent": "Brent råolje", "NatGas": "Naturgass",
    "SPX": "S&P 500", "NAS100": "Nasdaq 100",
    "Corn": "Mais", "Wheat": "Hvete", "Soybean": "Soyabønner",
    "Cotton": "Bomull", "Sugar": "Sukker", "Coffee": "Kaffe", "Cocoa": "Kakao",
    "BTC": "Bitcoin", "ETH": "Ether",
}

# ─── Hjelpefunksjoner ──────────────────────────────────────────────────────

def _mm_net_from_entry(entry: dict) -> Optional[float]:
    """Hent MM net fra en COT-entry (spekulanter-feltet)."""
    if not entry:
        return None
    return (entry.get("spekulanter") or {}).get("net")


def _mm_long_from_entry(entry: dict) -> Optional[float]:
    if not entry:
        return None
    return (entry.get("spekulanter") or {}).get("long")


def _mm_short_from_entry(entry: dict) -> Optional[float]:
    if not entry:
        return None
    return (entry.get("spekulanter") or {}).get("short")


def _comm_net_from_entry(entry: dict) -> Optional[float]:
    """Hent kommersiell net (produsenter i disagg, kommersielle i legacy)."""
    if not entry:
        return None
    prod = (entry.get("produsenter") or {}).get("net")
    if prod is None:
        prod = (entry.get("kommersielle") or {}).get("net")
    return prod


def _comm_long_from_entry(entry: dict) -> Optional[float]:
    if not entry:
        return None
    prod = (entry.get("produsenter") or {}).get("long")
    if prod is None:
        prod = (entry.get("kommersielle") or {}).get("long")
    return prod


def _comm_short_from_entry(entry: dict) -> Optional[float]:
    if not entry:
        return None
    prod = (entry.get("produsenter") or {}).get("short")
    if prod is None:
        prod = (entry.get("kommersielle") or {}).get("short")
    return prod


# Aktør-grupper: hvilke felter som finnes per rapport-type.
# Hver aktør har et display-navn på norsk og en kort beskrivelse av hva de er.
ACTOR_FIELDS = {
    "disaggregated": [
        ("spekulanter", "Managed Money", "Hedgefond og fondsforvaltere — 'mengden' / trend-følgere"),
        ("produsenter", "Kommersielle",  "Produsenter, prosessorer og fysiske hedgere — 'smart money'"),
        ("smahandlere", "Småhandlere",   "Små, ikke-rapporteringspliktige posisjoner — retail"),
    ],
    "tff": [
        ("spekulanter", "Hedgefond",     "Belånte fond og hedgefond — 'mengden' / spekulativ retning"),
        ("institusjoner","Pensjonsfond", "Asset managers og pensjonsfond — strukturelle posisjoner"),
        ("meglere",     "Banker/Meglere","Dealers — markedsstillere som tar motsatt side av spekulasjon"),
        ("smahandlere", "Småhandlere",   "Små, ikke-rapporteringspliktige posisjoner — retail"),
    ],
    "legacy": [
        ("spekulanter", "Spekulanter",   "Store ikke-kommersielle posisjoner — spekulativ retning"),
        ("kommersielle","Kommersielle",  "Produsenter og fysiske hedgere — 'smart money'"),
        ("smahandlere", "Småhandlere",   "Små, ikke-rapporteringspliktige posisjoner — retail"),
    ],
}


def build_actor_board(latest: dict, prev: Optional[dict],
                      history: list[dict], report_type: str) -> list[dict]:
    """Bygg liste over aktører med posisjon, percentil og uke-Δ.

    For hver aktør i ACTOR_FIELDS[report_type], returner:
      - key, navn (norsk), forklaring
      - long, short, net (denne uken)
      - long_delta, short_delta, net_delta (vs forrige uke)
      - net_pctile_52w (rank i forhold til 52-ukers historie av denne aktørens net)
      - verdict (kort tekst-tag: "BYGGER LONG", "DEKKER SHORTS", etc.)
    """
    actors = ACTOR_FIELDS.get(report_type, ACTOR_FIELDS["disaggregated"])
    out = []
    hist52 = history[-52:] if len(history) >= 52 else history

    for field, navn, forklaring in actors:
        cur = latest.get(field) or {}
        long_now = cur.get("long")
        short_now = cur.get("short")
        net_now = cur.get("net")
        if net_now is None:
            continue

        # Uke-deltaer
        prev_field = (prev or {}).get(field) or {}
        long_d = (long_now or 0) - (prev_field.get("long") or 0) if prev else None
        short_d = (short_now or 0) - (prev_field.get("short") or 0) if prev else None
        net_d = (net_now or 0) - (prev_field.get("net") or 0) if prev else None

        # Percentile 52u
        net_hist = [(e.get(field) or {}).get("net") for e in hist52]
        net_pctile = rank_percentile(net_now, net_hist)

        # Verdict — kort beskrivelse av hva aktøren gjorde denne uken
        verdict = "STABIL"
        if long_d is not None and short_d is not None:
            if long_d > 0 and short_d < 0:
                verdict = "BYGGER LONG"
            elif long_d < 0 and short_d > 0:
                verdict = "BYGGER SHORT"
            elif long_d > 0 and short_d > 0:
                verdict = "ØKER BEGGE SIDER"
            elif long_d < 0 and short_d < 0:
                verdict = "REDUSERER BEGGE SIDER"
            elif long_d > 0 and short_d == 0:
                verdict = "BYGGER LONG"
            elif short_d > 0 and long_d == 0:
                verdict = "BYGGER SHORT"
            elif long_d < 0 and short_d == 0:
                verdict = "REDUSERER LONG"
            elif short_d < 0 and long_d == 0:
                verdict = "DEKKER SHORT"

        # Pos: long/short/balansert basert på net
        denominator = (long_now or 0) + (short_now or 0)
        if denominator > 0:
            net_ratio = net_now / denominator
            if net_ratio > 0.1:
                posisjon = "long"
            elif net_ratio < -0.1:
                posisjon = "short"
            else:
                posisjon = "balansert"
        else:
            posisjon = "balansert"

        out.append({
            "key": field,
            "navn": navn,
            "forklaring": forklaring,
            "label": cur.get("label") or navn,
            "long": long_now,
            "short": short_now,
            "net": net_now,
            "long_delta": long_d,
            "short_delta": short_d,
            "net_delta": net_d,
            "net_pctile_52w": net_pctile,
            "posisjon": posisjon,
            "verdict": verdict,
        })
    return out


def _kfmt(n: Optional[float]) -> str:
    """Format som 'NNk' (8200 → '8.2k'). For narrative."""
    if n is None:
        return "—"
    if abs(n) >= 1000:
        return f"{n/1000:.1f}k"
    return f"{int(round(n))}"


# ─── Flow-dekomponering ────────────────────────────────────────────────────

def decompose_flow(latest: dict, prev: dict) -> dict:
    """Diff mellom siste og forrige uke. Attribuerer OI-endring.

    Returnerer dict med Δ-felter og attribusjons-streng på norsk.
    """
    if not latest or not prev:
        return {"available": False}

    mm_long_d = (_mm_long_from_entry(latest) or 0) - (_mm_long_from_entry(prev) or 0)
    mm_short_d = (_mm_short_from_entry(latest) or 0) - (_mm_short_from_entry(prev) or 0)
    comm_long_d = (_comm_long_from_entry(latest) or 0) - (_comm_long_from_entry(prev) or 0)
    comm_short_d = (_comm_short_from_entry(latest) or 0) - (_comm_short_from_entry(prev) or 0)

    oi_now = latest.get("open_interest") or 0
    oi_prev = prev.get("open_interest") or 0
    oi_delta = oi_now - oi_prev
    oi_delta_pct = round(100 * oi_delta / oi_prev, 1) if oi_prev else 0

    mm_net_d = mm_long_d - mm_short_d
    comm_net_d = comm_long_d - comm_short_d

    # Attribusjon — hvem drev OI-endringen og hvordan ble den finansiert?
    if oi_delta > 0:
        # OI steg — nye posisjoner. Hvem bygger mest?
        if mm_long_d > 0 and comm_short_d > 0:
            attribusjon = "MM long-bygging finansiert av kommersiell hedging"
        elif mm_short_d > 0 and comm_long_d > 0:
            attribusjon = "MM short-bygging finansiert av kommersielle kjøp"
        elif mm_long_d > abs(mm_short_d) and mm_long_d > 0:
            attribusjon = "MM bygger longs (ensidig)"
        elif mm_short_d > abs(mm_long_d) and mm_short_d > 0:
            attribusjon = "MM bygger shorts (ensidig)"
        else:
            attribusjon = "Bred posisjonsbygging på begge sider"
    elif oi_delta < 0:
        # OI falt — posisjonslukking
        if mm_long_d < 0 and mm_short_d < 0:
            attribusjon = "Bilateral MM-derisking (begge sider redusert)"
        elif mm_long_d < 0:
            attribusjon = "MM long-likvidering"
        elif mm_short_d < 0:
            attribusjon = "MM short-dekking"
        else:
            attribusjon = "Kommersiell posisjonslukking"
    else:
        attribusjon = "Rotasjon uten netto OI-endring"

    return {
        "available": True,
        "mm_long_delta": int(mm_long_d),
        "mm_short_delta": int(mm_short_d),
        "mm_net_delta": int(mm_net_d),
        "comm_long_delta": int(comm_long_d),
        "comm_short_delta": int(comm_short_d),
        "comm_net_delta": int(comm_net_d),
        "oi_delta": int(oi_delta),
        "oi_delta_pct": oi_delta_pct,
        "attribusjon": attribusjon,
    }


# ─── Regime-klassifisering ─────────────────────────────────────────────────

REGIMES = {
    "akkumulasjon":   {"farge": "grønn",  "retning": "opp",     "label": "Akkumulasjon"},
    "markup":         {"farge": "grønn",  "retning": "opp",     "label": "Markup"},
    "distribusjon":   {"farge": "rød",    "retning": "ned",     "label": "Distribusjon"},
    "markdown":       {"farge": "rød",    "retning": "ned",     "label": "Markdown"},
    "squeeze-opp":    {"farge": "gul",    "retning": "opp",     "label": "Squeeze-oppsett (short)"},
    "squeeze-ned":    {"farge": "gul",    "retning": "ned",     "label": "Squeeze-oppsett (long)"},
    "kapitulasjon":   {"farge": "gul",    "retning": "opp",     "label": "Kapitulasjon"},
    "nøytral":        {"farge": "grå",    "retning": "nøytral", "label": "Nøytral"},
}


def classify_regime(mm_pctile: Optional[float],
                    oi_trend: str,   # "rising" / "falling" / "flat"
                    price_trend: str,  # "up" / "down" / "flat"
                    comm_pctile: Optional[float] = None) -> str:
    """Wyckoff-inspirert regime-klassifikator.

    Bruker MM-percentile-bånd × OI-trend × pris-trend (+ kommersiell-percentile
    der tilgjengelig) til å produsere en regime-nøkkel fra REGIMES.
    """
    if mm_pctile is None:
        return "nøytral"

    low = mm_pctile <= 25
    high = mm_pctile >= 75
    extreme_high = mm_pctile >= 90
    extreme_low = mm_pctile <= 10

    # Kapitulasjon: ekstrem ene vei + sterk pris-bevegelse motsatt
    if extreme_low and price_trend == "down" and oi_trend == "falling":
        return "kapitulasjon"
    if extreme_high and price_trend == "up" and oi_trend == "falling":
        # Tunne ut — long-likvidering ved topp
        return "distribusjon"

    # Squeeze-oppsett: kraftig ekstrem motsatt pris-trend
    if extreme_low and price_trend == "up":
        return "squeeze-opp"   # MM ekstrem short i opptrend = short-squeeze risiko
    if extreme_high and price_trend == "down":
        return "squeeze-ned"   # MM ekstrem long i nedtrend = long-squeeze risiko

    # Distribusjon: MM trengt long mens OI/pris ikke følger med, eller kommersielle ekstreme short
    if high and (price_trend in ("flat", "up")):
        if oi_trend == "rising" and price_trend == "up":
            return "markup"  # fortsatt sunn opptrend
        return "distribusjon"

    # Akkumulasjon / markdown
    if low:
        if price_trend == "down" and oi_trend == "falling":
            return "markdown"
        if oi_trend == "rising" or price_trend in ("flat", "up"):
            return "akkumulasjon"
        return "markdown"

    # Mellom-band: bruk pris-trend
    if 25 < mm_pctile < 75:
        if price_trend == "up" and oi_trend in ("rising", "flat"):
            return "markup"
        if price_trend == "down" and oi_trend in ("rising", "flat"):
            return "markdown"

    return "nøytral"


# ─── Konviksjons-score ─────────────────────────────────────────────────────

def conviction_score(mm_long_d: int, mm_short_d: int) -> dict:
    """Score long/short-konviksjon 0-10 basert på flyt-mønster.

    Long-build + short-cover = sterk long-konviksjon
    Begge sider vokser = lav konviksjon (hedge/par)
    Begge sider faller = derisking
    """
    # Skaler delta til konviksjon-score basert på retning
    long_score = 5  # nøytral utgangspunkt
    short_score = 5

    abs_long = abs(mm_long_d)
    abs_short = abs(mm_short_d)

    # Long-konviksjon
    if mm_long_d > 0 and mm_short_d < 0:
        # Best mulig: bygger longs OG dekker shorts
        long_score = 8 + min(2, (abs_long + abs_short) / 20000)
    elif mm_long_d > 0 and mm_short_d > 0:
        # Begge vokser — lav konviksjon
        long_score = 5
    elif mm_long_d > 0:
        long_score = 6 + min(2, abs_long / 15000)
    elif mm_long_d < 0 and mm_short_d > 0:
        long_score = 1 + max(0, 2 - abs_long / 20000)
    elif mm_long_d < 0:
        long_score = 3

    # Short-konviksjon (speil av long)
    if mm_short_d > 0 and mm_long_d < 0:
        short_score = 8 + min(2, (abs_long + abs_short) / 20000)
    elif mm_short_d > 0 and mm_long_d > 0:
        short_score = 5
    elif mm_short_d > 0:
        short_score = 6 + min(2, abs_short / 15000)
    elif mm_short_d < 0 and mm_long_d > 0:
        short_score = 1 + max(0, 2 - abs_short / 20000)
    elif mm_short_d < 0:
        short_score = 3

    # Begrunnelse på norsk
    if mm_long_d > 0 and mm_short_d < 0:
        begrunnelse = "MM bygger longs OG dekker shorts — ensidig flyt på long-siden"
    elif mm_short_d > 0 and mm_long_d < 0:
        begrunnelse = "MM bygger shorts OG dekker longs — ensidig flyt på short-siden"
    elif mm_long_d > 0 and mm_short_d > 0:
        begrunnelse = "Begge sider vokser — lav konviksjon (hedging/par-handler)"
    elif mm_long_d < 0 and mm_short_d < 0:
        begrunnelse = "Begge sider reduseres — bred derisking"
    elif mm_long_d > 0:
        begrunnelse = "Long-bygging, shorts uendret"
    elif mm_short_d > 0:
        begrunnelse = "Short-bygging, longs uendret"
    elif mm_long_d < 0:
        begrunnelse = "Long-likvidering"
    else:
        begrunnelse = "Short-dekking"

    return {
        "long": round(min(10, max(0, long_score)), 1),
        "short": round(min(10, max(0, short_score)), 1),
        "begrunnelse": begrunnelse,
    }


# ─── Divergens-flags ───────────────────────────────────────────────────────

def detect_flags(mm_pctile: Optional[float],
                 comm_pctile: Optional[float],
                 oi_trend: str,
                 price_trend: str,
                 mm_net_4w_change: Optional[float],
                 price_4w_change: Optional[float]) -> list[str]:
    """Returnerer liste av aktive flag-koder. UI rendrer norske labels."""
    flags = []
    if mm_pctile is not None:
        if mm_pctile >= 85:
            flags.append("mm_ekstrem_long")
        if mm_pctile <= 15:
            flags.append("mm_ekstrem_short")
    if comm_pctile is not None:
        if comm_pctile >= 85:
            flags.append("kommersiell_ekstrem_long")
        if comm_pctile <= 15:
            flags.append("kommersiell_ekstrem_short")

    # Pris vs MM divergens (4 ukers vindu)
    if mm_net_4w_change is not None and price_4w_change is not None:
        if price_4w_change > 1 and mm_net_4w_change < 0:
            flags.append("pris_opp_mm_ned")
        elif price_4w_change < -1 and mm_net_4w_change > 0:
            flags.append("pris_ned_mm_opp")

    # OI / pris-mismatch
    if oi_trend == "rising" and price_trend == "down":
        flags.append("ny_short_konviksjon")
    if oi_trend == "falling" and price_trend == "up":
        flags.append("short_dekking_oppgang")

    return flags


# Norske labels for flags (brukes av UI)
FLAG_LABELS_NO: dict[str, str] = {
    "mm_ekstrem_long": "MM trengt long (>85 percentil)",
    "mm_ekstrem_short": "MM trengt short (<15 percentil)",
    "kommersiell_ekstrem_long": "Kommersielle ekstremt long",
    "kommersiell_ekstrem_short": "Kommersielle ekstremt short",
    "pris_opp_mm_ned": "Pris stiger mens MM reduserer — distribusjon-mistanke",
    "pris_ned_mm_opp": "Pris faller mens MM bygger — akkumulasjon-mistanke",
    "ny_short_konviksjon": "Stigende OI + fallende pris — ny short-konviksjon",
    "short_dekking_oppgang": "Fallende OI + stigende pris — short-dekking",
}


# ─── Analog-lookup ──────────────────────────────────────────────────────────

def find_analogs(history: list[dict],
                 prices: Optional[dict],
                 current_mm_pctile: float,
                 current_oi_trend: str,
                 lookback_weeks: int = 520) -> list[dict]:
    """Finn historiske uker med lignende konfigurasjon (MM-percentile-bånd
    + OI-trend-retning) og returner deres 4u/8u fremoverkast.

    `history` er sortert kronologisk eldst-først.
    `prices` er dict med {dato_str: pris} fra data/prices/<key>.json (kan være None).

    Returnerer liste av matchende analoger.
    """
    if not history or current_mm_pctile is None:
        return []

    band_lo = max(0, current_mm_pctile - 8)
    band_hi = min(100, current_mm_pctile + 8)

    # Vi vurderer bare historikk fra index hist[26:] og frem (trenger nok forhistorie til pctile)
    # og lar minst 8 uker stå igjen for forward-return
    analogs = []
    n = len(history)
    if n < MIN_WEEKS_FOR_PCTILE + 10:
        return []

    # Pris-historikk indeksert
    price_lookup = {}
    if prices and isinstance(prices, dict):
        for d, p in prices.items():
            price_lookup[d] = p

    # Iter gjennom hver kandidat-uke (i+26 ≤ i ≤ n-8) for å ha både pctile-input og forward
    for i in range(MIN_WEEKS_FOR_PCTILE, n - 8):
        entry_i = history[i]
        mm_net_i = _mm_net_from_entry(entry_i)
        if mm_net_i is None:
            continue
        # Beregn percentile-på-tidspunkt-i mot hist[i-26:i+1]
        window = [_mm_net_from_entry(history[j]) for j in range(max(0, i - 52), i + 1)]
        pct_i = rank_percentile(mm_net_i, window)
        if pct_i is None or not (band_lo <= pct_i <= band_hi):
            continue

        # Sjekk OI-trend rundt punkt i (4u avg change_oi)
        oi_changes_i = [(history[j].get("change_oi") or 0) for j in range(max(0, i - 3), i + 1)]
        avg4w_i = sum(oi_changes_i) / max(1, len(oi_changes_i))
        if current_oi_trend == "rising" and avg4w_i <= 0:
            continue
        if current_oi_trend == "falling" and avg4w_i >= 0:
            continue
        # "flat" — godta alt

        # Forward returns 4u/8u
        date_i = entry_i.get("date", "")
        fwd4w = None
        fwd8w = None
        if price_lookup and date_i:
            try:
                d0 = _dt.date.fromisoformat(date_i)
                p0 = _nearest_price(price_lookup, d0)
                if p0:
                    p4 = _nearest_price(price_lookup, d0 + _dt.timedelta(weeks=4))
                    p8 = _nearest_price(price_lookup, d0 + _dt.timedelta(weeks=8))
                    if p4:
                        fwd4w = round(100 * (p4 - p0) / p0, 2)
                    if p8:
                        fwd8w = round(100 * (p8 - p0) / p0, 2)
            except Exception:
                pass

        analogs.append({
            "dato": date_i,
            "mm_pctile": pct_i,
            "oi_4w_avg": round(avg4w_i, 0),
            "fwd_4u_pct": fwd4w,
            "fwd_8u_pct": fwd8w,
        })

    # Begrens til siste N analoger (mest relevante kontekstuelt)
    return analogs[-20:]


def _nearest_price(lookup: dict, target_date: _dt.date) -> Optional[float]:
    """Finn pris nærmest target_date (innen ±7 dager)."""
    for offset in range(0, 8):
        for sign in (0, -1, 1) if offset > 0 else (0,):
            d = target_date + _dt.timedelta(days=sign * offset)
            key = d.isoformat()
            if key in lookup:
                return lookup[key]
    return None


def aggregate_analogs(analogs: list[dict]) -> dict:
    """Aggregér analog-statistikk: hit-rate, median fwd-return, sample-count."""
    if not analogs:
        return {"count": 0, "available": False}

    fwd4 = [a["fwd_4u_pct"] for a in analogs if a.get("fwd_4u_pct") is not None]
    fwd8 = [a["fwd_8u_pct"] for a in analogs if a.get("fwd_8u_pct") is not None]

    out = {"count": len(analogs), "available": True}
    if fwd4:
        median4 = statistics.median(fwd4)
        out["median_4u_pct"] = round(median4, 2)
        out["positive_rate_4u"] = round(sum(1 for v in fwd4 if v > 0) / len(fwd4), 2)
    if fwd8:
        median8 = statistics.median(fwd8)
        out["median_8u_pct"] = round(median8, 2)
        out["positive_rate_8u"] = round(sum(1 for v in fwd8 if v > 0) / len(fwd8), 2)
    return out


# ─── Prædiktivt utfall ────────────────────────────────────────────────────

def predict_outcome(regime: str,
                    analogs_agg: dict,
                    conviction: dict,
                    flags: list[str]) -> dict:
    """Aggregér regime + analoger + konviksjon + flags til en prædiksjon.

    Retning: opp / ned / nøytral
    Tidsvindu: 1u / 2-4u / 4-6u / 1-3md
    Sannsynlighet: 0.0-0.85 (cap)
    Forventet beveg: median fra analoger (med fortegn etter retning)
    """
    base_retning = REGIMES.get(regime, REGIMES["nøytral"])["retning"]
    base_tidsvindu = "2-4 uker"
    base_sansyn = 0.5
    base_beveg = None
    begrunnelser = []

    # Regime-baseret startpunkt
    if regime == "distribusjon":
        base_retning = "ned"
        base_tidsvindu = "4-6 uker"
        base_sansyn = 0.65
        begrunnelser.append("Distribusjons-regime: MM trengt long, smart money distribuerer")
    elif regime == "markup":
        base_retning = "opp"
        base_tidsvindu = "4-8 uker"
        base_sansyn = 0.6
        begrunnelser.append("Markup-regime: pris og posisjonering støtter opptrend")
    elif regime == "akkumulasjon":
        base_retning = "opp"
        base_tidsvindu = "1-3 måneder"
        base_sansyn = 0.55
        begrunnelser.append("Akkumulasjon: smart money posisjonerer for opptur")
    elif regime == "markdown":
        base_retning = "ned"
        base_tidsvindu = "4-8 uker"
        base_sansyn = 0.6
        begrunnelser.append("Markdown-regime: nedtrend støttet av COT")
    elif regime in ("squeeze-opp", "squeeze-ned"):
        base_retning = "opp" if regime == "squeeze-opp" else "ned"
        base_tidsvindu = "1-3 uker"
        base_sansyn = 0.55
        begrunnelser.append("Squeeze-oppsett: ekstrem posisjonering motsatt pris-trend")
    elif regime == "kapitulasjon":
        base_retning = "opp"
        base_tidsvindu = "2-6 uker"
        base_sansyn = 0.55
        begrunnelser.append("Kapitulasjon: salgs-utmattelse, mulighet for mean-reversion")

    # Justering basert på analog-statistikk
    if analogs_agg.get("available") and analogs_agg.get("count", 0) >= 3:
        if "median_4u_pct" in analogs_agg:
            median = analogs_agg["median_4u_pct"]
            pos_rate = analogs_agg.get("positive_rate_4u", 0.5)
            base_beveg = median
            # Hvis analoger sterkt støtter regime-retning, øk sansynlighet
            if base_retning == "opp" and median > 0.5:
                base_sansyn = min(0.85, base_sansyn + 0.1 * pos_rate)
                begrunnelser.append(
                    f"{analogs_agg['count']} analoger: {int(pos_rate*100)}% positive, median +{median}% over 4u"
                )
            elif base_retning == "ned" and median < -0.5:
                base_sansyn = min(0.85, base_sansyn + 0.1 * (1 - pos_rate))
                begrunnelser.append(
                    f"{analogs_agg['count']} analoger: {int((1-pos_rate)*100)}% negative, median {median}% over 4u"
                )
            elif (base_retning == "opp" and median < -0.5) or (base_retning == "ned" and median > 0.5):
                # Analoger motsier regime — reduser sansynlighet
                base_sansyn = max(0.4, base_sansyn - 0.1)
                begrunnelser.append(f"Analoger motsier regime (median {median}%) — lavere konfidens")

    # Konviksjon-justering
    if base_retning == "opp" and conviction["long"] >= 7:
        base_sansyn = min(0.85, base_sansyn + 0.05)
    elif base_retning == "ned" and conviction["short"] >= 7:
        base_sansyn = min(0.85, base_sansyn + 0.05)

    return {
        "retning": base_retning,
        "tidsvindu": base_tidsvindu,
        "sannsynlighet": round(base_sansyn, 2),
        "forventet_beveg_pct": base_beveg,
        "begrunnelse": " · ".join(begrunnelser) if begrunnelser else "Standard regime-utfall",
    }


# ─── Narrative-generator ──────────────────────────────────────────────────

def build_narrative(asset_key: str,
                    mm_pctile: Optional[float],
                    regime: str,
                    flow: dict,
                    conviction: dict,
                    flags: list[str],
                    analogs_agg: dict,
                    prediksjon: dict) -> str:
    """Bygg én norsk fortellende setning som oppsummerer alt."""
    navn = INSTRUMENT_NAVN_NO.get(asset_key, asset_key)
    deler = []

    # Åpning: MM-percentile
    if mm_pctile is not None:
        if mm_pctile >= 80:
            deler.append(f"MM er trengt long ({mm_pctile:.0f}%ile 52u)")
        elif mm_pctile <= 20:
            deler.append(f"MM er trengt short ({mm_pctile:.0f}%ile 52u)")
        else:
            deler.append(f"MM-posisjonering er {mm_pctile:.0f}%ile 52u")

    # Uke-flyt
    if flow.get("available"):
        ml = flow["mm_long_delta"]
        ms = flow["mm_short_delta"]
        oip = flow["oi_delta_pct"]
        oi_str = f"OI {'+' if oip >= 0 else ''}{oip}%"
        deler.append(f"Denne uken: MM long {'+' if ml >= 0 else ''}{_kfmt(ml)}, "
                     f"MM short {'+' if ms >= 0 else ''}{_kfmt(ms)}, {oi_str} ({flow['attribusjon']})")

    # Regime
    regime_label = REGIMES.get(regime, REGIMES["nøytral"])["label"]
    deler.append(f"Regime: {regime_label}")

    # Analog + prediksjon
    if analogs_agg.get("available") and analogs_agg.get("count", 0) >= 3:
        n = analogs_agg["count"]
        if "median_4u_pct" in analogs_agg:
            m = analogs_agg["median_4u_pct"]
            deler.append(f"{n} analoge oppsett: median {'+' if m >= 0 else ''}{m}% over 4 uker")

    # Prediksjon-konkluderende setning
    retn = prediksjon["retning"]
    tv = prediksjon["tidsvindu"]
    sn = int(prediksjon["sannsynlighet"] * 100)
    if retn == "opp":
        deler.append(f"Forventet oppgang innen {tv} ({sn}% sannsynlighet)")
    elif retn == "ned":
        deler.append(f"Forventet nedgang innen {tv} ({sn}% sannsynlighet)")
    else:
        deler.append(f"Nøytralt utfall ({sn}% sannsynlighet)")

    return f"{navn}: " + ". ".join(deler) + "."


# ─── Pris-historikk ────────────────────────────────────────────────────────

def load_price_history(asset_key: str, base_dir: str) -> Optional[dict]:
    """Last pris-historikk fra data/prices/<key>.json. Returner {dato: pris}-dict
    eller None hvis filen mangler."""
    stem = PRICE_HISTORY_FILE.get(asset_key)
    if not stem:
        return None
    path = os.path.join(base_dir, "data", "prices", f"{stem}.json")
    raw = _safe_json_load(path)
    if not raw or not isinstance(raw, dict):
        return None
    rows = raw.get("data") or []
    return {r["date"]: r["price"] for r in rows if "date" in r and "price" in r}


def price_trend_from_history(prices: Optional[dict], date_str: str, weeks_back: int = 4) -> tuple[str, Optional[float]]:
    """Bestem pris-trend (up/down/flat) og prosent-endring siste N uker."""
    if not prices or not date_str:
        return ("flat", None)
    try:
        d_now = _dt.date.fromisoformat(date_str)
    except ValueError:
        return ("flat", None)
    p_now = _nearest_price(prices, d_now)
    p_then = _nearest_price(prices, d_now - _dt.timedelta(weeks=weeks_back))
    if not p_now or not p_then:
        return ("flat", None)
    pct = 100 * (p_now - p_then) / p_then
    if pct > 1.5:
        return ("up", round(pct, 2))
    if pct < -1.5:
        return ("down", round(pct, 2))
    return ("flat", round(pct, 2))


# ─── Hoved-byggerutine ────────────────────────────────────────────────────

def interpret_asset(asset_key: str,
                    market_name: str,
                    report_type: str,
                    base_dir: str,
                    current_year: int) -> dict:
    """Bygg full interpretation-dict for én asset."""
    latest = _load_latest_entry(market_name, report_type, base_dir)
    if not latest:
        return {
            "asset": asset_key,
            "data_quality": "missing",
            "reason": f"No latest entry for '{market_name}' in {report_type}",
        }

    history = load_history(market_name, report_type, base_dir, current_year=current_year)
    if len(history) < MIN_WEEKS_FOR_PCTILE:
        return {
            "asset": asset_key,
            "data_quality": "insufficient_history",
            "history_weeks": len(history),
        }

    # Forrige uke (for flyt-Δ)
    prev = history[-2] if len(history) >= 2 else None

    # MM net + percentile
    mm_net_now = _mm_net_from_entry(latest)
    mm_hist_52w = [_mm_net_from_entry(e) for e in history[-52:]]
    mm_pctile = rank_percentile(mm_net_now, mm_hist_52w)

    # Kommersiell percentile
    comm_net_now = _comm_net_from_entry(latest)
    comm_hist_52w = [_comm_net_from_entry(e) for e in history[-52:]]
    comm_pctile = rank_percentile(comm_net_now, comm_hist_52w)

    # OI-trend (4u snitt change_oi)
    oi_changes_4w = [(e.get("change_oi") or 0) for e in history[-4:]]
    avg_oi_4w = sum(oi_changes_4w) / max(1, len(oi_changes_4w))
    if avg_oi_4w > 0:
        oi_trend = "rising"
    elif avg_oi_4w < 0:
        oi_trend = "falling"
    else:
        oi_trend = "flat"

    # Pris-trend
    prices = load_price_history(asset_key, base_dir)
    price_trend, price_4w_change = price_trend_from_history(prices, latest.get("date", ""), weeks_back=4)

    # MM net 4u endring (for divergens-flag)
    mm_net_4w_ago = None
    if len(history) >= 5:
        mm_net_4w_ago = _mm_net_from_entry(history[-5])
    mm_net_4w_change = None
    if mm_net_now is not None and mm_net_4w_ago is not None:
        mm_net_4w_change = mm_net_now - mm_net_4w_ago

    # Regime
    regime = classify_regime(mm_pctile, oi_trend, price_trend, comm_pctile)

    # Flow-dekomponering
    flow = decompose_flow(latest, prev) if prev else {"available": False}

    # Konviksjon
    if flow.get("available"):
        conviction = conviction_score(flow["mm_long_delta"], flow["mm_short_delta"])
    else:
        conviction = {"long": 5, "short": 5, "begrunnelse": "Ingen forrige uke å sammenligne med"}

    # Flags
    flags = detect_flags(mm_pctile, comm_pctile, oi_trend, price_trend,
                          mm_net_4w_change, price_4w_change)

    # Analoger
    if mm_pctile is not None:
        analogs = find_analogs(history, prices, mm_pctile, oi_trend)
    else:
        analogs = []
    analogs_agg = aggregate_analogs(analogs)

    # Prediksjon
    prediksjon = predict_outcome(regime, analogs_agg, conviction, flags)

    # Narrative
    narrative = build_narrative(asset_key, mm_pctile, regime, flow,
                                 conviction, flags, analogs_agg, prediksjon)

    # Aktør-tavle: alle grupper i COT-rapporten med deres flyt og percentil
    actor_board = build_actor_board(latest, prev, history, report_type)

    return {
        "asset": asset_key,
        "navn_no": INSTRUMENT_NAVN_NO.get(asset_key, asset_key),
        "cot_date": latest.get("date"),
        "report_type": report_type,
        "data_quality": "fresh",
        "history_weeks": len(history),

        # Råverdier (for rendering)
        "mm_net": mm_net_now,
        "mm_pctile_52w": mm_pctile,
        "comm_net": comm_net_now,
        "comm_pctile_52w": comm_pctile,
        "open_interest": latest.get("open_interest"),
        "oi_trend": oi_trend,
        "oi_change_4w_avg": round(avg_oi_4w, 0),
        "price_trend": price_trend,
        "price_4w_change_pct": price_4w_change,

        # Tolkning
        "regime": regime,
        "regime_label": REGIMES.get(regime, REGIMES["nøytral"])["label"],
        "regime_farge": REGIMES.get(regime, REGIMES["nøytral"])["farge"],
        "flow_week": flow,
        "conviction": conviction,
        "flags": flags,
        "flag_labels": [FLAG_LABELS_NO.get(f, f) for f in flags],
        "analogs": analogs[-5:] if analogs else [],
        "analogs_aggregate": analogs_agg,
        "prediksjon": prediksjon,
        "smart_money_crowd": _smart_money_label(mm_pctile, comm_pctile),
        "narrative": narrative,
        "actor_board": actor_board,
    }


def _smart_money_label(mm_pctile: Optional[float], comm_pctile: Optional[float]) -> dict:
    """Sammenlign MM-percentile mot kommersiell-percentile, klassifiser konfigurasjon."""
    if mm_pctile is None or comm_pctile is None:
        return {"available": False}
    if mm_pctile >= 75 and comm_pctile <= 25:
        label = "Klassisk topp-konfigurasjon: mengden long, smart money short"
    elif mm_pctile <= 25 and comm_pctile >= 75:
        label = "Klassisk bunn-konfigurasjon: mengden short, smart money long"
    elif abs(mm_pctile - comm_pctile) < 20:
        label = "Mengden og smart money samkjørt — lite signal"
    else:
        label = "Moderat divergens mellom mengden og smart money"
    return {
        "available": True,
        "mm_pctile": mm_pctile,
        "commercial_pctile": comm_pctile,
        "label": label,
    }


def build_interpretation_cache(base_dir: str) -> dict:
    """Bygg full interpretation-cache for alle assets i EXTENDED_ASSET_MAP
    pluss stub-entries for NO_COT_ASSETS."""
    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    current_year = _dt.datetime.now(_dt.timezone.utc).year
    assets: dict[str, dict] = {}
    max_cot_date = ""

    for scoring_key, market_name, report_type, _supp in EXTENDED_ASSET_MAP:
        try:
            entry = interpret_asset(scoring_key, market_name, report_type,
                                    base_dir, current_year)
            assets[scoring_key] = entry
            if entry.get("cot_date") and entry["cot_date"] > max_cot_date:
                max_cot_date = entry["cot_date"]
        except Exception as e:
            assets[scoring_key] = {
                "asset": scoring_key,
                "navn_no": INSTRUMENT_NAVN_NO.get(scoring_key, scoring_key),
                "data_quality": "error",
                "reason": str(e),
            }

    # Stub-entries for instrumenter uten COT
    for key in NO_COT_ASSETS:
        assets[key] = {
            "asset": key,
            "navn_no": INSTRUMENT_NAVN_NO.get(key, key),
            "data_quality": "ingen_cot",
            "reason": "Ingen COT-rapport tilgjengelig (kontrakt ikke rapporteringspliktig hos CFTC)",
        }

    return {
        "generated": now_iso,
        "cot_date": max_cot_date or None,
        "assets": assets,
    }


def save_interpretation_cache(cache: dict, path: str) -> None:
    """Skriv interpretation-cache til disk. Oppretter katalog ved behov."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


# ─── CLI-entrypoint ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    base = os.path.dirname(os.path.abspath(__file__))
    cache = build_interpretation_cache(base)
    out_path = os.path.join(base, "data", "cot_interpretation", "latest.json")
    save_interpretation_cache(cache, out_path)
    print(f"Skrev interpretation for {len(cache['assets'])} aktiva til {out_path}")
    print(f"COT-dato: {cache['cot_date']}")
    # Vis en kort oppsummering
    for k, v in cache["assets"].items():
        if v.get("data_quality") == "fresh":
            print(f"  {k:10s} regime={v['regime_label']:30s} "
                  f"pred={v['prediksjon']['retning']:6s} "
                  f"sansyn={v['prediksjon']['sannsynlighet']:.2f}")
        else:
            print(f"  {k:10s} [{v.get('data_quality')}] {v.get('reason', '')}")
