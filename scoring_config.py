"""
scoring_config.py — Delte scoring-konstanter og funksjoner.

Importert av: fetch_all.py, rescore.py, push_signals.py
Ingen side-effekter: ingen I/O, ingen API-kall, ingen print.
"""

# ─── VEKTER PER KRITERIUM PER HORISONT ───────────────────────────
# 9 kriterier — kun reelle setup-faktorer
# fred_fundamental kun for MAKRO (makrodata er månedlig, ikke relevant for kort sikt)
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
# MAX: SCALP=5.0, SWING=7.5, MAKRO=9.0
MAX_WEIGHTED_SCORE = {
    h: sum(w[h] for w in SCORE_WEIGHTS.values())
    for h in ("SCALP", "SWING", "MAKRO")
}

GRADE_THRESHOLDS = {
    "SCALP": {"A+": 4.5, "A": 3.5, "B": 2.5},
    "SWING": {"A+": 6.5, "A": 5.5, "B": 4.0},
    "MAKRO": {"A+": 8.0, "A": 7.0, "B": 5.5},
}

SCORE_LABELS_NO = {
    "sma200":             "Over SMA200",
    "momentum_20d":       "Momentum 20d",
    "cot_confirms":       "COT bekrefter",
    "cot_strong":         "COT sterk (>10%)",
    "cot_momentum":       "COT momentum Δ",
    "htf_level_weight":   "HTF-nivå ≥ 3",
    "d1_4h_congruent":    "D1+4H kongruent",
    "fred_fundamental":   "Fundamental (FRED)",
    "smc_confirms":       "SMC bekrefter",
}

# ─── KORRELASJONSGRUPPER (for bot max-posisjoner) ────────────────
CORRELATION_GROUPS = {
    "EURUSD": "usd_pairs", "GBPUSD": "usd_pairs",
    "USDJPY": "usd_pairs", "AUDUSD": "usd_pairs",
    "Gold": "precious_metals", "Silver": "precious_metals",
    "Brent": "energy", "WTI": "energy",
    "SPX": "us_indices", "NAS100": "us_indices",
}
MAX_CONCURRENT = {
    "precious_metals": 2, "us_indices": 1, "energy": 1, "usd_pairs": 2,
}

# ─── REGIME-BASERTE KORRELASJONSGRENSER ──────────────────────────
CORRELATION_REGIME_CONFIGS = {
    "normal": {
        "max_per_group": {"precious_metals": 2, "us_indices": 1, "energy": 1, "usd_pairs": 2},
        "max_total": 6,
    },
    "risk_off": {   # VIX > 25
        "max_per_group": {"precious_metals": 1, "us_indices": 1, "energy": 1, "usd_pairs": 1},
        "max_total": 3,
    },
    "crisis": {     # VIX > 35
        "max_per_group": {"precious_metals": 1, "us_indices": 1, "energy": 1, "usd_pairs": 1},
        "max_total": 2,
    },
}
VIX_CORRELATION_THRESHOLDS = {"risk_off": 25, "crisis": 35}

# ─── DXY-PENALTY KONFIGURASJON ───────────────────────────────────
DXY_MOMENTUM_THRESHOLD = 2.0   # 2% chg5d = full penalty

# ─── PUSH-TERSKLER ──────────────────────────────────────────────
PUSH_THRESHOLDS = {"SCALP": 3.0, "SWING": 4.5, "MAKRO": 5.5}
HORIZON_PRIORITY = {"MAKRO": 0, "SWING": 1, "SCALP": 2, "WATCHLIST": 3}

# ─── HORISONT-CONFIG (sendes til boten via signal_server) ────────
HORIZON_CONFIGS = {
    "SCALP": {
        "confirmation_tf": "5min",
        "confirmation_max_candles": 6,
        "confirmation_escape_atr_factor": 0.5,
        "confirmation_min_score": 2,
        "confirmation_strict_score": 3,
        "entry_zone_margin": 0.0015,
        "entry_zone_margin_atr": 0.3,      # 0.3×ATR(D1) — fallback til pct
        "exit_t1_close_pct": 0.50,
        "exit_t2_close_pct": 0.25,
        "exit_trail_tf": "5min",
        "exit_trail_atr_mult": {"fx": 2.0, "gold": 2.5, "silver": 2.5, "oil": 2.5, "index": 2.0},
        "exit_ema_tf": "5min",
        "exit_ema_period": 9,
        "exit_timeout_partial_candles": 8,
        "exit_timeout_partial_pct": 0.50,
        "exit_timeout_full_candles": 16,
        "exit_geo_spike_atr_mult": 2.0,
        "sizing_base_risk_usd": 20,
    },
    "SWING": {
        "confirmation_tf": "15min",
        "confirmation_max_candles": 8,
        "confirmation_escape_atr_factor": 0.7,
        "confirmation_min_score": 2,
        "confirmation_strict_score": 3,
        "entry_zone_margin": 0.0025,
        "entry_zone_margin_atr": 0.7,      # 0.7×ATR(D1)
        "exit_t1_close_pct": 0.33,
        "exit_t2_close_pct": 0.33,
        "exit_trail_tf": "1H",
        # Bot bruker 1H ATR for SWING — reelle verdier
        "exit_trail_atr_mult": {"fx": 3.0, "gold": 4.0, "silver": 4.0, "oil": 3.5, "index": 3.0},
        "exit_ema_tf": "1H",
        "exit_ema_period": 9,
        "exit_timeout_partial_candles": 96,   # 96×5m = 8 timer
        "exit_timeout_partial_pct": 0.50,
        "exit_timeout_full_hours": 120,       # 5 dager
        "exit_be_timeout_hours": 48,
        "exit_event_close_hours": 2,
        "exit_geo_spike_atr_mult": 3.0,
        "sizing_base_risk_usd": 40,
    },
    "MAKRO": {
        "confirmation_tf": "1H",
        "confirmation_max_candles": 6,
        "confirmation_escape_atr_factor": 1.0,
        "confirmation_min_score": 1,       # 1H candle: EMA gradient alene er nok
        "confirmation_strict_score": 2,     # Krever 2/3 ved motstridende USD
        "entry_zone_margin": 0.0040,
        "entry_zone_margin_atr": 1.2,      # 1.2×ATR(D1)
        "exit_t1_close_pct": 0.25,
        "exit_t2_close_pct": 0.25,
        "exit_trail_tf": "D1",
        # Bot bruker 1H ATR for MAKRO (D1 ikke implementert ennå) — 1H-justerte verdier
        # D1 ATR ≈ 2× 1H ATR, så 2.5 × D1 ≈ 5.0 × 1H
        "exit_trail_atr_mult": {"fx": 5.0, "gold": 6.0, "silver": 6.0, "oil": 5.5, "index": 5.0},
        "exit_ema_tf": "D1",
        "exit_ema_period": 9,
        "exit_timeout_partial_candles": 288,  # 288×5m = 24 timer
        "exit_timeout_partial_pct": 0.50,
        "exit_timeout_full_hours": 360,       # 15 dager
        "exit_timeout_days": 15,
        "exit_score_deterioration": 6.0,
        "exit_geo_spike_atr_mult": 3.0,
        "sizing_base_risk_usd": 60,
    },
}


# ─── DELTE SCORING-FUNKSJONER ────────────────────────────────────

def determine_horizon(criteria, nearest_level_weight):
    """Bestem horisont basert på 9 reelle kriterier, nivå-vekt OG vektet kvalitet.
    Max 9 kriterier: SCALP=5.0, SWING=7.5, MAKRO=9.0"""
    has_cot     = criteria.get("cot_confirms", False)
    raw_count   = sum(1 for v in criteria.values() if v)
    def _tentative_score(h):
        return sum(SCORE_WEIGHTS.get(c, {}).get(h, 0) for c, v in criteria.items() if v)
    # MAKRO: ≥6/9 treff + COT + sterk HTF-nivå + score ≥7.0/10.0
    if raw_count >= 6 and has_cot and nearest_level_weight >= 4:
        if _tentative_score("MAKRO") >= 7.0:
            return "MAKRO"
    # SWING: ≥5/9 treff + HTF-nivå ≥3 + score ≥5.0/8.5
    if raw_count >= 5 and nearest_level_weight >= 3:
        if _tentative_score("SWING") >= 5.0:
            return "SWING"
    # SCALP: ≥3/9 treff
    if raw_count >= 3:
        return "SCALP"
    return "WATCHLIST"


def calculate_weighted_score(criteria, horizon):
    """Beregn vektet score. Returnerer (score, max, details_list)."""
    h = horizon if horizon != "WATCHLIST" else "SCALP"
    score = 0.0
    details = []
    for crit_id, passed in criteria.items():
        weight = SCORE_WEIGHTS.get(crit_id, {}).get(h, 0)
        earned = weight if passed else 0
        details.append({
            "kryss":  SCORE_LABELS_NO.get(crit_id, crit_id),
            "id":     crit_id,
            "verdi":  passed,
            "vekt":   weight,
            "poeng":  earned,
        })
        score += earned
    return round(score, 1), MAX_WEIGHTED_SCORE[h], details


def get_grade(score, horizon):
    if horizon == "WATCHLIST":
        return "C", "bear"
    t = GRADE_THRESHOLDS[horizon]
    if score >= t["A+"]:  return "A+", "bull"
    elif score >= t["A"]: return "A",  "bull"
    elif score >= t["B"]: return "B",  "warn"
    return "C", "bear"
