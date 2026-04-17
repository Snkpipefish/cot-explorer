"""
driver_group_mapping.py — Asset-class-mapping og data-henting for driver_matrix.

Holder all logikk for å hente riktig per-asset-data fra de ulike kildene
(data/comex, data/shipping, data/oilgas, data/fundamentals, data/conab,
data/unica, data/crypto) og pakke dem som kwargs til driver_matrix.score_asset().
"""

from __future__ import annotations

from pathlib import Path
import json


# ─── Asset → asset_class ─────────────────────────────────────────────────

ASSET_CLASS_MAP = {
    # FX
    "EURUSD":    "fx",
    "GBPUSD":    "fx",
    "USDJPY":    "fx",
    "AUDUSD":    "fx",
    # Metals
    "Gold":      "metals",
    "Silver":    "metals",
    # Energy
    "Brent":     "energy",
    "WTI":       "energy",
    # Indices
    "SPX":       "indices",
    "NAS100":    "indices",
    # Grains (Conab-dekning for Brasil-side)
    "Corn":      "grains",
    "Wheat":     "grains",
    "Soybean":   "grains",
    "Cotton":    "grains",   # bomull er teknisk sett "softs" men scoret som grains
    # Softs (ICE + Brasil-spesifikk)
    "Sugar":     "softs",
    "Coffee":    "softs",
    "Cocoa":     "softs",
    # Crypto
    "BTC":       "crypto",
    "ETH":       "crypto",
}


# ─── Helper: trygge json-lesere ──────────────────────────────────────────

def _safe_json(path: Path) -> dict:
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ─── Konsolidert data-innhenting (kalles én gang ved oppstart) ───────────

def load_all_sources(base_dir: Path) -> dict:
    """Les alle eksterne datafiler ved oppstart. Returnerer dict som brukes
    av build_context_for_asset()."""
    return {
        "comex":        _safe_json(base_dir / "data" / "comex" / "latest.json"),
        "shipping":     _safe_json(base_dir / "data" / "shipping" / "latest.json"),
        "oilgas":       _safe_json(base_dir / "data" / "oilgas" / "latest.json"),
        "fundamentals": _safe_json(base_dir / "data" / "fundamentals" / "latest.json"),
        "crypto":       _safe_json(base_dir / "data" / "crypto" / "latest.json"),
        "conab":        _safe_json(base_dir / "data" / "conab" / "latest.json"),
        "unica":        _safe_json(base_dir / "data" / "unica" / "latest.json"),
    }


# ─── Bygg kwargs til driver_matrix.score_asset() per asset ──────────────

def build_context_for_asset(asset: str,
                            sources: dict,
                            macro_context: dict) -> dict:
    """Pakker alle relevante data-kilder i kwargs for score_asset().

    macro_context inneholder global pris-data fra fetch_all.py:
      - dxy_chg5d
      - vix_regime
      - brl_chg5d
      - geo_active
      - usda_blackout (dict {asset: ...})
    """
    asset_class = ASSET_CLASS_MAP.get(asset, "fx")
    ctx: dict = {
        "asset":       asset,
        "asset_class": asset_class,
        # Global macro-data (alltid tilgjengelig)
        "dxy_chg5d":   macro_context.get("dxy_chg5d"),
        "vix_regime":  macro_context.get("vix_regime", "normal"),
        "geo_active":  macro_context.get("geo_active", False),
    }

    fund = sources.get("fundamentals", {})
    market_rates = fund.get("market_rates") or {}

    # Real yield og yield curve (hentet av fetch_fundamentals.py som DFII10/DGS10/DGS2)
    if market_rates.get("dfii10"):
        ctx["real_yield_10y"] = market_rates["dfii10"].get("value")
        ctx["real_yield_chg"] = market_rates["dfii10"].get("chg_5d")
    if market_rates.get("term_spread") is not None:
        ctx["term_spread"] = market_rates["term_spread"]

    # ── FX ──
    if asset_class == "fx":
        inst = (fund.get("instrument_scores") or {}).get(asset, {})
        ctx["fund_instrument_score"] = inst.get("score")
        # Rente-spread: hvis tilgjengelig i FRED-data, legg inn
        ctx["rate_spread_diff"] = macro_context.get(f"rate_spread_{asset}")
        ctx["term_spread"]      = macro_context.get("term_spread")

    # ── METALS ──
    elif asset_class == "metals":
        ctx["real_yield_10y"] = macro_context.get("real_yield_10y")
        ctx["real_yield_chg"] = macro_context.get("real_yield_chg")
        comex = sources.get("comex", {})
        metal_key = asset.lower()
        metal_data = comex.get(metal_key, {})
        stress = (comex.get("stress_index") or {}).get(metal_key)
        ctx["comex_stress"]         = stress
        ctx["registered_oz_change"] = metal_data.get("change_oz")
        ctx["gold_silver_ratio_z"]  = macro_context.get("gold_silver_ratio_z")

    # ── ENERGY ──
    elif asset_class == "energy":
        shipping = sources.get("shipping", {})
        oilgas   = sources.get("oilgas", {})
        ctx["shipping_risk"]         = shipping.get("overall_risk")
        ctx["oilgas_signal"]         = oilgas.get("overall_signal")
        ctx["oil_supply_disruption"] = bool(macro_context.get("oil_supply_disruption"))
        ctx["brent_wti_spread"]      = oilgas.get("brent_wti_spread")

    # ── INDICES ──
    elif asset_class == "indices":
        inst = (fund.get("instrument_scores") or {}).get(asset, {})
        ctx["fund_instrument_score"] = inst.get("score")
        ctx["term_spread"]           = macro_context.get("term_spread")

    # ── GRAINS ──
    elif asset_class == "grains":
        conab = sources.get("conab", {})
        conab_crops = conab.get("crops", {})
        # Asset → Conab-key mapping
        conab_key_map = {
            "Corn":    "milho",
            "Wheat":   "trigo",
            "Soybean": "soja",
            "Cotton":  "algodao",
        }
        crop = conab_crops.get(conab_key_map.get(asset, ""), {})
        ctx["conab_mom"]      = crop.get("mom_change_pct")
        ctx["conab_yoy"]      = crop.get("yoy_change_pct")
        usda_bo = macro_context.get("usda_blackout") or {}
        ctx["usda_blackout"]  = asset in usda_bo
        ctx["yield_score"]    = macro_context.get(f"yield_score_{asset}")
        ctx["enso_risk"]      = macro_context.get(f"enso_risk_{asset}", 0)

    # ── SOFTS ──
    elif asset_class == "softs":
        unica = sources.get("unica", {})
        conab = sources.get("conab", {})
        conab_crops = conab.get("crops", {})
        if asset == "Sugar":
            ctx["unica_mix_sugar"]   = unica.get("mix_sugar_pct")
            ctx["unica_mix_qoq"]     = unica.get("mix_sugar_change_pct_qoq")
            ctx["unica_crush_yoy"]   = unica.get("crush_accumulated_yoy_pct")
        if asset == "Coffee":
            cafe = conab_crops.get("cafe_total", {})
            ctx["conab_coffee_mom"]  = cafe.get("mom_change_pct")
            ctx["conab_coffee_yoy"]  = cafe.get("yoy_change_pct")
        ctx["brl_chg5d"]         = macro_context.get("brl_chg5d")
        ctx["harmattan_severity"] = macro_context.get(f"harmattan_{asset}", 0.0)
        ctx["frost_severity"]     = macro_context.get(f"frost_{asset}", 0.0)
        ctx["yield_score"]        = macro_context.get(f"yield_score_{asset}")

    # ── CRYPTO ──
    elif asset_class == "crypto":
        crypto = sources.get("crypto", {})
        ctx["fear_greed"] = (crypto.get("fear_greed") or {}).get("value")

    # ── Event-risk (universelle) ──
    upcoming = macro_context.get(f"upcoming_event_{asset}")
    if upcoming:
        ctx["upcoming_event_hours"] = upcoming.get("hours")
        ctx["event_name"]           = upcoming.get("name", "")

    return ctx
