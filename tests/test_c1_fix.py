"""
test_c1_fix.py — regresjonstest for korrelasjons-bias (C1).

Før fiksen: 9-kriterie-systemet kunne gi A-grade fra kun to uavhengige drivers
(trend + COT) fordi hver familie ble talt 3 ganger.

Etter fiksen: grade krever confluens på tvers av minst 3 driver-familier
(for A) eller 4 (for A+). Trend + COT alene er kun 2 familier = max B.

Kjøring:
    python3 tests/test_c1_fix.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import driver_matrix as dm


def test_c1_trend_plus_cot_alone_max_b():
    """Trend- og COT-familien full styrke, ingenting annet → max B."""
    result = dm.score_asset(
        direction="bull",
        asset="EURUSD", asset_class="fx",
        sma200_aligned=True, momentum_aligned=True, d1_4h_congruent=True,
        cot_bias_aligns=True, cot_pct=20.0, cot_momentum_aligns=True,
        # Ingen macro, ingen fundamental, ingen structure
    )
    assert result.grade in ("B", "C"), \
        f"C1 FAIL: trend+COT alene ga {result.grade}, forventet B eller C"
    assert result.active_driver_groups <= 2, \
        f"C1 FAIL: {result.active_driver_groups} familier aktive, forventet ≤2"
    print(f"PASS: trend+COT alene → grade={result.grade}, "
          f"active_driver_groups={result.active_driver_groups}, score={result.total_score:.2f}")


def test_four_groups_confluence_gives_a():
    """4 uavhengige familier med moderat score → minst A."""
    result = dm.score_asset(
        direction="bull",
        asset="Gold", asset_class="metals",
        sma200_aligned=True, momentum_aligned=True, d1_4h_congruent=False,
        cot_bias_aligns=True, cot_pct=15.0, cot_momentum_aligns=False,
        nearest_level_weight=4, smc_confirms=True,
        dxy_chg5d=-2.0, real_yield_10y=-0.2, vix_regime="elevated",
        comex_stress=45, registered_oz_change=-60000,
    )
    assert result.grade in ("A+", "A"), \
        f"FAIL: 4+ grupper confluence ga {result.grade}, forventet A/A+"
    assert result.active_driver_groups >= 4, \
        f"FAIL: {result.active_driver_groups} familier, forventet ≥4"
    print(f"PASS: 4-grupper confluence → grade={result.grade}, "
          f"active_driver_groups={result.active_driver_groups}, score={result.total_score:.2f}")


def test_single_group_gives_c():
    """Kun én familie aktiv → alltid C."""
    result = dm.score_asset(
        direction="bull",
        asset="SPX500", asset_class="indices",
        nearest_level_weight=5, smc_confirms=True,
        # Alt annet = 0
    )
    assert result.grade == "C", \
        f"FAIL: enkelt gruppe ga {result.grade}, forventet C"
    print(f"PASS: enkelt gruppe → grade={result.grade}, "
          f"active_driver_groups={result.active_driver_groups}")


def test_risk_gate_caps_grade_at_usda_blackout():
    """USDA blackout (risk_factors=3) skal kappe grade fra A+ til A."""
    result = dm.score_asset(
        direction="bull",
        asset="Corn", asset_class="grains",
        sma200_aligned=True, momentum_aligned=True, d1_4h_congruent=True,
        cot_bias_aligns=True, cot_pct=25.0, cot_momentum_aligns=True,
        nearest_level_weight=4, smc_confirms=True,
        dxy_chg5d=-2.0, yield_score=30, conab_mom=-5.0, conab_yoy=-12,
        usda_blackout=True,
    )
    # Uten gate: A+ (høy score, mange familier). Med gate: A.
    assert result.grade != "A+", \
        f"FAIL: risk-gate slo ikke inn, ga {result.grade}"
    print(f"PASS: USDA blackout risk-gate → grade={result.grade} "
          f"(ikke A+), risk.score={result.driver_groups['risk'].score:.2f}")


def test_horizon_auto_determination():
    """Horisont skal settes basert på antall familier + score."""
    # SWING: 3 familier, moderat score
    result = dm.score_asset(
        direction="bull", asset="EURUSD", asset_class="fx",
        sma200_aligned=True, momentum_aligned=True, d1_4h_congruent=True,
        cot_bias_aligns=True, cot_pct=15.0, cot_momentum_aligns=True,
        nearest_level_weight=3, smc_confirms=True,
    )
    assert result.horizon in ("SWING", "SCALP"), \
        f"FAIL: 3-grupper confluence ga horisont {result.horizon}"
    print(f"PASS: auto-horizon for 3-grupper SWING → {result.horizon}")


if __name__ == "__main__":
    print("═" * 60)
    print(" C1 regression tests — driver_matrix")
    print("═" * 60)
    tests = [
        test_c1_trend_plus_cot_alone_max_b,
        test_four_groups_confluence_gives_a,
        test_single_group_gives_c,
        test_risk_gate_caps_grade_at_usda_blackout,
        test_horizon_auto_determination,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {t.__name__}: {e}")
            failed += 1
    print("═" * 60)
    print(f" Resultat: {passed} passert, {failed} feilet")
    print("═" * 60)
    sys.exit(0 if failed == 0 else 1)
