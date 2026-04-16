#!/usr/bin/env python3
"""
Lightweight rescore — oppdaterer scores basert på nye priser UTEN API-kall.

Bruker kun data som allerede finnes i macro/latest.json (patchet av update_prices.sh).
Oppdaterer: sma200, momentum_20d, dir_color, horizon, score, grade.
Beholder: COT, HTF-nivåer, D1/4H alignment, fundamentals, SMC (statisk mellom fetch_all.py).

Kjøres i update_prices.sh etter prispatch, før push_signals.py.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

# ── Inline scoring-konstanter og funksjoner (unngår import av fetch_all.py som kjører hele modulen) ──
SCORE_WEIGHTS = {
    "sma200":             {"SCALP": 1.0,  "SWING": 1.0,  "MAKRO": 1.0},
    "momentum_20d":       {"SCALP": 1.0,  "SWING": 1.0,  "MAKRO": 1.0},
    "cot_confirms":       {"SCALP": 0,    "SWING": 1.0,  "MAKRO": 1.0},
    "cot_strong":         {"SCALP": 0,    "SWING": 0.5,  "MAKRO": 1.0},
    "cot_momentum":       {"SCALP": 0,    "SWING": 1.0,  "MAKRO": 1.0},
    "htf_level_weight":   {"SCALP": 1.0,  "SWING": 1.0,  "MAKRO": 1.0},
    "d1_4h_congruent":    {"SCALP": 1.0,  "SWING": 1.0,  "MAKRO": 1.0},
    "fred_fundamental":   {"SCALP": 0,    "SWING": 0,    "MAKRO": 1.0},
    "smc_confirms":       {"SCALP": 1.0,  "SWING": 1.0,  "MAKRO": 1.0},
}

GRADE_THRESHOLDS = {
    "SCALP": {"A+": 4.5, "A": 3.5, "B": 2.5},
    "SWING": {"A+": 6.5, "A": 5.5, "B": 4.0},
    "MAKRO": {"A+": 8.0, "A": 7.0, "B": 5.5},
}

def determine_horizon(criteria, nearest_level_weight):
    has_cot   = criteria.get("cot_confirms", False)
    raw_count = sum(1 for v in criteria.values() if v)
    def _ts(h):
        return sum(SCORE_WEIGHTS.get(c, {}).get(h, 0) for c, v in criteria.items() if v)
    if raw_count >= 6 and has_cot and nearest_level_weight >= 4:
        if _ts("MAKRO") >= 7.0: return "MAKRO"
    if raw_count >= 5 and nearest_level_weight >= 3:
        if _ts("SWING") >= 5.0: return "SWING"
    if raw_count >= 3: return "SCALP"
    return "WATCHLIST"

def calculate_weighted_score(criteria, horizon):
    h = horizon if horizon != "WATCHLIST" else "SCALP"
    score, details = 0.0, []
    for crit_id, passed in criteria.items():
        weight = SCORE_WEIGHTS.get(crit_id, {}).get(h, 0)
        earned = weight if passed else 0
        details.append({"id": crit_id, "verdi": passed, "vekt": weight, "poeng": earned})
        score += earned
    max_s = sum(w[h] for w in SCORE_WEIGHTS.values())
    return round(score, 1), round(max_s, 1), details

def get_grade(score, horizon):
    if horizon == "WATCHLIST": return "C", "bear"
    t = GRADE_THRESHOLDS[horizon]
    if score >= t["A+"]:  return "A+", "bull"
    elif score >= t["A"]: return "A",  "bull"
    elif score >= t["B"]: return "B",  "warn"
    return "C", "bear"

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

        # Hent eksisterende criteria-verdier (statiske mellom fetch_all.py)
        old_details = {d["id"]: d["verdi"] for d in lv.get("score_details", [])}

        # Oppdater kun de 2 pris-avhengige kriteriene
        criteria = {}
        for crit_id in SCORE_WEIGHTS:
            if crit_id == "sma200":
                criteria[crit_id] = above_sma
            elif crit_id == "momentum_20d":
                criteria[crit_id] = (chg20 > 0.5 and above_sma) or (chg20 < -0.5 and not above_sma)
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

        # DXY-konflikt
        dxy_conflict = lv.get("dxy_conflict", False)
        if dxy_conflict:
            penalty = 2.0 if horizon in ("SWING", "MAKRO") else 1.0
            score = max(0, round(score - penalty, 1))

        grade, grade_color = get_grade(score, horizon)

        # Signal-stabilitet (forenklet — kun retning-flip)
        prev = stab.get(key, {})
        prev_dir = prev.get("dir_color", "")
        dir_color = lv.get("dir_color", "bull")  # Behold eksisterende dir_color
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

        # Oppdater kun hvis noe endret seg
        if (lv.get("horizon") != horizon or
            lv.get("score") != score or
            lv.get("grade") != grade):
            lv["horizon"] = horizon
            lv["score"] = score
            lv["max_score"] = max_score
            lv["grade"] = grade
            lv["score_details"] = score_details
            lv["session_now"] = session_now
            lv["in_session"] = sesjon_riktig
            updated += 1

    # Skriv tilbake
    MACRO_FILE.write_text(json.dumps(macro, ensure_ascii=False, indent=2))
    print(f"rescore: {updated} instrumenter oppdatert (0 API-kall)")

if __name__ == "__main__":
    rescore()
