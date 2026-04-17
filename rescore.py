#!/usr/bin/env python3
"""
Lightweight rescore — oppdaterer scores basert på nye priser UTEN API-kall.

Bruker kun data som allerede finnes i macro/latest.json (patchet av update_prices.sh).
Oppdaterer: sma200, momentum_20d, d1_4h_congruent, dir_color, horizon, score, grade.
Beholder: COT, HTF-nivåer, fundamentals, SMC (statisk mellom fetch_all.py).

Kjøres i update_prices.sh etter prispatch, før push_signals.py.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

from scoring_config import (
    SCORE_WEIGHTS, GRADE_THRESHOLDS, DXY_MOMENTUM_THRESHOLD,
    determine_horizon, calculate_weighted_score, get_grade,
)


def get_session_status():
    now = datetime.now(timezone.utc)
    import zoneinfo
    cet = now.astimezone(zoneinfo.ZoneInfo("Europe/Oslo"))
    ch, cm = cet.hour, cet.minute
    cet_min = ch * 60 + cm
    sessions = []
    if 7*60 <= cet_min < 12*60:  sessions.append("London")
    if 13*60 <= cet_min < 17*60: sessions.append("NY Overlap")
    if 8*60 <= cet_min < 12*60:  sessions.append("London Fix")
    if not sessions: sessions.append("Off-session")
    return {"active": any(s != "Off-session" for s in sessions),
            "label": " / ".join(sessions), "cet_hour": ch}

MACRO_FILE = Path("data/macro/latest.json")
STAB_FILE  = Path("data/macro/signal_stability.json")

def rescore():
    if not MACRO_FILE.exists():
        print("rescore: macro/latest.json finnes ikke — hopper over")
        return

    macro = json.loads(MACRO_FILE.read_text())
    levels = macro.get("trading_levels", {})
    prices = macro.get("prices", {})

    # Stabilitetsdata (for flip-sjekk)
    stab = json.loads(STAB_FILE.read_text()) if STAB_FILE.exists() else {}

    session_now = get_session_status()
    updated = 0

    for key, lv in levels.items():
        p = prices.get(key, {})
        curr  = p.get("price") or lv.get("current")
        chg20 = p.get("chg20d", 0) or 0
        sma200 = lv.get("sma200")
        if not curr or not sma200:
            continue

        above_sma = curr > sma200
        dir_color = lv.get("dir_color", "bull")

        # Hent eksisterende criteria-verdier (statiske mellom fetch_all.py)
        old_details = {d["id"]: d["verdi"] for d in lv.get("score_details", [])}

        # Oppdater pris-avhengige kriterier: sma200, momentum_20d, d1_4h_congruent
        criteria = {}
        for crit_id in SCORE_WEIGHTS:
            if crit_id == "sma200":
                criteria[crit_id] = above_sma
            elif crit_id == "momentum_20d":
                criteria[crit_id] = (chg20 > 0.5 and above_sma) or (chg20 < -0.5 and not above_sma)
            elif crit_id == "d1_4h_congruent":
                # Oppdater basert på lagrede EMA-verdier (ingen API-kall)
                ema9_d1 = lv.get("ema9_d1")
                ema9_4h = lv.get("ema9_4h")
                if ema9_d1 is not None and ema9_4h is not None:
                    if dir_color == "bull":
                        criteria[crit_id] = curr > ema9_d1 and curr > ema9_4h
                    else:
                        criteria[crit_id] = curr < ema9_d1 and curr < ema9_4h
                else:
                    criteria[crit_id] = old_details.get(crit_id, False)
            else:
                criteria[crit_id] = old_details.get(crit_id, False)

        # Nearest level weight (cachet)
        nlw = lv.get("nearest_level_weight", 1)
        # Fallback: beregn fra supports/resistances
        if nlw == 1 or "nearest_level_weight" not in lv:
            sups = lv.get("supports", [])
            ress = lv.get("resistances", [])
            sup_w = max((l["weight"] for l in sups if l.get("dist_atr", 99) <= 2.0), default=0) if sups else 0
            res_w = max((l["weight"] for l in ress if l.get("dist_atr", 99) <= 2.0), default=0) if ress else 0
            if sup_w == 0 and sups: sup_w = sups[0]["weight"]
            if res_w == 0 and ress: res_w = ress[0]["weight"]
            nlw = max(sup_w, res_w)

        horizon = determine_horizon(criteria, nlw)
        score, max_score, score_details = calculate_weighted_score(criteria, horizon)

        # DXY-konflikt — graduert penalty
        dxy_conflict = lv.get("dxy_conflict", False)
        if dxy_conflict:
            dxy_strength = lv.get("dxy_momentum_strength", 1.0) or 1.0
            base_penalty = 2.0 if horizon in ("SWING", "MAKRO") else 1.0
            penalty = round(base_penalty * dxy_strength, 2)
            score = max(0, round(score - penalty, 1))

        grade, grade_color = get_grade(score, horizon)

        # Signal-stabilitet (forenklet — kun retning-flip)
        prev = stab.get(key, {})
        prev_dir = prev.get("dir_color", "")
        # Oppdater dir_color basert på SMA200 (forenklet — full dir_score krever chg5d + COT)
        if above_sma and dir_color == "bear":
            pass  # Behold bear — full rescore i fetch_all.py
        elif not above_sma and dir_color == "bull":
            pass  # Behold bull — full rescore i fetch_all.py

        if prev_dir and prev_dir != dir_color:
            if horizon == "MAKRO":    horizon = "SWING"
            elif horizon == "SWING":  horizon = "SCALP"
            elif horizon == "SCALP":  horizon = "WATCHLIST"
            score, max_score, score_details = calculate_weighted_score(criteria, horizon)
            grade, grade_color = get_grade(score, horizon)

        # Sesjon-filter
        klasse = lv.get("klasse", "A")
        sesjon_riktig = (
            (klasse == "A" and "London" in session_now["label"]) or
            (klasse == "B" and ("London" in session_now["label"] or "NY" in session_now["label"])) or
            (klasse == "C" and "NY" in session_now["label"])
        )
        if horizon == "SCALP" and not sesjon_riktig:
            horizon = "WATCHLIST"
            grade, grade_color = "C", "bear"

        # Oppdater kun session + evt. horizon-downgrade ved signal-flip.
        # score/max_score/grade/score_details eies na av driver_matrix i
        # fetch_all.py (schema 2.0). Hvis rescore overskriver dem med legacy
        # 9-kriterie-verdier (SCALP=5.0, SWING=7.5, MAKRO=9.0) blir det
        # inkonsistent med driver matrix-skala (SCALP=4.2, SWING=5.0, MAKRO=5.2).
        prev_horizon = lv.get("horizon")
        if prev_horizon != horizon:
            # Kun horizon-endring hvis rescore-beregningen valgte en
            # STRENGERE horisont (f.eks. etter signal-flip).
            HORIZON_RANK = {"MAKRO": 0, "SWING": 1, "SCALP": 2, "WATCHLIST": 3}
            if HORIZON_RANK.get(horizon, 3) > HORIZON_RANK.get(prev_horizon, 3):
                lv["horizon"] = horizon
                updated += 1
        if lv.get("session_now") != session_now or lv.get("in_session") != sesjon_riktig:
            lv["session_now"] = session_now
            lv["in_session"] = sesjon_riktig
            updated += 1

    # Skriv tilbake
    MACRO_FILE.write_text(json.dumps(macro, ensure_ascii=False, indent=2))
    print(f"rescore: {updated} instrumenter oppdatert (0 API-kall)")

if __name__ == "__main__":
    rescore()
