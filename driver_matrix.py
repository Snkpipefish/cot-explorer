"""
driver_matrix.py — 6-familie-scoring som fikser korrelasjons-bias (C1)

Problem det løser:
  Gamle 9-kriterie-systemet hadde 3 trend-kriterier og 3 COT-kriterier som
  kunne fyre på SAMME underliggende driver, slik at to uavhengige signaler
  ga A-grade. Dette systemet krever CONFLUENS PÅ TVERS AV UAVHENGIGE
  DATAKILDE-FAMILIER for å nå A/A+ grade.

Seks familier:
  TREND         — SMA200, momentum, D1/4H align                  (composite)
  POSITIONING   — COT bias/styrke/momentum                       (composite)
  MACRO         — DXY, VIX, real yields, yield curve, F&G        (asset-specific)
  FUNDAMENTAL   — asset-spesifikk tilbud/etterspørsel            (asset-specific)
  RISK/EVENT    — kalender, geo, event-avstand                   (modifier)
  STRUCTURE     — HTF-nivå, SMC, fibo                            (composite)

Hver familie returnerer (score 0-1, drivers list[str]). Grade bygges av:
  - total = sum(group_score * horizon_weight)
  - active_driver_groups = count der score >= 0.3
  - grade kombinerer begge i grade()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ─── FAMILIE-INTERNE TERSKLER ────────────────────────────────────────────

GROUP_ACTIVE_THRESHOLD = 0.3   # Score >= dette teller som "aktiv familie"

# Grade krever både poeng OG antall aktive familier
# Kalibrert for realistiske gruppe-scores (0.5-0.8 per aktive familie):
#   4+ active × 1.0 = 4.0 score → A+
#   3+ active × 1.0 = 3.0 score → A
#   2+ active × 1.0 = 2.0 score → B
# C1-fiks bevares: 2 familier kan IKKE nå A (trenger 3 til A).
GRADE_RULES = [
    # (grade, min_score, min_active_families)
    ("A+", 4.0, 4),
    ("A",  3.0, 3),
    ("B",  2.0, 2),
]

HORIZON_GROUP_WEIGHTS = {
    "SCALP":  {"trend": 1.2, "positioning": 0.5, "macro": 0.7,
               "fundamental": 0.5, "risk": 0.8, "structure": 1.3},
    "SWING":  {"trend": 1.0, "positioning": 1.0, "macro": 1.0,
               "fundamental": 1.0, "risk": 1.0, "structure": 1.0},
    "MAKRO":  {"trend": 0.8, "positioning": 1.3, "macro": 1.3,
               "fundamental": 1.3, "risk": 0.8, "structure": 0.5},
}

# Horisont-bestemmelse baseres på minst N aktive familier OG score-krav
HORIZON_GATES = [
    # (horizon, min_score, min_active, extra_check)
    # MAKRO: 4+ familier, høyt score, må inkludere fundamental eller macro
    ("MAKRO", 3.5, 4, lambda driver_groups: (driver_groups.get("fundamental", 0) + driver_groups.get("macro", 0)) >= 0.7),
    ("SWING", 2.5, 3, None),
    ("SCALP", 1.5, 2, None),
]


# ─── DATAKLASSER ─────────────────────────────────────────────────────────

@dataclass
class GroupScore:
    """Resultat fra én familie-funksjon."""
    score:   float          # 0-1
    drivers: list[str]      # Tekst-drivere for display
    weight:  float = 1.0    # Settes av horisont-kontekst


@dataclass
class GroupResult:
    """Samlet resultat for alle 6 familier."""
    driver_groups:        dict[str, GroupScore]
    total_score:     float
    active_driver_groups: int
    grade:           str
    horizon:         str
    direction:       str                 # "bull"/"bear"/"?"

    def flat_drivers(self, limit: int = 8) -> list[str]:
        """Returnér alle drivers flatet med familie-prefiks, toppen først."""
        order = ["fundamental", "macro", "positioning", "trend", "structure", "risk"]
        out = []
        for group_key in order:
            grp = self.driver_groups.get(group_key)
            if not grp:
                continue
            for d in grp.drivers:
                out.append(d)
                if len(out) >= limit:
                    return out
        return out

    def to_dict(self) -> dict:
        """JSON-serialisering for trading_levels."""
        return {
            "grade":            self.grade,
            "score":            round(self.total_score, 2),
            "active_driver_groups":  self.active_driver_groups,
            "horizon":          self.horizon,
            "direction":        self.direction,
            "driver_groups": {
                k: {"score": round(v.score, 2), "weight": v.weight,
                    "drivers": v.drivers}
                for k, v in self.driver_groups.items()
            },
            "group_drivers":   self.flat_drivers(limit=8),
        }


# ─── FAMILIE 1: TREND ────────────────────────────────────────────────────

def compute_trend(sma200_aligned: bool,
                  momentum_aligned: bool,
                  d1_4h_congruent: bool) -> GroupScore:
    """Composite trend-score fra tre delsignaler (ikke additivt 3×).

    Alle tre gir 1.0. En av tre gir 0.33. Ingen gir 0.0.
    """
    signals = [sma200_aligned, momentum_aligned, d1_4h_congruent]
    active = sum(1 for s in signals if s)
    score  = active / 3.0
    drivers = []
    if sma200_aligned:    drivers.append("SMA200-align")
    if momentum_aligned:  drivers.append("Momentum 20d +")
    if d1_4h_congruent:   drivers.append("D1+4H kongruent")
    return GroupScore(score=score, drivers=drivers)


# ─── FAMILIE 2: POSITIONING (COT) ────────────────────────────────────────

def compute_positioning(cot_bias_aligns: bool,
                        cot_pct: Optional[float],
                        cot_momentum_aligns: bool) -> GroupScore:
    """Composite COT-score.

    cot_bias_aligns:    bias (LONG/SHORT) = signal-retning
    cot_pct:            netto posisjonering i %, absolutt verdi
                        25%+ = full styrke (cap 1.0)
    cot_momentum_aligns: Δ i posisjonering peker samme vei som retning
    """
    bias_score = 1.0 if cot_bias_aligns else 0.0
    strength   = min(abs(cot_pct or 0) / 25.0, 1.0)
    momentum   = 1.0 if cot_momentum_aligns else 0.0
    score = (bias_score + strength + momentum) / 3.0

    drivers = []
    if cot_bias_aligns:
        drivers.append(f"COT bias align ({(cot_pct or 0):+.1f}%)")
    if strength >= 0.6:
        drivers.append(f"COT sterk ({abs(cot_pct or 0):.0f}% net)")
    if cot_momentum_aligns:
        drivers.append("COT momentum +")
    return GroupScore(score=score, drivers=drivers)


# ─── FAMILIE 3: MACRO ────────────────────────────────────────────────────

def compute_macro(asset_class: str,
                  direction: str,
                  dxy_chg5d: Optional[float] = None,
                  vix_regime: str = "normal",
                  real_yield_10y: Optional[float] = None,
                  real_yield_chg: Optional[float] = None,
                  term_spread: Optional[float] = None,
                  fear_greed: Optional[int] = None,
                  fund_instrument_score: Optional[float] = None) -> GroupScore:
    """Macro-composite. Asset-class-spesifikk tolkning av felles makrodata."""
    components: list[tuple[float, str]] = []   # (bidrag 0-1, driver-tekst)

    is_bull = direction in ("buy", "bull", "long")
    is_bear = direction in ("sell", "bear", "short")

    # DXY (gjelder alle unntatt USD-par som har det i fundamentals)
    if dxy_chg5d is not None and asset_class not in ("fx",):
        # Svekket DXY = bull for metaller/commodity/indekser
        if asset_class in ("metals", "softs", "grains", "energy"):
            if dxy_chg5d < -1.0 and is_bull:
                components.append((min(abs(dxy_chg5d) / 3.0, 1.0), f"DXY svak {dxy_chg5d:+.1f}%"))
            elif dxy_chg5d > 1.0 and is_bear:
                components.append((min(abs(dxy_chg5d) / 3.0, 1.0), f"DXY sterk {dxy_chg5d:+.1f}%"))

    # VIX-regime
    if vix_regime == "elevated":
        # Risk-off favoriserer gold og treasuries, skader risky
        if asset_class == "metals" and is_bull:
            components.append((0.5, "VIX elevert — flight to safety"))
        elif asset_class == "indices" and is_bear:
            components.append((0.5, "VIX elevert — risk-off"))
    elif vix_regime == "extreme":
        if asset_class == "metals" and is_bull:
            components.append((0.8, "VIX ekstrem — crisis bid"))
        elif asset_class == "indices" and is_bear:
            components.append((0.8, "VIX ekstrem — panikk-salg"))

    # Real yields — direkte driver for gull/sølv
    if asset_class == "metals" and real_yield_10y is not None:
        # Negative real yields = bull gold
        if real_yield_10y < 0 and is_bull:
            components.append((min(abs(real_yield_10y) / 2.0, 1.0),
                              f"Real yields negative ({real_yield_10y:.2f}%)"))
        elif real_yield_10y > 1.5 and is_bear:
            components.append((min((real_yield_10y - 1.5) / 2.0, 1.0),
                              f"Real yields høye ({real_yield_10y:.2f}%)"))
        # Bevegelse siste uke
        if real_yield_chg is not None:
            if real_yield_chg < -0.1 and is_bull:
                components.append((min(abs(real_yield_chg) * 3, 1.0),
                                  f"Real yields faller ({real_yield_chg:+.2f}%)"))

    # Yield curve (for FX carry og indekser)
    if term_spread is not None:
        if asset_class == "indices":
            # Inversjon = resesjonrisk = bear indekser
            if term_spread < -0.3 and is_bear:
                components.append((min(abs(term_spread) / 1.0, 1.0),
                                  f"Yield curve invertert ({term_spread:+.2f}%)"))
        if asset_class == "fx" and fund_instrument_score is None:
            # Uten per-par-data, bruk term-spread som generisk USD-styrke-proxy
            if term_spread > 0.5 and is_bull:
                components.append((0.3, f"USD carry positiv ({term_spread:+.2f}%)"))

    # Fase 1: fund_instrument_score er FLYTTET til FUNDAMENTAL (per-asset-USD-
    # bias er asset-spesifikk, ikke global makro). Se compute_fundamental_fx og
    # compute_fundamental_indices. Ved å holde den utenfor MACRO unngår vi at
    # én FRED-score lyser opp to "uavhengige" familier (C1-prinsipp).

    # Fear & Greed som risk-regime-proxy (Fase 1: utvidet til metaller og indekser,
    # ikke bare crypto). Logikk: extreme fear → flight-to-safety (bull gold/silver,
    # bear risky assets); extreme greed → risk-on (bear gold, bull indices).
    if fear_greed is not None:
        if asset_class == "crypto":
            if fear_greed <= 25 and is_bull:   # extreme fear = contrarian bull
                components.append((0.5, f"F&G {fear_greed} — extreme fear"))
            elif fear_greed >= 75 and is_bear:
                components.append((0.5, f"F&G {fear_greed} — extreme greed"))
        elif asset_class == "metals":
            # Safe-haven bid: extreme fear → bull metaller
            if fear_greed <= 25 and is_bull:
                components.append((0.5, f"F&G {fear_greed} — safe-haven bid"))
            elif fear_greed >= 80 and is_bear:
                components.append((0.3, f"F&G {fear_greed} — risk-on (bear metals)"))
        elif asset_class == "indices":
            # Greed-ekstremer er contrarian bear, fear-ekstremer bull (oversold bounce)
            if fear_greed >= 75 and is_bear:
                components.append((0.4, f"F&G {fear_greed} — extreme greed"))
            elif fear_greed <= 20 and is_bull:
                components.append((0.4, f"F&G {fear_greed} — capitulation bull"))

    # Beregn composite: snitt av bidrag, med minimum 0.3 per bidrag
    filtered = [(s, d) for s, d in components if s >= 0.3]
    if not filtered:
        return GroupScore(score=0.0, drivers=[])
    total = min(sum(s for s, _ in filtered) / max(len(filtered), 1), 1.0)
    drivers = [d for _, d in filtered]
    return GroupScore(score=total, drivers=drivers[:3])


# ─── FAMILIE 4: FUNDAMENTAL (asset-class-specific) ───────────────────────

def compute_fundamental_metals(direction: str,
                               comex_stress: Optional[float],
                               registered_oz_change: Optional[float],
                               gold_silver_ratio_z: Optional[float] = None,
                               asset: str = "Gold") -> GroupScore:
    """Metals (Gold/Silver): COMEX inventory + GS-ratio."""
    components = []
    is_bull = direction in ("buy", "bull", "long")
    is_bear = direction in ("sell", "bear", "short")

    if comex_stress is not None:
        # stress_index: 0=ingen, 100=ekstremt. Høy stress = tight supply = bull
        if comex_stress >= 40 and is_bull:
            components.append((min(comex_stress / 80.0, 1.0),
                              f"COMEX stress {comex_stress:.0f}"))
        elif comex_stress < 20 and is_bear:
            components.append((0.3, f"COMEX stress lav {comex_stress:.0f}"))

    if registered_oz_change is not None:
        # Fall i registered oz = supply som forsvinner = bull
        if registered_oz_change < -30000 and is_bull:
            components.append((min(abs(registered_oz_change) / 100000, 1.0),
                              f"Registered oz {registered_oz_change:+,.0f}"))
        elif registered_oz_change > 30000 and is_bear:
            components.append((min(registered_oz_change / 100000, 1.0),
                              f"Registered oz +{registered_oz_change:,.0f}"))

    if gold_silver_ratio_z is not None:
        # Z-score >2 = gold svært dyr vs silver → bull silver, bear gold
        if abs(gold_silver_ratio_z) > 2:
            if asset == "Silver" and gold_silver_ratio_z > 2 and is_bull:
                components.append((0.6, f"GS-ratio Z {gold_silver_ratio_z:+.1f}"))
            elif asset == "Gold" and gold_silver_ratio_z > 2 and is_bear:
                components.append((0.4, f"GS-ratio Z {gold_silver_ratio_z:+.1f}"))

    filtered = [(s, d) for s, d in components if s >= 0.3]
    if not filtered:
        return GroupScore(score=0.0, drivers=[])
    total = min(sum(s for s, _ in filtered) / max(len(filtered), 1), 1.0)
    return GroupScore(score=total, drivers=[d for _, d in filtered][:3])


def compute_fundamental_energy(direction: str,
                               shipping_risk: Optional[str],
                               oilgas_signal: Optional[str],
                               oil_supply_disruption: bool = False,
                               brent_wti_spread: Optional[float] = None) -> GroupScore:
    """Energy (Oil): shipping + oilgas + backwardation."""
    components = []
    is_bull = direction in ("buy", "bull", "long")
    is_bear = direction in ("sell", "bear", "short")

    # Supply disruption = tight supply = bull olje
    if oil_supply_disruption and is_bull:
        components.append((0.8, "Supply disruption aktiv"))
    elif oil_supply_disruption and is_bear:
        # Supply disruption blokkerer short — gir negativ bidrag, men
        # vi returnerer bare 0 her og lar signal-pipeline-gate blokkere
        pass

    if shipping_risk == "HIGH" and is_bull:
        components.append((0.6, "Shipping risiko HIGH"))
    elif shipping_risk == "LOW" and is_bear:
        components.append((0.4, "Shipping risiko lav"))

    if oilgas_signal and "bull" in oilgas_signal.lower() and is_bull:
        components.append((0.5, f"Oilgas: {oilgas_signal}"))
    elif oilgas_signal and "bear" in oilgas_signal.lower() and is_bear:
        components.append((0.5, f"Oilgas: {oilgas_signal}"))

    # Backwardation (Brent>WTI+2) = tight current supply = bull
    if brent_wti_spread is not None and brent_wti_spread > 3 and is_bull:
        components.append((min(brent_wti_spread / 6.0, 1.0),
                          f"Brent-WTI spread {brent_wti_spread:+.1f}"))

    filtered = [(s, d) for s, d in components if s >= 0.3]
    if not filtered:
        return GroupScore(score=0.0, drivers=[])
    total = min(sum(s for s, _ in filtered) / max(len(filtered), 1), 1.0)
    return GroupScore(score=total, drivers=[d for _, d in filtered][:3])


def compute_fundamental_grains(direction: str,
                               conab_mom: Optional[float],
                               conab_yoy: Optional[float],
                               usda_blackout: bool,
                               yield_score: Optional[float],
                               enso_risk: int = 0) -> GroupScore:
    """Grains (Corn/Wheat/Soy/Cotton): Conab + USDA + yield + ENSO."""
    components = []
    is_bull = direction in ("buy", "bull", "long", "BUY")
    is_bear = direction in ("sell", "bear", "short", "SELL")

    # Conab m/m shock (strong driver)
    if conab_mom is not None and abs(conab_mom) >= 1.0:
        if conab_mom < 0 and is_bull:
            components.append((min(abs(conab_mom) / 4.0, 1.0),
                              f"Conab m/m {conab_mom:+.1f}% (bull)"))
        elif conab_mom > 0 and is_bear:
            components.append((min(conab_mom / 4.0, 1.0),
                              f"Conab m/m +{conab_mom:.1f}% (bear)"))

    # Conab YoY struktur (weaker, men alltid tilgjengelig)
    if conab_yoy is not None:
        if conab_yoy <= -10 and is_bull:
            components.append((0.5, f"Conab YoY {conab_yoy:+.1f}% (struktur)"))
        elif conab_yoy >= 10 and is_bear:
            components.append((0.5, f"Conab YoY +{conab_yoy:.1f}% (struktur)"))

    # Yield-score fra Open-Meteo
    if yield_score is not None:
        if yield_score < 40 and is_bull:
            components.append((0.8, f"Yield kritisk ({yield_score})"))
        elif yield_score < 55 and is_bull:
            components.append((0.5, f"Yield svak ({yield_score})"))
        elif yield_score > 85 and is_bear:
            components.append((0.5, f"Yield høy ({yield_score})"))

    # ENSO-risk
    if enso_risk >= 2 and is_bull:
        components.append((0.4, "ENSO-risiko høy"))

    filtered = [(s, d) for s, d in components if s >= 0.3]
    if not filtered:
        return GroupScore(score=0.0, drivers=[])
    total = min(sum(s for s, _ in filtered) / max(len(filtered), 1), 1.0)
    return GroupScore(score=total, drivers=[d for _, d in filtered][:3])


def compute_fundamental_softs(direction: str,
                              unica_mix_sugar: Optional[float] = None,
                              unica_mix_qoq: Optional[float] = None,
                              unica_crush_yoy: Optional[float] = None,
                              conab_coffee_mom: Optional[float] = None,
                              conab_coffee_yoy: Optional[float] = None,
                              brl_chg5d: Optional[float] = None,
                              harmattan_severity: float = 0.0,
                              frost_severity: float = 0.0,
                              yield_score: Optional[float] = None,
                              asset: str = "Sugar") -> GroupScore:
    """Softs (Sugar/Coffee/Cocoa/Cotton): UNICA + Conab café + BRL + harmattan."""
    components = []
    is_bull = direction in ("buy", "bull", "long", "BUY")
    is_bear = direction in ("sell", "bear", "short", "SELL")

    # UNICA sugar-mix (kun for Sugar)
    if asset == "Sugar":
        if (unica_mix_sugar is not None and unica_mix_qoq is not None):
            if unica_mix_sugar > 50 and unica_mix_qoq >= 1.0 and is_bear:
                components.append((0.6, f"UNICA mix {unica_mix_sugar:.1f}% ({unica_mix_qoq:+.1f}pp)"))
            elif unica_mix_sugar < 48 and unica_mix_qoq <= -1.0 and is_bull:
                components.append((0.6, f"UNICA mix {unica_mix_sugar:.1f}% ({unica_mix_qoq:+.1f}pp)"))
        if unica_crush_yoy is not None:
            if unica_crush_yoy <= -5 and is_bull:
                components.append((0.5, f"UNICA crush {unica_crush_yoy:+.1f}% YoY"))
            elif unica_crush_yoy >= 5 and is_bear:
                components.append((0.5, f"UNICA crush +{unica_crush_yoy:.1f}% YoY"))

    # Conab café (kun for Coffee)
    if asset == "Coffee":
        if conab_coffee_mom is not None and abs(conab_coffee_mom) >= 1.0:
            if conab_coffee_mom < 0 and is_bull:
                components.append((min(abs(conab_coffee_mom) / 4.0, 1.0),
                                  f"Conab café m/m {conab_coffee_mom:+.1f}%"))
            elif conab_coffee_mom > 0 and is_bear:
                components.append((min(conab_coffee_mom / 4.0, 1.0),
                                  f"Conab café m/m +{conab_coffee_mom:.1f}%"))
        if conab_coffee_yoy is not None:
            if conab_coffee_yoy <= -10 and is_bull:
                components.append((0.5, f"Conab café YoY {conab_coffee_yoy:+.1f}%"))
            elif conab_coffee_yoy >= 10 and is_bear:
                components.append((0.5, f"Conab café YoY +{conab_coffee_yoy:.1f}%"))

    # Harmattan (Cocoa, jan-feb)
    if asset == "Cocoa" and harmattan_severity >= 1.5 and is_bull:
        components.append((min(harmattan_severity / 2.0, 1.0), "Harmattan severity"))

    # Frost (Coffee/Sugar, jun-aug)
    if asset in ("Coffee", "Sugar") and frost_severity >= 1.5 and is_bull:
        components.append((0.7, "Frost-risiko Brasil-vinter"))

    # BRL-motvind (kun for BUY, Brasil-avhengige crops)
    if asset in ("Coffee", "Sugar") and brl_chg5d is not None and is_bull:
        if brl_chg5d > 3:
            # Svak BRL = eksportdumping = motvind for long
            components.append((-min(brl_chg5d / 10.0, 0.5), f"BRL svak +{brl_chg5d:.1f}%"))

    # Yield-score fra Open-Meteo
    if yield_score is not None:
        if yield_score < 40 and is_bull:
            components.append((0.6, f"Yield kritisk ({yield_score})"))
        elif yield_score < 55 and is_bull:
            components.append((0.4, f"Yield svak ({yield_score})"))

    # Filter negative bidrag — disse reduserer, men returneres ikke som "aktive"
    positive = [(s, d) for s, d in components if s >= 0.3]
    negative_sum = sum(s for s, _ in components if s < 0)
    if not positive:
        return GroupScore(score=0.0, drivers=[])
    total = sum(s for s, _ in positive) / max(len(positive), 1)
    total = max(min(total + negative_sum, 1.0), 0.0)
    drivers = [d for _, d in positive][:3]
    if negative_sum < 0:
        drivers.append(f"Motvind {negative_sum:+.1f}")
    return GroupScore(score=total, drivers=drivers)


def compute_fundamental_fx(direction: str,
                           fund_instrument_score: Optional[float],
                           rate_spread_diff: Optional[float] = None) -> GroupScore:
    """FX: FRED instrument-score + rente-spread mot motpart-valuta."""
    components = []
    is_bull = direction in ("buy", "bull", "long")
    is_bear = direction in ("sell", "bear", "short")

    if fund_instrument_score is not None:
        if fund_instrument_score > 0.3 and is_bull:
            components.append((min(abs(fund_instrument_score) / 2.0, 1.0),
                              f"FRED fund {fund_instrument_score:+.2f}"))
        elif fund_instrument_score < -0.3 and is_bear:
            components.append((min(abs(fund_instrument_score) / 2.0, 1.0),
                              f"FRED fund {fund_instrument_score:+.2f}"))

    if rate_spread_diff is not None:
        if rate_spread_diff > 0.5 and is_bull:
            components.append((min(rate_spread_diff / 2.0, 1.0),
                              f"Rente-spread +{rate_spread_diff:.2f}"))
        elif rate_spread_diff < -0.5 and is_bear:
            components.append((min(abs(rate_spread_diff) / 2.0, 1.0),
                              f"Rente-spread {rate_spread_diff:.2f}"))

    filtered = [(s, d) for s, d in components if s >= 0.3]
    if not filtered:
        return GroupScore(score=0.0, drivers=[])
    total = min(sum(s for s, _ in filtered) / max(len(filtered), 1), 1.0)
    return GroupScore(score=total, drivers=[d for _, d in filtered][:2])


def compute_fundamental_indices(direction: str,
                                fund_instrument_score: Optional[float]) -> GroupScore:
    """Indices (SPX/NAS): per-instrument FRED-score som asset-spesifikk
    USD/makro-eksponering. VIX og term_spread er flyttet til MACRO (Fase 1).
    """
    components = []
    is_bull = direction in ("buy", "bull", "long")
    is_bear = direction in ("sell", "bear", "short")

    if fund_instrument_score is not None:
        if fund_instrument_score > 0.3 and is_bull:
            components.append((min(fund_instrument_score / 2.0, 1.0),
                              f"FRED fund {fund_instrument_score:+.2f}"))
        elif fund_instrument_score < -0.3 and is_bear:
            components.append((min(abs(fund_instrument_score) / 2.0, 1.0),
                              f"FRED fund {fund_instrument_score:+.2f}"))

    filtered = [(s, d) for s, d in components if s >= 0.3]
    if not filtered:
        return GroupScore(score=0.0, drivers=[])
    total = min(sum(s for s, _ in filtered) / max(len(filtered), 1), 1.0)
    return GroupScore(score=total, drivers=[d for _, d in filtered][:2])


# ─── FAMILIE 5: RISK/EVENT ───────────────────────────────────────────────

def compute_risk_event(geo_active: bool = False,
                       upcoming_event_hours: Optional[float] = None,
                       event_name: str = "",
                       usda_blackout: bool = False,
                       vix_regime: str = "normal") -> GroupScore:
    """Risk/event — positiv familie-score kun når det er konkrete positive
    event-setups ELLER når risk er nær kritisk. Ingen events = 0.0 (ikke
    aktiv) slik at "ingen nyheter" ikke falskelig teller som driver.

    Denne familien anses som modifier; i score_asset brukes den som vanlig
    additiv familie (med horisont-vekt). Høy-risk-gate håndteres separat
    via _risk_gate_grade() som kapper grade ved kritisk event-nærhet.
    """
    risk_factors = 0
    drivers = []

    if usda_blackout:
        risk_factors += 3
        drivers.append("USDA blackout")
    if geo_active:
        risk_factors += 2
        drivers.append("Geo aktiv")
    if upcoming_event_hours is not None:
        if upcoming_event_hours < 2:
            risk_factors += 3
            drivers.append(f"{event_name or 'Event'} om {upcoming_event_hours:.0f}t")
        elif upcoming_event_hours < 24:
            risk_factors += 1
            drivers.append(f"{event_name or 'Event'} om {upcoming_event_hours:.0f}t")
    if vix_regime == "extreme":
        risk_factors += 2
        drivers.append("VIX ekstrem")
    elif vix_regime == "elevated":
        risk_factors += 1
        drivers.append("VIX elevert")

    if risk_factors == 0:
        # Ingen risikofaktorer → familien er ikke aktiv (teller ikke i
        # active_driver_groups). Ingen drivere returneres.
        return GroupScore(score=0.0, drivers=[])

    # Høyere risk → høyere score i denne familien (ikke som "bra trade" men
    # som "risk-regime-oppmerksomhet"). Score kan tolkes som confidence i
    # event-analysen; den telles likevel i driver-diversitet.
    # Samtidig: gate i _risk_gate_grade() forhindrer A/A+ ved kritisk risk.
    score = min(risk_factors * 0.25, 1.0)
    return GroupScore(score=score, drivers=drivers[:3])


def _risk_gate_grade(current_grade: str, risk_factors: int) -> str:
    """Kap grade ved kritisk event-nærhet.

    risk_factors >= 5 (USDA blackout + nær event + VIX ekstrem) → maks B
    risk_factors >= 3 (f.eks. USDA blackout alene, eller geo+elevert)  → maks A (ikke A+)
    """
    order = ["C", "B", "A", "A+"]
    cap   = None
    if risk_factors >= 5:
        cap = "B"
    elif risk_factors >= 3:
        cap = "A"
    if cap and order.index(current_grade) > order.index(cap):
        return cap
    return current_grade


# ─── FAMILIE 6: STRUCTURE ────────────────────────────────────────────────

def compute_structure(nearest_level_weight: int = 0,
                      smc_confirms: bool = False,
                      fibo_zone_hit: bool = False) -> GroupScore:
    """HTF-nivå, SMC-bekreftelse, fibo-zone."""
    components = []
    # Nivå-vekt 0-5 → score 0-1
    if nearest_level_weight >= 3:
        components.append((min(nearest_level_weight / 5.0, 1.0),
                          f"HTF-nivå w{nearest_level_weight}"))
    if smc_confirms:
        components.append((0.7, "SMC-bekreftelse"))
    if fibo_zone_hit:
        components.append((0.5, "Fibo-zone"))

    if not components:
        return GroupScore(score=0.0, drivers=[])
    total = min(sum(s for s, _ in components) / max(len(components), 1), 1.0)
    return GroupScore(score=total, drivers=[d for _, d in components][:2])


# ─── AGGREGATE: score_asset + grade + horizon ────────────────────────────

def grade(total_score: float, active_driver_groups: int) -> str:
    for g, min_sc, min_fam in GRADE_RULES:
        if total_score >= min_sc and active_driver_groups >= min_fam:
            return g
    return "C"


def determine_horizon(driver_groups: dict[str, float],
                      total_unweighted: float,
                      active_driver_groups: int) -> str:
    """Velg høyeste horisont hvor både score- og familie-krav er møtt.
    Bruker nåværende active_driver_groups som gate; inkluderer asset-class-
    spesifikk sjekk for MAKRO (må ha fundamental/macro-bidrag)."""
    for horizon, min_score, min_active, extra_check in HORIZON_GATES:
        if total_unweighted < min_score:
            continue
        if active_driver_groups < min_active:
            continue
        if extra_check is not None and not extra_check(driver_groups):
            continue
        return horizon
    return "WATCHLIST"


def score_asset(
    direction: str,
    horizon_hint: Optional[str] = None,
    # Trend-input
    sma200_aligned: bool = False,
    momentum_aligned: bool = False,
    d1_4h_congruent: bool = False,
    # Positioning
    cot_bias_aligns: bool = False,
    cot_pct: Optional[float] = None,
    cot_momentum_aligns: bool = False,
    # Struktur
    nearest_level_weight: int = 0,
    smc_confirms: bool = False,
    fibo_zone_hit: bool = False,
    # Macro / fundamental (kwargs passerer til asset-specific funksjoner)
    **context,
) -> GroupResult:
    """Hovedkoordinator — kaller alle 6 familier og aggregerer.

    context inkluderer typisk:
      asset: str
      asset_class: str  ("fx", "metals", "energy", "indices", "grains", "softs", "crypto")
      dxy_chg5d, vix_regime, real_yield_10y, real_yield_chg, term_spread,
      fear_greed, fund_instrument_score
      comex_stress, registered_oz_change, gold_silver_ratio_z
      shipping_risk, oilgas_signal, oil_supply_disruption, brent_wti_spread
      conab_mom, conab_yoy, usda_blackout, yield_score, enso_risk
      unica_mix_sugar, unica_mix_qoq, unica_crush_yoy,
      conab_coffee_mom, conab_coffee_yoy, brl_chg5d, harmattan_severity, frost_severity
      rate_spread_diff
      geo_active, upcoming_event_hours, event_name
    """
    asset_class = context.get("asset_class", "fx")
    asset       = context.get("asset", "")

    # Familie 1 — TREND
    trend = compute_trend(sma200_aligned, momentum_aligned, d1_4h_congruent)

    # Familie 2 — POSITIONING
    positioning = compute_positioning(cot_bias_aligns, cot_pct, cot_momentum_aligns)

    # Familie 3 — MACRO
    macro = compute_macro(
        asset_class=asset_class,
        direction=direction,
        dxy_chg5d=context.get("dxy_chg5d"),
        vix_regime=context.get("vix_regime", "normal"),
        real_yield_10y=context.get("real_yield_10y"),
        real_yield_chg=context.get("real_yield_chg"),
        term_spread=context.get("term_spread"),
        fear_greed=context.get("fear_greed"),
        fund_instrument_score=context.get("fund_instrument_score"),
    )

    # Familie 4 — FUNDAMENTAL (asset-class-dispatch)
    if asset_class == "metals":
        fundamental = compute_fundamental_metals(
            direction=direction,
            comex_stress=context.get("comex_stress"),
            registered_oz_change=context.get("registered_oz_change"),
            gold_silver_ratio_z=context.get("gold_silver_ratio_z"),
            asset=asset,
        )
    elif asset_class == "energy":
        fundamental = compute_fundamental_energy(
            direction=direction,
            shipping_risk=context.get("shipping_risk"),
            oilgas_signal=context.get("oilgas_signal"),
            oil_supply_disruption=context.get("oil_supply_disruption", False),
            brent_wti_spread=context.get("brent_wti_spread"),
        )
    elif asset_class == "grains":
        fundamental = compute_fundamental_grains(
            direction=direction,
            conab_mom=context.get("conab_mom"),
            conab_yoy=context.get("conab_yoy"),
            usda_blackout=context.get("usda_blackout", False),
            yield_score=context.get("yield_score"),
            enso_risk=context.get("enso_risk", 0),
        )
    elif asset_class == "softs":
        fundamental = compute_fundamental_softs(
            direction=direction,
            unica_mix_sugar=context.get("unica_mix_sugar"),
            unica_mix_qoq=context.get("unica_mix_qoq"),
            unica_crush_yoy=context.get("unica_crush_yoy"),
            conab_coffee_mom=context.get("conab_coffee_mom"),
            conab_coffee_yoy=context.get("conab_coffee_yoy"),
            brl_chg5d=context.get("brl_chg5d"),
            harmattan_severity=context.get("harmattan_severity", 0.0),
            frost_severity=context.get("frost_severity", 0.0),
            yield_score=context.get("yield_score"),
            asset=asset,
        )
    elif asset_class == "indices":
        fundamental = compute_fundamental_indices(
            direction=direction,
            fund_instrument_score=context.get("fund_instrument_score"),
        )
    elif asset_class == "fx":
        fundamental = compute_fundamental_fx(
            direction=direction,
            fund_instrument_score=context.get("fund_instrument_score"),
            rate_spread_diff=context.get("rate_spread_diff"),
        )
    else:
        # crypto eller annet → tom fundamental
        fundamental = GroupScore(score=0.0, drivers=[])

    # Familie 5 — RISK/EVENT
    risk = compute_risk_event(
        geo_active=context.get("geo_active", False),
        upcoming_event_hours=context.get("upcoming_event_hours"),
        event_name=context.get("event_name", ""),
        usda_blackout=context.get("usda_blackout", False),
        vix_regime=context.get("vix_regime", "normal"),
    )

    # Familie 6 — STRUCTURE
    structure = compute_structure(
        nearest_level_weight=nearest_level_weight,
        smc_confirms=smc_confirms,
        fibo_zone_hit=fibo_zone_hit,
    )

    driver_groups = {
        "trend":       trend,
        "positioning": positioning,
        "macro":       macro,
        "fundamental": fundamental,
        "risk":        risk,
        "structure":   structure,
    }

    # risk-familien er et GATE, ikke et additivt bidrag. Den telles IKKE i
    # active_driver_groups og IKKE i total_score-summeringen. Den brukes kun til
    # å kappe grade ved kritisk event-nærhet (se _risk_gate_grade nedenfor).
    NON_SCORING = {"risk"}

    score_raw_map = {k: v.score for k, v in driver_groups.items()
                     if k not in NON_SCORING}
    active_count = sum(1 for s in score_raw_map.values() if s >= GROUP_ACTIVE_THRESHOLD)
    total_unweighted = sum(score_raw_map.values())

    horizon = horizon_hint or determine_horizon(
        score_raw_map, total_unweighted, active_count)

    # Anvend horizon-vekter på de SCORING-familiene
    weights = HORIZON_GROUP_WEIGHTS.get(horizon, HORIZON_GROUP_WEIGHTS["SWING"])
    weighted_total = 0.0
    for k, grp in driver_groups.items():
        grp.weight = weights.get(k, 1.0)
        if k not in NON_SCORING:
            weighted_total += grp.score * grp.weight

    base_grade = grade(weighted_total, active_count)

    # Risk-gate: kapp grade hvis event-risiko er kritisk
    # Risk-score 0.0 = ingen events, 1.0 = mange event-faktorer
    risk_factors = int(round(risk.score * 4)) if risk.score > 0 else 0
    final_grade = _risk_gate_grade(base_grade, risk_factors)

    return GroupResult(
        driver_groups=driver_groups,
        total_score=weighted_total,
        active_driver_groups=active_count,
        grade=final_grade,
        horizon=horizon if final_grade != "C" else "WATCHLIST",
        direction=direction if direction in ("bull", "bear") else
                  ("bull" if direction in ("buy", "long") else
                   "bear" if direction in ("sell", "short") else "?"),
    )
