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


def test_risk_gate_b_cap_at_extreme_event_pile_up():
    """Risk_factors >= 5 skal kappe grade til B.

    Konstruerer en pile-up: USDA blackout (3) + VIX ekstrem (2) + nær event
    (3) = 8 risk_factors. Tidligere var dette dead code fordi risk_factors
    ble derivert fra `score * 4` (capped på 4 → B-cap aldri trigget). Etter
    fixen i compute_risk_event (returnerer (GroupScore, int) tuple) skal
    B-cap nå være aktiv.
    """
    result = dm.score_asset(
        direction="bull",
        asset="Corn", asset_class="grains",
        sma200_aligned=True, momentum_aligned=True, d1_4h_congruent=True,
        cot_bias_aligns=True, cot_pct=25.0, cot_momentum_aligns=True,
        nearest_level_weight=4, smc_confirms=True,
        dxy_chg5d=-2.0, yield_score=30, conab_mom=-5.0, conab_yoy=-12,
        usda_blackout=True,
        vix_regime="extreme",
        upcoming_event_hours=1.0,
        event_name="NFP",
    )
    # Uten gate ville dette gitt A+ (perfekt setup). Med risk_factors=8 → B.
    assert result.grade == "B", \
        f"FAIL: B-cap (risk_factors >= 5) slo ikke inn, ga {result.grade}"
    print(f"PASS: pile-up risk → grade={result.grade} "
          f"(forventet B; tidligere dead code før compute_risk_event tuple-fix)")


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


# ──────────────────────────────────────────────────────────────
# Fase 1-4 regresjonstester (data-flow + C1 + staleness + grade-pct)
# ──────────────────────────────────────────────────────────────

def test_fred_score_only_in_fundamental_not_macro():
    """Fase 1: fund_instrument_score skal IKKE telle i MACRO (kun FUNDAMENTAL).
    Før Fase 1: score i begge familier → 4 aktive. Etter: kun FUNDAMENTAL aktiv.
    """
    result = dm.score_asset(
        direction="bull",
        asset="USDJPY", asset_class="fx",
        fund_instrument_score=1.5,  # Eneste input — kun FRED-score
        # Ingen DXY/VIX/yields/etc.
    )
    macro_sc = result.driver_groups["macro"].score
    fund_sc  = result.driver_groups["fundamental"].score
    assert macro_sc == 0.0, \
        f"FAIL: FRED-score lyste opp MACRO ({macro_sc}), skal kun være i FUNDAMENTAL"
    assert fund_sc > 0, \
        f"FAIL: FRED-score skal aktivere FUNDAMENTAL, fikk {fund_sc}"
    print(f"PASS: FRED-score kun i FUNDAMENTAL → macro={macro_sc:.2f}, "
          f"fund={fund_sc:.2f}, active={result.active_driver_groups}")


def test_real_yields_flow_to_metals_macro():
    """Fase 0.1 + Fase 1: real_yield_10y skal aktivere MACRO for metaller."""
    result = dm.score_asset(
        direction="bull",
        asset="Gold", asset_class="metals",
        real_yield_10y=-0.5,   # Negative real yields = bull gull
        real_yield_chg=-0.15,  # Faller = sterkere bull
    )
    macro_sc = result.driver_groups["macro"].score
    assert macro_sc > 0, \
        f"FAIL: Negative real yields ga ikke MACRO-score (fikk {macro_sc})"
    drivers = " ".join(result.driver_groups["macro"].drivers)
    assert "Real yields" in drivers, \
        f"FAIL: MACRO-drivers inkluderer ikke real yields: {drivers}"
    print(f"PASS: real_yield_10y={-0.5} → MACRO={macro_sc:.2f} "
          f"drivers={result.driver_groups['macro'].drivers}")


def test_fear_greed_activates_metals_macro():
    """Fase 1: extreme fear (F&G ≤ 25) skal aktivere MACRO for metals (safe-haven bid)."""
    result = dm.score_asset(
        direction="bull",
        asset="Gold", asset_class="metals",
        fear_greed=15,  # extreme fear
    )
    drivers = " ".join(result.driver_groups["macro"].drivers)
    assert "F&G" in drivers or "safe-haven" in drivers, \
        f"FAIL: F&G=15 (extreme fear) ga ikke safe-haven-bidrag for Gold: {drivers}"
    print(f"PASS: F&G=15 → Gold MACRO drivers: {result.driver_groups['macro'].drivers}")


def test_fear_greed_activates_indices_bear():
    """Fase 1: extreme greed (F&G ≥ 75) skal aktivere MACRO for indices (contrarian bear)."""
    result = dm.score_asset(
        direction="bear",
        asset="SPX", asset_class="indices",
        fear_greed=85,
    )
    drivers = " ".join(result.driver_groups["macro"].drivers)
    assert "F&G" in drivers or "greed" in drivers, \
        f"FAIL: F&G=85 (extreme greed) ga ikke bidrag for bear SPX: {drivers}"
    print(f"PASS: F&G=85 bear SPX → MACRO drivers: {result.driver_groups['macro'].drivers}")


def test_data_quality_fallback_caps_grade():
    """Fase 3: _fallback=True på kritisk input (real_yield) → data_quality=degraded → max A."""
    # Bygg en "perfekt A+-oppskrift": 4 familier aktive, høy score
    result = dm.score_asset(
        direction="bull",
        asset="Gold", asset_class="metals",
        sma200_aligned=True, momentum_aligned=True, d1_4h_congruent=True,
        cot_bias_aligns=True, cot_pct=25.0, cot_momentum_aligns=True,
        nearest_level_weight=4, smc_confirms=True,
        real_yield_10y=-0.5, real_yield_chg=-0.15,
        comex_stress=60, registered_oz_change=-100000,
        # Fase 3: marker real_yield som fallback (cache)
        _meta_real_yield_10y={"_fallback": True, "_age_hours": 24},
    )
    assert result.data_quality == "degraded", \
        f"FAIL: _fallback=True ga data_quality={result.data_quality}, forventet degraded"
    assert result.grade != "A+", \
        f"FAIL: degraded data skulle kappe grade fra A+, fikk {result.grade}"
    print(f"PASS: _fallback=True → data_quality=degraded, grade={result.grade} "
          f"(ikke A+), notes={result.quality_notes}")


def test_data_quality_stale_caps_to_b():
    """Fase 3: _cot_age_days > 20 → stale → max B."""
    result = dm.score_asset(
        direction="bull",
        asset="Silver", asset_class="metals",
        sma200_aligned=True, momentum_aligned=True, d1_4h_congruent=True,
        cot_bias_aligns=True, cot_pct=25.0, cot_momentum_aligns=True,
        nearest_level_weight=5, smc_confirms=True,
        real_yield_10y=-0.5, real_yield_chg=-0.15,
        comex_stress=70, registered_oz_change=-100000,
        _cot_age_days=25,  # Stale COT
    )
    assert result.data_quality == "stale", \
        f"FAIL: COT 25d gammel ga data_quality={result.data_quality}, forventet stale"
    assert result.grade in ("B", "C"), \
        f"FAIL: stale COT skulle kappe grade til B, fikk {result.grade}"
    print(f"PASS: COT=25d → data_quality=stale, grade={result.grade}")


def test_grade_pct_scales_across_horizons():
    """Fase 4: samme familie-score i ulike horisonter skal gi samme relative grade.

    Vi bruker samme perfekte trend+COT-oppskrift, men tvinger gjennom ulik
    horisont via horizon_hint. A/A+-grenser skal være relative, ikke absolutte.
    """
    kwargs = dict(
        direction="bull", asset="Gold", asset_class="metals",
        sma200_aligned=True, momentum_aligned=True, d1_4h_congruent=True,
        cot_bias_aligns=True, cot_pct=25.0, cot_momentum_aligns=True,
        nearest_level_weight=4, smc_confirms=True,
        real_yield_10y=-0.5, real_yield_chg=-0.15,
        comex_stress=50, registered_oz_change=-60000,
    )
    r_scalp = dm.score_asset(**kwargs, horizon_hint="SCALP")
    r_swing = dm.score_asset(**kwargs, horizon_hint="SWING")
    r_makro = dm.score_asset(**kwargs, horizon_hint="MAKRO")
    # Alle skal lande på samme grade når input er identisk
    # (grunnet prosent-normaliseringen i Fase 4)
    grades = {r_scalp.grade, r_swing.grade, r_makro.grade}
    assert len(grades) <= 2, \
        f"FAIL: samme input ga forskjellig grade i ulike horisonter: {grades}"
    print(f"PASS: grade pct-scaling SCALP={r_scalp.grade} "
          f"SWING={r_swing.grade} MAKRO={r_makro.grade}")


def test_gs_ratio_z_extreme_silver_bull():
    """Fase 0.1: GS-ratio-z > 2 + bull Silver → FUNDAMENTAL inkluderer GS-ratio-driver."""
    result = dm.score_asset(
        direction="bull",
        asset="Silver", asset_class="metals",
        gold_silver_ratio_z=2.5,
        comex_stress=30,  # litt trigger for å ikke få tom fundamental
    )
    drivers = " ".join(result.driver_groups["fundamental"].drivers)
    assert "GS-ratio" in drivers or "GS" in drivers, \
        f"FAIL: GS-Z=2.5 bull Silver ga ikke GS-ratio-driver: {drivers}"
    print(f"PASS: GS-Z=2.5 → Silver FUNDAMENTAL drivers: "
          f"{result.driver_groups['fundamental'].drivers}")


# ──────────────────────────────────────────────────────────────
# Fase 2.1 regresjonstester (disaggregated COT / positioning_v2)
# ──────────────────────────────────────────────────────────────

def test_mm_percentile_extreme_bull_activates_positioning():
    """MM på bunn-percentile (ekstremt underbefolket long) + bull-retning →
    contrarian-bull signal aktiverer POSITIONING selv uten COT-bias-match."""
    result = dm.score_asset(
        direction="bull", asset="Gold", asset_class="metals",
        cot_bias_aligns=False, cot_pct=-5.0, cot_momentum_aligns=False,
        mm_net_pctile_52w=5.0,   # Bunn 5 %
    )
    drivers = " ".join(result.driver_groups["positioning"].drivers)
    assert "percentile" in drivers.lower() or "contra-bull" in drivers, \
        f"FAIL: MM bunn-percentile ga ikke contrarian-signal: {drivers}"
    assert result.driver_groups["positioning"].score > 0.3, \
        f"FAIL: score for lav ({result.driver_groups['positioning'].score})"
    print(f"PASS: MM=5 pctile + bull → POSITIONING drivers: "
          f"{result.driver_groups['positioning'].drivers}")


def test_mm_comm_divergence_bear_topp_signal():
    """MM mye mer long enn Commercial (z=+2) + bear-retning = klassisk topp-signal."""
    result = dm.score_asset(
        direction="bear", asset="Gold", asset_class="metals",
        cot_bias_aligns=True, cot_pct=-10, cot_momentum_aligns=False,
        mm_comm_divergence_z=2.0,
    )
    drivers = " ".join(result.driver_groups["positioning"].drivers)
    assert "divergens" in drivers.lower() or "topp-signal" in drivers, \
        f"FAIL: MM/Comm divergens-ekstrem ga ikke topp-signal: {drivers}"
    print(f"PASS: MM/Comm z=+2 bear → drivers: "
          f"{result.driver_groups['positioning'].drivers}")


def test_oi_warning_reduces_positioning():
    """Stigende OI mot handelsretning skal redusere POSITIONING-score."""
    baseline = dm.score_asset(
        direction="bull", asset="Gold", asset_class="metals",
        cot_bias_aligns=True, cot_pct=15.0, cot_momentum_aligns=True,
    )
    with_warning = dm.score_asset(
        direction="bull", asset="Gold", asset_class="metals",
        cot_bias_aligns=True, cot_pct=15.0, cot_momentum_aligns=True,
        oi_regime_label="warning",   # OI bygger opp mot bull-retning
    )
    assert with_warning.driver_groups["positioning"].score \
         < baseline.driver_groups["positioning"].score, \
        f"FAIL: OI warning reduserte ikke score " \
        f"(baseline={baseline.driver_groups['positioning'].score}, " \
        f"warning={with_warning.driver_groups['positioning'].score})"
    print(f"PASS: OI warning reduserer score: "
          f"{baseline.driver_groups['positioning'].score:.2f} → "
          f"{with_warning.driver_groups['positioning'].score:.2f}")


def test_c1_still_holds_with_positioning_v2():
    """POSITIONING v2 kan ha 5-6 sub-signaler på maks, men C1-prinsippet skal
    holde: én familie alene kan ikke gi A-grade uten 3+ aktive familier."""
    r = dm.score_asset(
        direction="bull", asset="Gold", asset_class="metals",
        cot_bias_aligns=True, cot_pct=25.0, cot_momentum_aligns=True,
        mm_net_pctile_52w=3,          # Bunn-ekstrem
        mm_comm_divergence_z=-2.0,    # Bunn-divergens
        oi_regime_label="confirmation",
    )
    assert r.grade == "C", f"C1-brudd: POSITIONING alene ga {r.grade}"
    assert r.active_driver_groups <= 1
    print(f"PASS: POSITIONING maks alene → grade={r.grade} (C1 holder)")


def test_positioning_v2_backward_compat():
    """Uten nye kwargs skal v2 gi samme score som legacy-versjonen."""
    r = dm.score_asset(
        direction="bull", asset="EURUSD", asset_class="fx",
        cot_bias_aligns=True, cot_pct=20, cot_momentum_aligns=True,
        # Ingen mm_net_pctile_52w osv.
    )
    # 3 legacy subs, alle på 1.0 (strength=20/25=0.8) → ~(1+0.8+1)/3 = 0.93
    assert r.driver_groups["positioning"].score > 0.8, \
        f"FAIL: backward-compat score lav: {r.driver_groups['positioning'].score}"
    print(f"PASS: backward-compat uten nye kwargs → "
          f"score={r.driver_groups['positioning'].score:.2f}")


def test_index_investor_structural_long_for_agri_bull():
    """Index investor structurally long + bull Corn → additiv POSITIONING-bidrag."""
    baseline = dm.score_asset(
        direction="bull", asset="Corn", asset_class="grains",
        cot_bias_aligns=True, cot_pct=10, cot_momentum_aligns=False,
    )
    with_idx = dm.score_asset(
        direction="bull", asset="Corn", asset_class="grains",
        cot_bias_aligns=True, cot_pct=10, cot_momentum_aligns=False,
        index_investor_bias="structural_long",
    )
    drivers = " ".join(with_idx.driver_groups["positioning"].drivers)
    assert "Indeksfond" in drivers, \
        f"FAIL: index investor ga ikke driver: {drivers}"
    print(f"PASS: Index investor long + bull Corn → drivers: "
          f"{with_idx.driver_groups['positioning'].drivers}")


# ─── Runde 4: olje supply-disruption som POSITIONING-bias ───────────────

def test_oil_disruption_no_bull_bias_in_positioning():
    """LONG-signal på olje: POSITIONING skal IKKE få bull-bonus fra supply-
    disruption (FUNDAMENTAL_energy gir allerede +0.8). Score skal være
    uendret mellom med/uten disruption-flagg når direction='bull'."""
    baseline = dm.compute_positioning_v2(
        cot_bias_aligns=True, cot_pct=10, cot_momentum_aligns=True,
        direction="bull",
    )
    with_disrupt = dm.compute_positioning_v2(
        cot_bias_aligns=True, cot_pct=10, cot_momentum_aligns=True,
        direction="bull", oil_supply_disruption=True,
    )
    assert abs(with_disrupt.score - baseline.score) < 0.001, \
        f"FAIL: bull-disruption endret POSITIONING-score (skal være uendret), " \
        f"baseline={baseline.score}, ny={with_disrupt.score}"
    drivers = " ".join(with_disrupt.drivers)
    assert "Supply disruption" not in drivers, \
        f"FAIL: bull skal ikke ha supply-driver i POSITIONING (FUNDAMENTAL dekker)"
    print(f"PASS: oil disruption + bull → POSITIONING uendret "
          f"({baseline.score:.2f}) — FUNDAMENTAL_energy dekker bull-bidrag")


def test_oil_disruption_positioning_bias_bear():
    """SHORT-signal på olje med supply-disruption → POSITIONING får -0.4-bidrag."""
    baseline = dm.compute_positioning_v2(
        cot_bias_aligns=True, cot_pct=-10, cot_momentum_aligns=True,
        direction="bear",
    )
    with_disrupt = dm.compute_positioning_v2(
        cot_bias_aligns=True, cot_pct=-10, cot_momentum_aligns=True,
        direction="bear", oil_supply_disruption=True,
    )
    assert with_disrupt.score < baseline.score, \
        f"FAIL: bear-disruption skulle redusere score, baseline={baseline.score}, ny={with_disrupt.score}"
    drivers = " ".join(with_disrupt.drivers)
    assert "Supply disruption (advarer SHORT)" in drivers, \
        f"FAIL: forventet 'Supply disruption (advarer SHORT)' i drivers: {drivers}"
    print(f"PASS: oil disruption + bear → POSITIONING penalty "
          f"({baseline.score:.2f} → {with_disrupt.score:.2f}) drivers: {with_disrupt.drivers}")


def test_oil_score_asset_propagates_disruption_context():
    """score_asset for energy med oil_supply_disruption=True i context →
    POSITIONING-score skal være LAVERE enn uten flagget (bear-penalty -0.4
    aktiveres). Vi sammenligner score istedenfor driver-tekst fordi
    drivers[:3] kan presse ut supply-driveren ved mange aktive sub-signaler."""
    without_disrupt = dm.score_asset(
        direction="bear",
        sma200_aligned=False, momentum_aligned=True, d1_4h_congruent=True,
        cot_bias_aligns=True, cot_pct=-15, cot_momentum_aligns=True,
        asset="Brent", asset_class="energy",
        oil_supply_disruption=False,
        shipping_risk="HIGH",
    )
    with_disrupt = dm.score_asset(
        direction="bear",
        sma200_aligned=False, momentum_aligned=True, d1_4h_congruent=True,
        cot_bias_aligns=True, cot_pct=-15, cot_momentum_aligns=True,
        asset="Brent", asset_class="energy",
        oil_supply_disruption=True,
        shipping_risk="HIGH",
    )
    pos_baseline = without_disrupt.driver_groups["positioning"].score
    pos_disrupt  = with_disrupt.driver_groups["positioning"].score
    assert pos_disrupt < pos_baseline, \
        f"FAIL: context-propagering brutt — POSITIONING-score skulle synke, " \
        f"baseline={pos_baseline:.2f}, med disruption={pos_disrupt:.2f}"
    print(f"PASS: score_asset propagerer oil_supply_disruption → POSITIONING "
          f"({pos_baseline:.2f} → {pos_disrupt:.2f})")


def test_oil_disruption_does_not_force_dir_color():
    """Etter runde 4: oil_supply_disruption skal IKKE flippe direction internt
    i driver_matrix. score_asset skal ta direction som gitt og lar POSITIONING
    håndtere bias-justeringen."""
    bear_with_disrupt = dm.score_asset(
        direction="bear",
        sma200_aligned=False, momentum_aligned=True, d1_4h_congruent=True,
        cot_bias_aligns=True, cot_pct=-15, cot_momentum_aligns=True,
        asset="Brent", asset_class="energy",
        oil_supply_disruption=True,
    )
    assert bear_with_disrupt.direction == "bear", \
        f"FAIL: driver_matrix skulle ikke flippe direction, fikk {bear_with_disrupt.direction}"
    print(f"PASS: driver_matrix bevarer direction='bear' selv med oil_supply_disruption=True")


if __name__ == "__main__":
    print("═" * 60)
    print(" C1 regression tests — driver_matrix")
    print("═" * 60)
    tests = [
        test_c1_trend_plus_cot_alone_max_b,
        test_four_groups_confluence_gives_a,
        test_single_group_gives_c,
        test_risk_gate_caps_grade_at_usda_blackout,
        test_risk_gate_b_cap_at_extreme_event_pile_up,
        test_horizon_auto_determination,
        # Fase 1-4 nye tester
        test_fred_score_only_in_fundamental_not_macro,
        test_real_yields_flow_to_metals_macro,
        test_fear_greed_activates_metals_macro,
        test_fear_greed_activates_indices_bear,
        test_data_quality_fallback_caps_grade,
        test_data_quality_stale_caps_to_b,
        test_grade_pct_scales_across_horizons,
        test_gs_ratio_z_extreme_silver_bull,
        # Fase 2.1 positioning_v2 nye tester
        test_mm_percentile_extreme_bull_activates_positioning,
        test_mm_comm_divergence_bear_topp_signal,
        test_oi_warning_reduces_positioning,
        test_c1_still_holds_with_positioning_v2,
        test_positioning_v2_backward_compat,
        test_index_investor_structural_long_for_agri_bull,
        # Runde 4: olje supply-disruption som POSITIONING-bias
        test_oil_disruption_no_bull_bias_in_positioning,
        test_oil_disruption_positioning_bias_bear,
        test_oil_score_asset_propagates_disruption_context,
        test_oil_disruption_does_not_force_dir_color,
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
