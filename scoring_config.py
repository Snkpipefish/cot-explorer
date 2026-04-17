"""
scoring_config.py — Delte scoring-konstanter.

Importert av: fetch_all.py, rescore.py, push_signals.py
Ingen side-effekter: ingen I/O, ingen API-kall, ingen print.

Schema 2.0 (2026-04): legacy 9-kriterie-scoring (SCORE_WEIGHTS, MAX_WEIGHTED_SCORE,
GRADE_THRESHOLDS, calculate_weighted_score, get_grade, determine_horizon) er
fjernet — erstattet av driver_matrix.py som hovedscoring-motor. Denne filen
inneholder nå kun korrelasjons-grenser, horisont-konfig og push-terskler.
"""

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

# ─── AGRI KORRELASJONSGRUPPER ──────────────────────────────────
# Mais/soya/hvete korrelerer .85+ i trender — maks 1 per sub-gruppe
# Kaffe/sukker/kakao er softs-kluster — maks 1 per sub-gruppe
# Bomull er lavt korrelert med begge — eget cluster
AGRI_CORRELATION_SUBGROUPS = {
    "Corn": "grains", "Wheat": "grains", "Soybean": "grains",
    "Coffee": "softs", "Sugar": "softs", "Cocoa": "softs",
    "Cotton": "cotton",
}
AGRI_MAX_PER_SUBGROUP = 1

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
# Schema 2.0: driver_matrix bruker 0-6 skala (sum av 5 scoring-familier).
# Terskler alignet med HORIZON_GATES i driver_matrix (hvis horisont er
# auto-valgt til SWING, har signalet per definisjon score ≥ 2.5):
#   SCALP:  1.5  (horizon SCALP-gate)
#   SWING:  2.5  (horizon SWING-gate — enhver SWING-signal skal kunne pushes)
#   MAKRO:  3.5  (horizon MAKRO-gate)
# Legacy 9-kriterie-systemet (0-9 skala) brukte 3.0/4.5/5.5.
PUSH_THRESHOLDS = {"SCALP": 1.5, "SWING": 2.5, "MAKRO": 3.5}
HORIZON_PRIORITY = {"MAKRO": 0, "SWING": 1, "SCALP": 2, "WATCHLIST": 3}

# ─── AGRI SCORE-SKALA ───────────────────────────────────────────
# Agri bruker egen additiv skala (ikke driver_matrix 0-6). Teoretisk maks =
# outlook(5) + yield(3) + weather(2) + enso(2) + conab(2) + unica(2) + cross(2) = 18.
# Brukes av push_signals.py for `max_score`-feltet (UI score_pct = score/max).
AGRI_MAX_SCORE = 18

# ─── AGRI SIGNAL-AGING ──────────────────────────────────────────
# Maks avstand (i ATR-multipler) mellom live pris og entry før agri-signal
# regnes som utdatert. Speiler `should_push`-logikken for tekniske signaler.
AGRI_MAX_AGE_ATR = {"SCALP": 1.5, "SWING": 2.5, "MAKRO": 4.0}

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


# Legacy scoring-funksjoner (determine_horizon, calculate_weighted_score,
# get_grade) er fjernet i schema 2.0. Bruk driver_matrix.score_asset i
# stedet — den tar over scoring på tvers av fetch_all.py og rescore.py.
