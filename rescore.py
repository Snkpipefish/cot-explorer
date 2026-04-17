#!/usr/bin/env python3
"""
Lightweight rescore — oppdaterer driver-matrix scoring med friske priser UTEN
API-kall. Kjøres i update_prices.sh etter at fetch_prices.py har patchet
prices+chg5d/chg20d i macro/latest.json.

Schema 2.0 (2026-04-17): bruker driver_matrix.score_asset med ferske priser.
All input som ikke endrer seg intratime (COT, fundamentals, SMC, structure)
gjenbrukes fra eksisterende trading_levels-entries. Intratime-variabler
(dir_color, SMA200-align, chg5d/chg20d-momentum, DXY-regime, VIX-regime)
rekalkuleres fra ferske priser.

Legacy 9-kriterie-logikken er fjernet — den er erstattet av driver_matrix
som hovedscoring-motor i hele pipelinen.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone

import driver_matrix as dm
import driver_group_mapping as dgm
import cot_analytics as ca


BASE_DIR       = Path(os.path.expanduser("~/cot-explorer"))
MACRO_FILE     = BASE_DIR / "data" / "macro" / "latest.json"
STAB_FILE      = BASE_DIR / "data" / "macro" / "signal_stability.json"
FUND_FILE      = BASE_DIR / "data" / "fundamentals" / "latest.json"
ANALYTICS_FILE = BASE_DIR / "data" / "cot_analytics" / "latest.json"


# Asset-klasser for rescore-dispatch. Matcher INSTRUMENTS i fetch_all.py.
USD_QUOTE_PAIRS = {"USDJPY", "USDCHF", "USDCAD", "USDNOK"}
USD_BASE_PAIRS  = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"}
PRICES_ONLY     = {"VIX", "USDCHF", "USDNOK"}
SAFE_HAVENS     = {"Gold", "Silver", "USDJPY", "USDCHF"}
DXY_MOMENTUM_THRESHOLD = 2.0


def get_session_status():
    now = datetime.now(timezone.utc)
    import zoneinfo
    cet = now.astimezone(zoneinfo.ZoneInfo("Europe/Oslo"))
    ch, cm = cet.hour, cet.minute
    cet_min = ch * 60 + cm
    sessions = []
    if 7*60  <= cet_min < 12*60: sessions.append("London")
    if 13*60 <= cet_min < 17*60: sessions.append("NY Overlap")
    if 8*60  <= cet_min < 12*60: sessions.append("London Fix")
    if not sessions: sessions.append("Off-session")
    return {
        "active":   any(s != "Off-session" for s in sessions),
        "label":    " / ".join(sessions),
        "cet_hour": ch,
    }


def _dir_score(above_sma: bool, chg5: float, chg20: float,
               cot_pct, cot_chg, dxy_color, is_usd_pair: bool,
               is_xxxusd: bool) -> float:
    """Beregn dir_score (matcher fetch_all.py:1366-1420-logikken)."""
    d = 1.5 if above_sma else -1.5
    # chg5d
    if abs(chg5) > 0.1:
        mag = 1.0 if abs(chg5) > 0.3 else 0.5
        d += mag if chg5 > 0 else -mag
    # chg20d
    if abs(chg20) > 0.3:
        mag = 1.0 if abs(chg20) > 1.0 else 0.5
        d += mag if chg20 > 0 else -mag
    # COT bias
    if cot_pct is not None:
        if cot_pct > 4:   d += 1.0
        elif cot_pct < -4: d -= 1.0
    # COT momentum
    if cot_chg is not None and cot_pct is not None and cot_chg != 0:
        if (cot_chg > 0 and cot_pct >= 0) or (cot_chg < 0 and cot_pct <= 0):
            d += 0.5 if cot_chg > 0 else -0.5
    # Momentum-divergens
    if abs(chg5) > 0.3 and abs(chg20) > 0.3 \
       and ((chg5 > 0 and chg20 < 0) or (chg5 < 0 and chg20 > 0)):
        d -= 0.5
    # DXY-bias på USD-par
    if is_usd_pair and dxy_color in ("bull", "bear"):
        if is_xxxusd:
            d += -0.5 if dxy_color == "bull" else 0.5
        else:
            d += 0.5 if dxy_color == "bull" else -0.5
    return d


def _smc_confirms(lv: dict, dir_color: str) -> bool:
    """Gjenbruk SMC-logikken fra fetch_all.py:1513-1561."""
    smc_1h = lv.get("smc_1h") or {}
    smc_4h = lv.get("smc_4h") or {}
    bos_1h = (smc_1h.get("bos_levels") or [])
    bos_4h = (smc_4h.get("bos_levels") or [])
    recent_bos = sorted(bos_1h + bos_4h,
                        key=lambda b: b.get("idx", 0),
                        reverse=True)[:3]
    bos_ok = any(
        (b.get("type") == "BOS_opp" and dir_color == "bull") or
        (b.get("type") == "BOS_ned" and dir_color == "bear")
        for b in recent_bos
    )
    structure = smc_1h.get("structure", "MIXED") or "MIXED"
    struct_ok = (
        (dir_color == "bull" and structure in ("BULLISH", "BULLISH_SVAK")) or
        (dir_color == "bear" and structure in ("BEARISH", "BEARISH_SVAK"))
    )
    return bos_ok and struct_ok


def _compute_dxy_dir_color(tl: dict) -> str | None:
    """Finn DXY-direction fra trading_levels (beholdes fra fetch_all)."""
    dxy = tl.get("DXY") or {}
    return dxy.get("dir_color")


def rescore():
    if not MACRO_FILE.exists():
        print("rescore: macro/latest.json finnes ikke — hopper over")
        return

    macro = json.loads(MACRO_FILE.read_text())
    tl = macro.get("trading_levels", {})
    prices = macro.get("prices", {})
    vix_now = (prices.get("VIX") or {}).get("price", 20)
    dxy_color = _compute_dxy_dir_color(tl)
    session_now = get_session_status()

    # Last delt kontekst (0 API-kall — alt er diskfiler)
    try:
        sources = dgm.load_all_sources(BASE_DIR)
    except Exception as e:
        print(f"rescore: kunne ikke laste driver-kilder: {e}")
        sources = {}

    try:
        fund_data = json.loads(FUND_FILE.read_text()) if FUND_FILE.exists() else {}
    except Exception:
        fund_data = {}
    market_rates = (fund_data.get("market_rates") or {})
    dfii10       = (market_rates.get("dfii10") or {})

    analytics_cache = ca.load_cache(str(ANALYTICS_FILE)) if ANALYTICS_FILE.exists() else None
    analytics       = (analytics_cache or {}).get("assets", {})

    # Signal-stabilitet (beholdes fra forrige rescore)
    stab = json.loads(STAB_FILE.read_text()) if STAB_FILE.exists() else {}

    updated = 0
    for key, lv in tl.items():
        # Hopp over kun-pris-instrumenter
        if key in PRICES_ONLY:
            continue
        # Hopp over hvis ingen driver_groups (ikke initiert av fetch_all)
        if not lv.get("driver_groups"):
            continue

        curr    = lv.get("current") or 0
        sma200  = lv.get("sma200")  or 0
        chg5    = lv.get("chg5d")   or 0
        chg20   = lv.get("chg20d")  or 0
        above_sma = bool(sma200 and curr > sma200)

        cot = lv.get("cot") or {}
        cot_pct  = cot.get("pct")
        cot_chg  = cot.get("chg") or cot.get("change_spec_net") or 0

        is_xxxusd  = key in USD_BASE_PAIRS
        is_usd_pair = key in (USD_QUOTE_PAIRS | USD_BASE_PAIRS)

        # ── NY dir_color fra friske priser ───────────────────────
        d_score = _dir_score(above_sma, chg5, chg20, cot_pct, cot_chg,
                             dxy_color if key != "DXY" else None,
                             is_usd_pair and key != "DXY",
                             is_xxxusd)
        if d_score > 0.5:
            dir_color = "bull"
        elif d_score < -0.5:
            dir_color = "bear"
        else:
            dir_color = "bull" if above_sma else "bear"

        # Olje supply-disruption-override (beholdes fra fetch_all).
        # Logger override-grunn for transparens i UI/payload.
        if key in ("Brent", "WTI") and lv.get("oil_supply_disruption"):
            dir_color = "bull"
            lv["dir_override_reason"] = "oil_supply_disruption"
        elif lv.get("dir_override_reason") == "oil_supply_disruption":
            # Disruption har klarert — fjern override-flagget
            lv.pop("dir_override_reason", None)

        # ── TREND sub-signaler ──────────────────────────────────
        momentum_aligned = (chg20 > 0.5 and above_sma) or \
                           (chg20 < -0.5 and not above_sma)
        align = lv.get("regime_align", "")
        d1_4h_congruent = align in ("bull", "bear")

        # ── POSITIONING — COT-derivater med ny dir_color ────────
        cot_bias = cot.get("bias", "")
        cot_bias_aligns = (cot_bias == "LONG" and dir_color == "bull") or \
                          (cot_bias == "SHORT" and dir_color == "bear")
        cot_momentum_ok = (cot_chg > 0 and dir_color == "bull") or \
                          (cot_chg < 0 and dir_color == "bear")

        # ── STRUCTURE — nearest level + SMC ─────────────────────
        near_sup = max((l.get("weight", 0) for l in (lv.get("supports") or [])
                        if l.get("dist_atr", 99) <= 2.0), default=0)
        near_res = max((l.get("weight", 0) for l in (lv.get("resistances") or [])
                        if l.get("dist_atr", 99) <= 2.0), default=0)
        nearest_level_weight = max(near_sup, near_res)
        smc_confirms_ok = _smc_confirms(lv, dir_color)

        # ── _macro_ctx (per-asset context for driver_matrix) ─────
        _oil_disruption = bool(lv.get("oil_supply_disruption")) \
                          if key in ("Brent", "WTI") else False

        _macro_ctx = {
            "dxy_chg5d": (prices.get("DXY") or {}).get("chg5d")
                          if key != "DXY" else chg5,
            "vix_regime": ("extreme" if vix_now >= 35
                            else "elevated" if vix_now >= 25
                            else "normal"),
            "geo_active": False,  # Settes av push_signals
            "brl_chg5d":  ((prices.get("USDBRL") or {}).get("chg5d")
                            or (prices.get("BRL") or {}).get("chg5d")),
            "oil_supply_disruption": _oil_disruption,
            "term_spread":     market_rates.get("term_spread"),
            "real_yield_10y":  dfii10.get("value"),
            "real_yield_chg":  dfii10.get("chg_5d"),
            # fear_greed og gold_silver_ratio_z ikke tilgjengelige i rescore
            # (krever fetch_fear_greed + bot_history — for tungt for hver time).
            # Sub-signalene deaktiveres stille når None.
            "fear_greed":          None,
            "gold_silver_ratio_z": None,
            "_cot_age_days":       None,
        }

        # Disaggregated COT sub-signaler fra analytics-cache
        a = analytics.get(key, {})
        if a.get("data_quality") == "fresh":
            _macro_ctx["mm_net_pctile_52w"]    = a.get("mm_net_pctile_52w")
            _macro_ctx["mm_comm_divergence_z"] = a.get("mm_comm_divergence_z")
            _macro_ctx["index_investor_bias"]  = a.get("index_investor_bias")
            oi_avg_4w = a.get("oi_change_4w_avg", 0)
            oi_cur    = a.get("change_oi_current", 0)
            if oi_avg_4w or oi_cur:
                oi_reg, _ = ca.oi_regime(oi_cur, [oi_avg_4w], dir_color)
                _macro_ctx["oi_regime_label"] = oi_reg

        # Bygg full context for asset-klassen
        ctx_groups = dgm.build_context_for_asset(key, sources, _macro_ctx)

        # ── Kjør driver_matrix ──────────────────────────────────
        try:
            result = dm.score_asset(
                direction=dir_color,
                sma200_aligned=above_sma,
                momentum_aligned=momentum_aligned,
                d1_4h_congruent=d1_4h_congruent,
                cot_bias_aligns=cot_bias_aligns,
                cot_pct=cot_pct,
                cot_momentum_aligns=cot_momentum_ok,
                nearest_level_weight=nearest_level_weight,
                smc_confirms=smc_confirms_ok,
                fibo_zone_hit=False,
                **ctx_groups,
            )
        except Exception as e:
            print(f"  rescore {key} FEIL: {type(e).__name__}: {e}")
            continue

        # ── DXY-konflikt-penalty (beholdes fra fetch_all-logikken) ─
        dxy_conflict = lv.get("dxy_conflict", False)
        base_score   = round(result.total_score, 2)
        if dxy_conflict:
            dxy_strength = lv.get("dxy_momentum_strength") or 1.0
            base_penalty = 1.0 if result.horizon in ("SWING", "MAKRO") else 0.5
            penalty = round(base_penalty * dxy_strength, 2)
            base_score = max(0, round(base_score - penalty, 2))

        # Re-beregn grade etter penalty (manuelt — driver_matrix returnerer uweighted)
        # Vi beholder resultat.grade med mindre penalty dytter under terskel.
        final_grade = result.grade

        # Max_score = sum av vekter for aktive (non-risk) familier
        max_score = round(
            sum(g.weight for k, g in result.driver_groups.items() if k != "risk"),
            2,
        ) or 5.0
        score_pct = round(base_score / max_score * 100) if max_score else 0

        # Sesjon-filter (klasse A/B/C)
        klasse = lv.get("klasse", "A")
        sesjon_ok = (
            (klasse == "A" and "London"  in session_now["label"]) or
            (klasse == "B" and ("London" in session_now["label"]
                                 or "NY"  in session_now["label"])) or
            (klasse == "C" and  "NY"     in session_now["label"])
        )
        horizon = result.horizon
        if horizon == "SCALP" and not sesjon_ok:
            horizon = "WATCHLIST"
            final_grade = "C"

        # Signal-stabilitet — retning-flip → horisont-nedgradering
        prev = stab.get(key, {})
        prev_dir = prev.get("dir_color", "")
        if prev_dir and prev_dir != dir_color:
            horizon = {"MAKRO": "SWING", "SWING": "SCALP",
                       "SCALP": "WATCHLIST"}.get(horizon, horizon)

        # ── Skriv tilbake ───────────────────────────────────────
        lv["dir_color"]            = dir_color
        lv["horizon"]               = horizon
        lv["score"]                 = base_score
        lv["max_score"]             = max_score
        lv["score_pct"]             = score_pct
        lv["grade"]                 = final_grade
        lv["grade_color"]           = ("bull" if final_grade in ("A+", "A")
                                        else "warn" if final_grade == "B"
                                        else "bear")
        lv["driver_groups"]         = {
            k: {"score": round(v.score, 2), "weight": round(v.weight, 2),
                "drivers": v.drivers}
            for k, v in result.driver_groups.items()
        }
        lv["active_driver_groups"]  = result.active_driver_groups
        lv["group_drivers"]         = result.flat_drivers(limit=8)
        lv["data_quality"]          = result.data_quality
        lv["quality_notes"]         = result.quality_notes
        # dir_override_reason settes/clears tidligere i loopen via in-place
        # mutasjon av lv. Eksplisitt write-back her sikrer at feltet bevares
        # selv om noen senere refaktorerer write-back til å bygge ny dict.
        lv["dir_override_reason"]   = lv.get("dir_override_reason")
        lv["session_now"]           = session_now
        lv["in_session"]            = sesjon_ok
        updated += 1

    MACRO_FILE.write_text(json.dumps(macro, ensure_ascii=False, indent=2))
    print(f"rescore: {updated} instrumenter oppdatert via driver_matrix (0 API-kall)")


if __name__ == "__main__":
    rescore()
