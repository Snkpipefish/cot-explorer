# Detaljert: Hvordan Trading Setups Genereres

*Oppdatert for schema 2.0 — 6-familie driver matrix med disaggregated COT-analytics.*

## Oversikt

Trading-setups genereres i to parallelle pipelines — teknisk og agri-fundamental:

```
TEKNISK PIPELINE (full update — hver 4. time via update.sh):
fetch_all.py        → data/macro/latest.json     (nivåer, driver-familie-scores, setups)
                    → data/cot_analytics/latest.json  (MM-percentile, divergens-z, OI-regime)
push_signals.py     → data/signals.json          (horisont-filtrert, for bot)
                    → POST /push-alert            (til signal_server.py)
signal_server.py    → latest_signals.json         (oversatt til bot-format)
trading_bot.py      → cTrader (Skilling)          (entry, confirmation, exit)

INTRATIME RE-SCORING (hver time via update_prices.sh):
fetch_prices.py     → patcher priser i data/macro/latest.json (bevarer trading_levels)
fetch_oilgas.py     → oppdaterer data/oilgas/latest.json
rescore.py          → re-evaluerer ALLE 11 instrumenter via driver_matrix med
                       ferske priser + oppdatert dir_color + DXY/VIX-regime
                       (gjenbruker COT/fundamentals/SMC fra forrige fetch_all)

AGRI-FUNDAMENTAL PIPELINE:
fetch_agri.py           → data/agri/latest.json       (vær, COT, yield, ENSO)
push_agri_signals.py    → data/agri_signals.json      (filtrert, grade A/B)
push_signals.py         → POST /push-alert             (felles endpoint;
                                                       agri merges inn med
                                                       source: "agri_fundamental")
signal_server.py        → latest_signals.json          (filtreres bot-side på source)
trading_bot.py          → cTrader (Skilling)           (rekalibrert med live ATR)
```

---

## Steg 1: Datainnhenting (fetch_all.py)

### 1.1 Prisdata

For hvert av 14 instrumenter (10 tradeable + 4 kun-pris) hentes prisdata fra 3 kilder (prioritert):

| Prioritet | Kilde | Tidsrom | Intervall |
|-----------|-------|---------|-----------|
| 1 | Trading-bot (live_prices.json) | Sanntid | Hvert 58. min |
| 2 | Yahoo Finance | 1 år | D1, 1H, 15min |
| 3 | Stooq | 1 år | D1 |

**Instrumenter:**

| Instrument | Klasse | Sesjon | Primær COT-kilde |
|-----------|--------|--------|-----|
| EURUSD | A | London 08:00–12:00 | TFF (Leveraged Funds) |
| USDJPY | A | London 08:00–12:00 | TFF (Leveraged Funds) |
| GBPUSD | A | London 08:00–12:00 | TFF (Leveraged Funds) |
| AUDUSD | A | London 08:00–12:00 | TFF (Leveraged Funds) |
| Gold | B | London Fix / NY Fix | Disaggregated (Managed Money) |
| Silver | B | London Fix / NY Fix | Disaggregated (Managed Money) |
| Brent | B | London Fix / NY Fix | ICE + CFTC Disaggregated (OI-vektet) |
| WTI | B | London Fix / NY Fix | Disaggregated (Managed Money) |
| SPX | C | NY Open 14:30–17:00 | Disaggregated (Managed Money) |
| NAS100 | C | NY Open 14:30–17:00 | Disaggregated (Managed Money) |
| VIX | C | NY (kun posisjonsstørrelse) | — |
| DXY | A | London (kun display) | Disaggregated (Managed Money) |

### 1.2 Beregninger per instrument

Fra prisdata beregnes:

- **ATR(14)** på D1, 4H og 15min — volatilitetsmål
- **EMA(9)** på D1, 4H og 15min — trend per tidsramme
- **SMA(200)** på D1 — langsiktig trend
- **PDH/PDL/PDC** — Previous Day High/Low/Close
- **PWH/PWL** — Previous Week High/Low
- **Endring** 1d, 5d, 20d i prosent
- **Gold/Silver-ratio z-score (20d)** — beregnes én gang fra `bot_history.json`, brukes i metals FUNDAMENTAL

### 1.3 VIX Term-struktur

Hentes FØR instrument-loopen (VIX9D, VIX, VIX3M fra Yahoo Finance):

| Tilstand | Betingelse | Betydning |
|----------|-----------|-----------|
| Contango | VIX9D < VIX < VIX3M | Normalt — markedet rolig |
| Backwardation | VIX9D > VIX > VIX3M | Frykt — kortsiktig stress |
| Flat | Spreaden < 5% | Nøytralt |

VIX-regime mappes til `extreme`/`elevated`/`normal` og er en input til MACRO-familien (ikke lenger eget scoring-kriterie).

### 1.4 Nivåer (Support & Resistance)

Nivåer identifiseres fra tre tidsrammer og tagges med vekt:

#### Intraday (15min) — `find_intraday_levels()`
- Finner swing highs/lows over siste 3 candles
- Vekt: 1 (svak)

#### Swing (D1) — `find_swing_levels()`
- Finner swing highs/lows over siste 5 dager
- Vekt: 2-3 avhengig av antall berøringer

#### Nøkkelnivåer — automatisk tagget
| Nivå | Vekt | Kilde |
|------|------|-------|
| PWH/PWL | 4-5 | Previous Week High/Low |
| PDH/PDL | 3-4 | Previous Day High/Low |
| PDC | 2-3 | Previous Day Close |
| SMA200 | 3 | 200-dagers glidende snitt |
| Runde tall | 1-2 | Psykologiske nivåer |

#### SMC (Smart Money Concepts) — 15min, 1H, 4H
- **Order Blocks**: Siste bearish candle før bullish impuls (og omvendt)
- **BOS** (Break of Structure): Brudd over/under swing high/low
- **Supply/Demand soner**: Basert på order blocks med zone_top/zone_bottom

Alle nivåer merges via `merge_tagged_levels()`:
- Fjerner duplikater nærmere enn 0.3×ATR(15m)
- Høyere vekt vinner ved overlapp
- Sorteres etter avstand fra nåpris
- Maks 6 nivåer per side (support/resistance)

### 1.5 COT-data (to lag)

**Aggregert COT** — bestemmer `cot_bias`, `cot_pct` og `cot_momentum` per asset:
- Net posisjon for Managed Money / Hedge Funds (spekulanter) / OI
- Ukentlig endring (`change_spec_net`)
- Bias: LONG hvis net_pct > +4 %, SHORT hvis < -4 %, ellers NØYTRAL
- Kilde-kombinasjoner:

| Instrument | Primær | Fallback | Kombinering |
|---|---|---|---|
| Brent | ICE Futures Europe | CFTC | OI-vektet snitt |
| Hvete / Raps / Mais | Euronext (MiFID II) | CFTC | OI-vektet snitt |
| FX | TFF (Hedge Funds) | — | — |
| Alle andre | CFTC Disaggregated | — | — |

**Disaggregated analytics** — beregnes én gang per ny COT-release (fredag kveld) av `cot_analytics.py` og cachres i `data/cot_analytics/latest.json`:

| Felt | Beregning | Brukes til |
|---|---|---|
| `mm_net_pctile_52w` | Rank-percentile av MM-net-posisjon over rullende 52 uker | Contrarian-signal (bunn/topp-ekstremer) |
| `mm_comm_divergence_z` | Robust z-score av (MM_net − Commercial_net) via median/MAD | Topp/bunn-divergens-signal |
| `change_oi_current` + `oi_change_4w_avg` | 4-ukers OI-trend | OI-regime-klassifisering |
| `index_investor_bias` | Supplemental indeksfond net / OI > 5 % | Strukturelt agri-bias |
| `history_weeks` / `data_quality` | Antall ukentlige datapunkter i lookback | Graceful degradation (<26 uker → `insufficient_history`) |

Historikk hentes fra `data/history/<report_type>/YYYY.json` (16 års arkiv: 2010-2025) + `data/<report_type>/<YYYY-MM-DD>.json` (ukentlig). Dedupliseres på (date, market).

### 1.6 Makro-indikatorer

- **VIX** — markedsvolatilitet (brukes i MACRO-familien som regime-proxy)
- **DXY chg5d** — dollarindeks 5-dagers endring (MACRO, ikke for FX)
- **Real yields (DFII10)** — 10-års TIPS yield + 5d-endring (MACRO, især metaller)
- **Yield curve (term_spread = DGS10 − DGS2)** — resesjonsignal (MACRO, især indekser)
- **Fear & Greed** fra CNN — risk-regime-proxy (MACRO for crypto/metaller/indekser)
- **HYG/TIP/Copper/EEM** — display-indikatorer på dashboard (brukes ikke direkte i driver matrix)

Staleness-metadata: hver rate har `_fallback=True` hvis arvet fra cache (FRED 5xx) og `_age_hours` / `_fresh`-felt per per-input TTL (48h fresh for market rates).

### 1.7 Nyhetssentiment

Fra Google News RSS + BBC RSS:
- Siste 30 overskrifter scores mot risk_on/risk_off nøkkelordlister
- Net score: (risk_on_count - risk_off_count) / total → -1.0 til +1.0
- Brukes til `geo_active`-flagg (aktiveres av krigs-/sanksjonsord eller oljespike) som mater RISK/EVENT-familien

### 1.8 FRED Fundamentals

Fra `data/fundamentals/latest.json`:
- Aggregert USD-bias-score per instrument (±1.5 skala) basert på 14 FRED-indikatorer (GDP, CPI, PPI, PCE, ISM PMI, NFP, Unemployment, Initial Claims, JOLTS, ADP, Fed Funds, Retail Sales, Consumer Confidence)
- Cache-fallback: ved FRED 5xx arves verdier fra forrige run med `_fallback=True`
- Brukes **kun** i FUNDAMENTAL-familien for FX og indekser (ikke dobbelttelt i MACRO — C1-fiks fra Fase 1)

### 1.9 Asset-spesifikke fundamentals

Per asset-klasse leses egne kilder (via `driver_group_mapping.build_context_for_asset()`):

| Asset-klasse | Kilder |
|---|---|
| Metaller | `comex_stress`, `registered_oz_change`, `gold_silver_ratio_z` |
| Energi | `shipping_risk`, `oilgas_signal`, `brent_wti_spread`, `oil_supply_disruption` |
| Grains | `conab_mom`, `conab_yoy`, `yield_score`, `enso_risk`, `usda_blackout` |
| Softs | `unica_mix_sugar`, `unica_mix_qoq`, `unica_crush_yoy`, `conab_coffee_*`, `brl_chg5d`, `harmattan_severity`, `frost_severity` |
| Crypto | `fear_greed` (risk-regime) |

### 1.10 Kalender

Fra `data/calendar/latest.json`:
- Neste økonomiske hendelser med impact-nivå
- USDA Crop Progress (mandager) + Export Sales (torsdager) for agri-blackout
- Mater RISK/EVENT-familien via `upcoming_event_hours`

---

## Steg 2: Retningsbestemmelse og 6-familie Driver Matrix Scoring (fetch_all.py)

### 2.1 Retning (dir_color) — beholdt fra tidligere

En vektet `dir_score` bestemmer bull/bear-retning per instrument **før** driver-matrisen scorer styrken:

| Signal | Vekt | Betingelse |
|--------|------|------------|
| SMA200 | ±1.5 | Over = bull, under = bear |
| chg5d | ±0.5 / ±1.0 | Kun hvis \|chg5\| > 0.1% / 0.3% |
| chg20d | ±0.5 / ±1.0 | Kun hvis \|chg20\| > 0.3% / 1.0% |
| COT bias | ±1.0 | LONG / SHORT |
| COT momentum | ±0.5 | Ukentlig change_spec_net |
| DXY-bias | ±0.5 | XXXUSD: invers DXY. USDXXX: følger DXY |
| Momentum-divergens | -0.5 | Straff når chg5 og chg20 peker motsatt (>0.3%) |

**Hysterese:** dir_score > 0.5 → bull, < -0.5 → bear, mellom → SMA200 avgjør.

**Olje-override:** Hvis shipping/oilgas rapporterer `oil_supply_disruption`, tvinges `dir_color=bull` for Brent/WTI (supply-squeeze).

### 2.2 6-familie Driver Matrix (driver_matrix.score_asset)

Direction er bestemt. `driver_matrix` evaluerer nå 6 uavhengige driver-familier for å score **styrken** av setup-et. **C1-prinsippet**: grade krever confluens på tvers av **uavhengige** datakildefamilier — ikke flere signaler fra samme kilde.

| # | Familie | Datakilder | Composite-score |
|---|---|---|---|
| 1 | **TREND** | SMA200-align, 20d-momentum, D1+4H EMA9-kongruens | (n_active / 3), 0-1 |
| 2 | **POSITIONING** | COT bias-align, styrke, momentum + MM-percentile 52w, MM-Comm divergens-z, OI-regime, Index Investor | Snitt av ikke-null sub-signaler, 0-1 |
| 3 | **MACRO** | DXY chg5d, VIX-regime, real yields (DFII10), Fear & Greed, term_spread | Snitt av kvalifiserte bidrag (≥0.3), 0-1 |
| 4 | **FUNDAMENTAL** | Asset-spesifikk (se 1.9). For FX/indekser: FRED instrument-score | Snitt av kvalifiserte bidrag, 0-1 |
| 5 | **RISK/EVENT** | USDA blackout, geo-aktiv, nær event, VIX ekstrem | `min(risk_factors × 0.25, 1.0)` — **NON_SCORING**, kun grade-gate |
| 6 | **STRUCTURE** | Nærmeste HTF-nivå-vekt, SMC-bekreftelse, fibo-zone | Snitt, 0-1 |

### 2.3 POSITIONING sub-signaler — alpha-rik utvidelse

`compute_positioning_v2` har opptil 7 sub-signaler (per-asset). Hver gir 0-1 bidrag (OI-warning kan gi −0.3). Graceful degradation: ved `<26 uker` historikk eller manglende disaggregated-data faller den tilbake til legacy-logikk.

| Sub-signal | Aktivering |
|---|---|
| `cot_bias_aligns` | LONG/SHORT bias ↔ retning → 1.0 |
| `cot_momentum_aligns` | `change_spec_net` peker samme vei som net → 1.0 |
| `cot_pct / 25` cap (legacy) eller `mm_net_pctile_52w` (ny) | Se under |
| MM-percentile 52w | bull + pctile ≤ 10 → 1.0 (contrarian-bull). bull + pctile ≤ 20 → 0.5. bear + pctile ≥ 90 → 1.0. bear + pctile ≥ 80 → 0.5 |
| MM-Commercial divergens-z | bear + z ≥ 1.5 → 1.0 (topp-signal). bull + z ≤ -1.5 → 1.0 (bunn-signal). ±1.0 til 1.5 → 0.5 |
| OI-regime | confirmation (stigende OI i retning) → +0.5. warning (stigende OI mot retning) → **−0.3** |
| Index Investor-bias (supplemental, kun agri) | structural_long + bull → +0.3. structural_short + bear → +0.3 |

Aggregering: snitt av alle ikke-null bidrag, clampet til [0, 1.0].

### 2.4 MACRO sub-signaler

| Asset-class | DXY chg5d | VIX-regime | Real yields | Fear & Greed | Term spread |
|---|---|---|---|---|---|
| FX | — | — | — | — | (kun carry-fallback hvis FRED mangler) |
| Metaller | ±0.33-1.0 (svak DXY = bull) | elevated/extreme → safe-haven | <0 = bull, chg<-0.1 = akselerasjon | fear≤25 bull | — |
| Energi | ±0.33-1.0 | — | — | — | — |
| Grains/Softs | ±0.33-1.0 | — | — | — | — |
| Indekser | — | elevated/extreme → bear | — | greed≥75 bear, fear≤20 bull | <-0.3 + bear → bidrag |
| Crypto | — | — | — | fear≤25 bull, greed≥75 bear | — |

### 2.5 FUNDAMENTAL — asset-spesifikk

| Asset-class | Innhold |
|---|---|
| Metaller | COMEX stress (≥40 bull), registered oz-endring, GS-ratio-z > 2 (sølv bull, gull bear) |
| Energi | Supply-disruption (0.8 bull), shipping HIGH (0.6 bull), oilgas-signal, brent_wti_spread > 3 = backwardation |
| Grains | Conab m/m (abs ≥ 1 % + motsatt retning av pris), Conab yoy, yield_score (<40 kritisk), ENSO-risk |
| Softs | UNICA mix + qoq, UNICA crush yoy, Conab café, BRL chg5d (svak BRL = motvind), harmattan, frost, yield_score |
| FX | FRED `fund_instrument_score` (USD-bias ±1.5), rate_spread_diff (hvis tilgjengelig) |
| Indekser | FRED `fund_instrument_score` |
| Crypto | (tom — utvides senere) |

### 2.6 STRUCTURE

| Sub-signal | Bidrag |
|---|---|
| Nearest HTF-nivå weight ≥ 3 | `weight / 5` (cap 1.0) |
| SMC-bekreftelse (BOS + struktur-align) | 0.7 |
| Fibo-zone hit | 0.5 |

### 2.7 Horisont-bestemmelse

`driver_matrix.determine_horizon()` velger høyeste horisont hvor både score- og familie-krav er møtt:

| Horisont | Min unweighted score | Min aktive familier | Tilleggskrav |
|----------|---------------------|--------------------|--------------|
| MAKRO | ≥ 3.5 | 4 | `fundamental + macro ≥ 0.7` |
| SWING | ≥ 2.5 | 3 | — |
| SCALP | ≥ 1.5 | 2 | London/NY-sesjon |
| WATCHLIST | under dette | — | — |

**SCALP utenfor optimal sesjon → WATCHLIST** automatisk.

### 2.8 Horisont-vekter

Etter horisont er valgt, multipliseres hver familie med horisont-spesifikk vekt:

| Familie | SCALP | SWING | MAKRO |
|---|---|---|---|
| TREND | 1.2 | 1.0 | 0.8 |
| POSITIONING | 0.5 | 1.0 | 1.3 |
| MACRO | 0.7 | 1.0 | 1.3 |
| FUNDAMENTAL | 0.5 | 1.0 | 1.3 |
| STRUCTURE | 1.3 | 1.0 | 0.5 |

`weighted_total = sum(family_score × horizon_weight)`. Max per horisont: SCALP=4.2, SWING=5.0, MAKRO=5.2.

### 2.9 Grade — prosent-basert (Fase 4)

Grade-terskler uttrykt som prosent av max-score per horisont, slik at A i SCALP = A i SWING = A i MAKRO i **relativ edge**:

| Grade | Min % av max | Min aktive familier |
|---|---|---|
| A+ | 75 % | 4 |
| A | 55 % | 3 |
| B | 35 % | 2 |
| C | under dette | — |

Konkret terskel (weighted_total): A+ ≥ 3.15 (SCALP) / 3.75 (SWING) / 3.9 (MAKRO).

### 2.10 Grade-caps: risk-gate + staleness-gate

Etter initial grade-beregning kappes grade hvis:

| Trigger | Grade-cap |
|---|---|
| `risk_factors ≥ 5` (USDA blackout + nær event + VIX ekstrem) | B |
| `risk_factors ≥ 3` (f.eks. USDA blackout alene, eller geo+elevert) | A (ikke A+) |
| `data_quality = "degraded"` (én kritisk input `_fallback=True`) | A (ikke A+) |
| `data_quality = "stale"` (COT > 20d, eller kritisk input > 7d cache-stale) | B |

Strengeste cap vinner. `quality_notes` logger konkrete grunner (f.eks. "DGS2 arvet 18h fra cache", "COT 12d gammel").

### 2.11 Signal-stabilitet

`signal_stability.json` lagrer forrige kjørings verdier per instrument. Ved neste kjøring:
- **Retning flippet** (bull → bear) → nedgradér 1 nivå (MAKRO→SWING→SCALP→WATCHLIST)
- **Horisont flippet** (SWING → SCALP → SWING) → nedgradér 1 nivå

Dette forhindrer at ustabile signaler pushes til boten.

---

## Steg 3: Setup-generering (fetch_all.py → make_setup_l2l)

Level-to-level setups — **strukturbasert**, ikke mekanisk ATR.

### Entry-valg — horizon-tilpasset

| Horisont | Strategi | Maks avstand |
|----------|----------|-------------|
| SCALP | Nærmeste nivå (tight entry) | 1.0×ATR(D1) |
| SWING | Sterkeste weight innen 3×ATR(D1) | 3.0×ATR(D1) |
| MAKRO | Sterkeste weight innen 5×ATR(D1) | 5.0×ATR(D1) |

SWING/MAKRO prioriterer sterke HTF-nivåer (PWH/PWL w5, PDH/PDL w4) over nære svake nivåer (15m w1).

**LONG**: Sterkeste støttenivå innen horizon-avstand under nåpris
**SHORT**: Sterkeste motstandsnivå innen horizon-avstand over nåpris

### Stop Loss — strukturbasert

SL plasseres **ved strukturen**, ikke mekanisk ATR fra nåpris:

**Hierarki:**
1. Entry sin SMC sone-bunn/topp → `SL = zone_bottom - buffer` / `zone_top + buffer`
2. Nærmeste reelle nivå under/over entry → `SL = nivå - buffer` / `nivå + buffer`
3. Fallback: `entry ± 2×buffer`

**Buffer per kategori:**

| Kategori | Buffer |
|----------|--------|
| Valuta | 0.15×ATR(D1) |
| Råvarer | 0.25×ATR(D1) |
| Aksjer | 0.20×ATR(D1) |

### Take Profit — horisont-cap + min R:R

| Horisont | T1-cap | T2-cap | Min R:R |
|---|---|---|---|
| SCALP | 2.0×ATR(D1) | 3.0×ATR(D1) | 1.0 |
| SWING | 5.0×ATR(D1) | 8.0×ATR(D1) | 1.3 |
| MAKRO | Ingen cap | Ingen cap | 1.5 |

T1 velges som nærmeste motstandsnivå (LONG) med høyest HTF-vekt som gir R:R ≥ min_rr. T2 er neste nivå etter T1 med R:R ≥ 1.0, innen T2-cap.

### R:R-beregning

```
risk = |entry - SL|
R:R_T1 = |T1 - entry| / risk
R:R_T2 = |T2 - entry| / risk
```

---

## Steg 4: Filtrering og Horizon Config (push_signals.py)

### Horisont-basert filtrering

1. **Horisont-terskel** — weighted_total ≥ terskel for sin horisont
2. **Klar retning** — `dir_color` er "bull" eller "bear"
3. **Aktiv setup** — `setup_long` (bull) eller `setup_short` (bear) eksisterer
4. **Tradeable** — DXY ekskludert
5. **Ikke WATCHLIST** — pushes aldri

### Push-terskler (0-6 skala fra driver matrix)

| Horisont | Minimum weighted score |
|----------|-----------------------|
| SCALP | 1.5 |
| SWING | 2.5 |
| MAKRO | 3.5 |
| WATCHLIST | Aldri |

(Legacy 9-kriterie-systemet brukte 3.0/4.5/5.5 på 0-9 skala — **fullstendig fjernet** i schema 2.0. `rescore.py` (kjøres hver time) ble migrert til driver_matrix i commit 644c669, og `scoring_config.py` har ikke lenger legacy-funksjoner (commit 349a2b7). Driver-matrix er eneste scoring-motor.)

### Signal aging (FJERNET i schema 2.2)

Tidligere ble signaler avvist hvis pris hadde vandret > N×ATR fra entry.
**Dette er fjernet** i schema 2.2 fordi filteret hadde tre uavhengige bugs:

1. `abs(live - entry)` droppet også gunstige bevegelser (BUY hvor pris falt)
2. Agri brukte `atr_est` (H1-skala) mens tekniske brukte `atr_daily` (D1-skala)
   med samme terskel — agri ble droppet 7× mer aggressivt
3. Agri-instrumenter mangler i `macro["prices"]`, så fallback til `current`
   gjorde filteret til en no-op (samme verdi sammenlignet mot seg selv)

Ansvar for signal-utløp er nå fullt på bot-siden via `horizon_config.exit_timeout_*`-feltene
(SCALP `exit_timeout_full_candles=16`, SWING `exit_timeout_full_hours=120`,
MAKRO `exit_timeout_full_hours=360`). Hvis pris aldri når entry → boten dropper signalet selv.

### Sortering og limiter

Sorteres etter horisont-prioritet (MAKRO > SWING > SCALP), deretter score. Maks 5 signaler per kjøring (`PUSH_MAX_SIGNALS`).

Korrelasjonsgrenser (VIX-regime-avhengig):

| Regime | VIX | Precious | Indices | Energy | USD pairs | Total maks |
|--------|-----|----------|---------|--------|-----------|------------|
| Normal | < 25 | 2 | 1 | 1 | 2 | 6 |
| Risk-off | 25–35 | 1 | 1 | 1 | 1 | 3 |
| Crisis | > 35 | 1 | 1 | 1 | 1 | 2 |

### Horizon Config

Hvert signal inkluderer `horizon_config` med parametre for boten:

**SCALP:**
```json
{
  "confirmation_tf": "5min",
  "confirmation_max_candles": 6,
  "entry_zone_margin": 0.0015,
  "exit_t1_close_pct": 0.50,
  "exit_trail_tf": "5min",
  "exit_trail_atr_mult": {"fx": 2.0, "gold": 2.5, "oil": 2.5, "index": 2.0},
  "exit_ema_tf": "5min",
  "exit_ema_period": 9,
  "exit_timeout_partial_candles": 8,
  "exit_timeout_full_candles": 16,
  "sizing_base_risk_usd": 20
}
```

**SWING:**
```json
{
  "confirmation_tf": "15min",
  "confirmation_max_candles": 8,
  "entry_zone_margin": 0.0025,
  "exit_t1_close_pct": 0.33,
  "exit_t2_close_pct": 0.33,
  "exit_trail_tf": "1H",
  "exit_trail_atr_mult": {"fx": 8.0, "gold": 10.0, "silver": 10.0, "oil": 9.0, "index": 8.0},
  "exit_ema_tf": "1H",
  "exit_timeout_partial_candles": 96,
  "exit_timeout_full_hours": 120,
  "exit_be_timeout_hours": 48,
  "sizing_base_risk_usd": 40
}
```

**MAKRO:**
```json
{
  "confirmation_tf": "1H",
  "confirmation_max_candles": 6,
  "entry_zone_margin": 0.0040,
  "exit_t1_close_pct": 0.25,
  "exit_t2_close_pct": 0.25,
  "exit_trail_tf": "D1",
  "exit_trail_atr_mult": {"fx": 12.0, "gold": 15.0, "silver": 15.0, "oil": 13.0, "index": 12.0},
  "exit_ema_tf": "D1",
  "exit_timeout_partial_candles": 288,
  "exit_timeout_full_hours": 360,
  "exit_timeout_days": 15,
  "exit_score_deterioration": 6.0,
  "sizing_base_risk_usd": 60
}
```

### Flask-payload til `/push-alert` (schema 2.0)

```json
{
  "schema_version": "2.2",
  "generated": "2026-04-17 16:00 UTC",
  "global_state": {
    "geo_active": true,
    "vix_regime": "elevated",
    "correlation_regime": "normal"
  },
  "signals": [
    {
      "key": "eurusd", "name": "EUR/USD",
      "horizon": "SWING", "direction": "bull", "grade": "A",
      "score": 2.77, "max_score": 5.0, "score_pct": 55,
      "setup": {"entry": ..., "sl": ..., "t1": ..., "t2": ..., "rr_t1": 1.47},
      "cot": {"bias": "LONG", "pct": 12.4},
      "driver_groups": {
        "trend":       {"score": 1.0, "weight": 1.0, "drivers": ["SMA200-align", "Momentum 20d +"]},
        "positioning": {"score": 0.75, "weight": 1.0, "drivers": ["COT bias align (+12.4%)", "MM percentile 18 (lav)"]},
        "macro":       {"score": 0.45, "weight": 1.0, "drivers": ["DXY svak -1.5%"]},
        "fundamental": {"score": 0.60, "weight": 1.0, "drivers": ["FRED fund +0.8"]},
        "risk":        {"score": 0.00, "weight": 1.0, "drivers": []},
        "structure":   {"score": 0.40, "weight": 1.0, "drivers": ["HTF-nivå w3"]}
      },
      "active_driver_groups": 5,
      "data_quality": "fresh", "quality_notes": [],
      "correlation_group": "usd_pairs",
      "atr_d1": 94.44,
      "horizon_config": {...},
      "created_at": "2026-04-17T16:00:00+00:00"
    },
    {
      "key": "Cotton", "name": "Bomull",
      "horizon": "MAKRO", "direction": "bull", "grade": "A",
      "score": 9.0, "max_score": 18,
      "setup": {"entry": 77.15, "sl": 75.83, "t1": 78.85, "t2": 80.0, "rr_t1": 1.29},
      "source": "agri_fundamental",
      "correlation_group": "cotton",
      "data_quality": "fresh", "quality_notes": [],
      "yield_score": 34, "weather_outlook": "tørt",
      "drivers": ["Yield kritisk (34)", "Værstress USA Cotton Belt", "COT spekulanter snur long"]
    }
  ]
}
```

Signal-server validerer at alle `driver_groups.*.score` ∈ [0, 1]. Tekniske bruker `max_score` 4.2/5.0/5.2 (per horisont fra driver_matrix), agri bruker `max_score = 18` (sum av maks-poeng for alle 7 komponenter). Boten tar kun tradet — den sammenligner ikke score på tvers, så ulike skalaer er kun synlige i UI (`score_pct = score / max_score`).

### Olje supply-disruption blokkering

Leser shipping og oilgas-data (Hormuz, Suez, Midtøsten-konflikt). Når noen har `risk = HIGH`:

- **Olje SHORT-signaler blokkeres helt** — supply-squeeze = bullish for oljepris
- `dir_color` er allerede tvunget til `bull` i fetch_all.py
- `oil_supply_disruption = true` synlig i trading_levels for Brent/WTI
- Deaktiveres automatisk når risk synker (dynamisk, ikke hardkodet)

---

## Steg 4b: Agri-signaler (push_agri_signals.py)

### Datakilder

Fra `data/agri/latest.json` (generert av `fetch_agri.py`):
- **10 avlinger**: Mais, Hvete, Soyabønner, Canola, Bomull, Sukker, Kaffe, Kakao, Palmeolje, Ris
- **14 regioner** med Open-Meteo værvarsling + historisk sesongvær
- **ENSO-fase** (El Niño/La Niña) fra NOAA CPC
- **Vekstsyklus**: Såing → Vekst → Blomstring → Modning → Høsting
- **Yield-kvalitetsestimat**: estimate_yield_quality(wx_score, enso_adj)

Pluss:
- `data/conab/latest.json` — Brasiliansk avlingsestimat m/m + YoY per asset
- `data/unica/latest.json` — Brasiliansk sukker-mix + crush yoy

### Scoring per avling (separat fra driver matrix)

Agri bruker egen additiv scoring (ikke 6-familie matrix):

| Komponent | Poeng | Hva det sjekker |
|-----------|-------|-----------------|
| `outlook total_score` | 0–5 | Abs(vær + COT + yield) |
| Yield stress | 0–3 | **BUY**: lav yield_score (<40 kritisk = 3, <55 svak = 2, <70 middels = 1). **SELL**: høy yield_score (>85 rekord = 3, >70 sterk = 2, >60 god = 1). Symmetrisk siden Apr-2026. |
| Weather urgency | 0–2 | Akutt tørke/flom (wx_score ≥ 3) |
| ENSO risk | 0–2 | El Niño/La Niña-effekt (enso_adj) |
| Conab shock | 0–2 | m/m ≥ 1.0 % i retning av signal |
| UNICA mix | 0–2 | sukker-mix + crush-yoy for Sugar |
| Cross-confirm | 0–2 | Multi-kilde validering (inkl. analog-match fra `agri_analog.py`) |
| **Total** | **0–18** | Sum av alle komponenter (`AGRI_MAX_SCORE`) |

### Filtrering

- **Minimum score: 5.0** — under dette er signalet for svakt
- **Kun in-season avlinger** — utenfor sesong er data upålitelig
- **Kun tradeable instrumenter** — palmeolje og ris filtreres bort
- **Grade C droppes** — kun A (score ≥ 7) og B (score ≥ 5) sendes til bot
- **USDA blackout**: ±3h fra Crop Progress / Export Sales blokkerer signalet

### Retning og horisont

| Grade | Score | Horisont |
|-------|-------|----------|
| A | ≥ 7 | MAKRO (eller SWING) |
| B | ≥ 5 | SWING |
| C | < 5 | Sendes ikke |

Retning bestemmes av outlook-signal:
- BULLISH / STERKT BULLISH → BUY
- BEARISH / STERKT BEARISH → SELL
- NØYTRAL → ingen signal

### Entry/SL/T1-beregning (ATR%-basert)

```
ATR = pris × atr_pct / 100

BUY:  entry = pris - 0.3×ATR (pullback)
      SL    = entry - 1.5×ATR
      T1    = entry + 2.0×ATR
      T2    = entry + 3.0×ATR

SELL: entry = pris + 0.3×ATR (rally)
      SL    = entry + 1.5×ATR
      T1    = entry - 2.0×ATR
      T2    = entry - 3.0×ATR
```

ATR-estimater per instrument:
| Instrument | ATR% | Basis |
|-----------|------|-------|
| Corn | 1.5% | ~$6-7 på $450 |
| Wheat | 1.8% | ~$10 på $580 |
| Soybeans | 1.4% | ~$15 på $1100 |
| Cotton | 2.0% | Høy vol |
| Sugar | 2.2% | Veldig volatil |
| Coffee | 2.5% | Svært volatil |
| Cocoa | 2.8% | Ekstremt volatil |

**Boten rekalibrerer** entry/SL/T1 med live ATR(14) hvis estimat avviker > 30 %.

### Priskilde-prioritet

1. `price.value` fra agri/latest.json (USDA/historisk)
2. `bot_history.json` — bot-priser (mest oppdaterte)
3. `macro/latest.json` prices — fallback

---

## Steg 5: Signal-server translate (signal_server.py)

Flask-serveren oversetter signaler til bot-format.

### Tekniske signaler (POST /push-alert → GET /signals)

#### Entry Zone
```
margin = horizon_config.entry_zone_margin  (0.15%/0.25%/0.40%)
entry_zone = [entry - margin × entry, entry + margin × entry]
```
For olje med geo-warning: margin utvides til 0.4 %.

#### Character (for bot størrelse)

| Grade | Character |
|-------|-----------|
| A+, A | A+ |
| B | B |
| C | C (pushes ikke) |

### Agri-signaler (POST /push-agri-alert → GET /agri-signals)

Konverterer agri-format til standard bot-format:
- Entry/SL/T1/T2 direkte (ikke i setup-dict)
- `expiry_candles`: 48 (4 timer, vs 8 for tekniske)
- `confirmation_candle_limit`: 12 (1 time for bekreftelse)
- `source`: "agri_fundamental"
- `valid_until`: 24 timer fra generering

### Schema 2.0 validering

Signal-server validerer `driver_groups`-dict per signal:
- Alle `driver_groups.{trend,positioning,macro,fundamental,risk,structure}.score` ∈ [0, 1]
- Schema-versjoner < 2.0 gir WARN (ikke block)

### Session-tider

| Instrument | Session | CET |
|-----------|---------|-----|
| EURUSD, GBPUSD | London | 08:00-17:00 |
| USDJPY, AUDUSD | Tokyo/London | 02:00-17:00 |
| Gold | London/NY | 08:00-21:00 |
| Silver | NY | 14:00-21:00 |
| Brent, WTI | NY | 14:00-21:00 |
| SPX500, US100 | NY | 15:30-22:00 |
| Corn, Wheat, Soybean | CME Agri | 15:00-20:00 |
| Coffee, Cocoa, Sugar, Cotton | ICE Agri | 15:30-19:00 |

---

## Steg 6: Bot-eksekusjon (trading_bot.py)

### Livssyklus

```
WATCHLIST → AWAITING_CONFIRMATION → IN_TRADE → CLOSED
```

Boten henter to signal-kilder hvert 60. sekund:
- `GET /signals` — tekniske signaler
- `GET /agri-signals` — agri-fundamentale signaler (offset 10s)

### Confirmation per horisont

| Horisont | TF | Maks candles | Poeng krevd |
|----------|----|-------------|-------------|
| SCALP | 5min | 6 (30 min) | ≥ 2/3 |
| SWING | 15min | 8 (2 timer) | ≥ 2/3 |
| MAKRO | 1H | 6 (6 timer) | ≥ 2/3 |

3-punkt bekreftelse:

| Test | Betingelse | Poeng |
|------|-----------|-------|
| **Body size** | Body ≥ 30% av ATR(tf) | 1 |
| **Wick rejection** | Pris avviser fra entry zone | 1 |
| **EMA9 gradient** | EMA9 heller i riktig retning | 1 |

Trenger ≥ 2/3 poeng (3/3 hvis motstridende USD-retning).

### Position Sizing

VIX-basert grunnstørrelse:

| VIX | Posisjonsstørrelse |
|-----|--------------------|
| < 20 | Full |
| 20–30 | Halv |
| > 30 | Kvart |

Horizon-basert risiko (USD):

| Horisont | Base risk USD |
|----------|--------------|
| SCALP | $20 |
| SWING | $40 |
| MAKRO | $60 |

For agri-instrumenter: halvparten av normal størrelse. Maks samtidige agri-posisjoner: 2.

### Correlation Groups

| Gruppe | Instrumenter | Maks samtidige |
|--------|-------------|---------------|
| usd_pairs | EURUSD, GBPUSD, USDJPY, AUDUSD | 2 |
| precious_metals | Gold, Silver | 2 |
| energy | Brent, WTI | 1 |
| us_indices | SPX, NAS100 | 1 |

### Exit-regler per horisont

**SCALP:**

| Regel | Trigger | Handling |
|-------|---------|----------|
| **T1** | Pris ≥ T1 | Lukk 50%, SL → break-even, trail aktivert |
| **Trail** | Trail stop truffet (2.0-2.5×ATR 5min) | Lukk remaining |
| **EMA9** | EMA9(5min) krysser pris (post-T1) | Lukk remaining |
| **8-candle** | 8×5min uten T1 | Lukk 50% |
| **16-candle** | 16×5min total | Lukk alt remaining |
| **Geo-spike** | > 2.0×ATR mot posisjon | Nødlukk alt |

**SWING:**

| Regel | Trigger | Handling |
|-------|---------|----------|
| **T1** | Pris ≥ T1 | Lukk 33%, SL → break-even |
| **T2** | Pris ≥ T2 | Lukk 33%, trail aktivert |
| **Trail** | Trail stop truffet (8-10× 15m ATR ≈ 3× 1H ATR) | Lukk remaining |
| **Give-back** | Peak ≥85-90% av T1, nå ≤30-45% | Lukk alt (pre-T1) |
| **Partial timeout** | 96 candles (8 timer) | Lukk 50% eller trail |
| **Full timeout** | 120 timer (5 dager) | Lukk alt remaining |
| **BE timeout** | 48 timer uten T1 | Flytt SL → break-even |
| **Event** | Høy-risiko event innen 2 timer | Lukk alt |
| **Geo-spike** | > 3.0× 15m ATR mot posisjon | Nødlukk alt |

**MAKRO:**

| Regel | Trigger | Handling |
|-------|---------|----------|
| **T1** | Pris ≥ T1 | Lukk 25%, SL → break-even |
| **T2** | Pris ≥ T2 | Lukk 25%, trail aktivert |
| **Trail** | Trail stop truffet (12-15× 15m ATR ≈ 2.5× D1 ATR) | Lukk remaining |
| **Give-back** | Peak ≥85-90% av T1, nå ≤30-45% | Lukk alt (pre-T1) |
| **Partial timeout** | 288 candles (24 timer) | Lukk 50% eller trail |
| **Full timeout** | 360 timer (15 dager) | Lukk alt remaining |
| **Score-forverring** | Score faller under 6.0 | Lukk alt |
| **Geo-spike** | > 3.0× 15m ATR mot posisjon | Nødlukk alt |

### Trail ATR-multiplikator (kompensert for 15m ATR)

Boten bruker 15m ATR for trailing uavhengig av horizon_config.exit_trail_tf. Multiplikatorene er justert opp:

| Gruppe | SCALP (×15m) | SWING (≈×1H) | MAKRO (≈×D1) |
|--------|-------------|-------------|-------------|
| FX | 2.0 | 8.0 | 12.0 |
| Gold | 2.5 | 10.0 | 15.0 |
| Silver | 2.5 | 10.0 | 15.0 |
| Oil | 2.5 | 9.0 | 13.0 |
| Index | 2.0 | 8.0 | 12.0 |

### Give-back parametere per gruppe

| Gruppe | Peak threshold | Exit threshold |
|--------|---------------|----------------|
| FX | 0.85 | 0.30 |
| Gold | 0.90 | 0.45 |
| Silver | 0.88 | 0.42 |
| Oil | 0.90 | 0.45 |
| Indices | 0.85 | 0.35 |
| Agri | 0.85-0.88 | 0.35 |

### Geo R:R minimum

Under geo-events: min R:R = 1.5 (senket fra 2.0 — oppblåst ATR gir bredere SL).

### Agri-spesifikke regler

- **Session-filter**: Trades avvises utenfor likvide timer (spread for vid)
- **Maks 2 samtidige agri-posisjoner**
- **Strengere spread-grense**: 1.5×normal_spread (vs 3.0× for standard)
- **ATR-rekalibrering**: Hvis estimert ATR avviker > 30 % fra live ATR(14), justeres entry/SL/T1

### Reconcile ved restart

Når boten restarter, tar den over eksisterende posisjoner via cTrader API:
- `t1_price = 0.0` (ukjent — EMA9/8-candle tar over)
- `t1_price_reached = True` (forhindrer falsk "T1 nådd" når t1_price=0.0)
- `t1_hit = True` (hopp over T1 halvlukk-logikk)

### PnL-beregning

```
pip_size = {5 digits: 0.0001, 3 digits: 0.01, 2 digits: 0.01, 1 digit: 0.1}
pips = price_diff / pip_size
volume_std = cTrader_volume / 100    (Skilling centi-enheter)
pnl_usd = price_diff × volume_std   (÷ close_price for USD-base pairs)
pnl_usd -= spread_cost + commission  (fra cTrader deal-events)
```

---

## Dataflyt-diagram

```
       Yahoo/Stooq/Finnhub/FRED               Open-Meteo/NOAA/CFTC
                 │                                    │
           fetch_all.py                          fetch_agri.py
                 │                                    │
    ┌────────────┼────────────┐                 ┌─────┴─────┐
    │            │            │                 │           │
 Prisdata   COT (agg +    Makro (DXY,       Vær/ENSO   Agri COT
 ATR/EMA   disaggr.)      VIX, yields,     Yield/Vekst  Euronext
 SMA/SMC   cot_analytics  F&G, FRED)
    │            │            │                 │           │
    └────────────┼────────────┘                 └─────┬─────┘
                 │                                    │
         driver_matrix.score_asset           Agri outlook scoring
         (6 familier + C1 + grade)           (yield+vær+ENSO+COT)
         (data_quality gate)                        │
                 │                                  │
         Setup-generering                 Entry/SL/T1-beregning
         (make_setup_l2l)                 (ATR%-basert)
                 │                                  │
       data/macro/latest.json            data/agri/latest.json
       data/cot_analytics/latest.json           │
                 │                              │
           push_signals.py              push_agri_signals.py
           (horisont-filtrering,        (score ≥ 5, grade A/B,
            pct-grade-terskler,          USDA-blackout-sjekk)
            staleness-gate)                    │
                 │                             │
      ┌──────────┴──────────┐        ┌─────────┴──────────┐
      │                     │        │                    │
data/signals.json    POST /push-alert  agri_signals.json  POST /push-agri-alert
(GitHub Pages)       (signal_server)   (GitHub Pages)     (signal_server)
                          │                                │
                   latest_signals.json          latest_agri_signals.json
                          │                                │
                          └──────────┬─────────────────────┘
                                     │
                                trading_bot.py
                                (cTrader Open API)
                                     │
                            ┌────────┼────────┐
                            │        │        │
                      Entry zone  Confirm   Session
                      detection   (tf)      filter
                            │        │        │
                            └────────┼────────┘
                                     │
                              Position opened
                                     │
                        ┌────────────┼────────────┐
                        │            │            │
                  T1 (25-50%)   Trail/EMA9    Timeout
                  per horisont  per horisont  per horisont
                        │
                  signal_log.json
                  (PnL + result → git push)
```

---

## Viktige prinsipper

### C1 — uavhengig confluens
Grade kan ikke nå A/A+ uten confluens på tvers av **uavhengige** datakildefamilier. Selv om POSITIONING-familien har 7 sub-signaler på maks, må minst 2 andre familier også være aktive for A-grade.

### Graceful degradation
Manglende data kollapser ikke scoringen:
- < 26 ukers COT-historikk → MM-percentile = None → legacy `cot_pct/25`-fallback
- FRED 5xx → arvet cache-verdi med `_fallback=True` → grade cappet til A
- COT > 20 d gammel → `data_quality=stale` → grade cappet til B
- Manglende disaggregated-data → compute_positioning_v2 bruker kun 3 legacy-sub-signaler

### Staleness er synlig
`GroupResult.data_quality` og `quality_notes` logger konkret hvilke inputs som er degraded. Bot leser kun `grade`, men audit-info er synlig i `data/macro/latest.json`.

### Tester
- `tests/test_c1_fix.py` — 20 tester (driver matrix, C1-fiks, data_quality-gate, positioning_v2, B-cap risk-stack-up)
- `tests/test_cot_analytics.py` — 12 tester (percentile, z-score, OI-regime)
- Alle rene funksjoner — testbart uten filsystem

---

## Nåværende aktive signaler

Kjøres 6× daglig via `update.sh` og priser oppdateres hver time via `update_prices.sh`.

For å se aktive signaler:
```bash
cat data/signals.json | python3 -m json.tool
cat data/agri_signals.json | python3 -m json.tool
```

For å se COT-analytics-cache:
```bash
cat data/cot_analytics/latest.json | python3 -m json.tool
```

For å se historikk:
```bash
cat data/signal_log.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
for e in d['entries']:
    sig = e.get('signal', {})
    pnl = e.get('pnl', {})
    print(f\"{e.get('timestamp','')}  {sig.get('instrument',''):12s}  {e.get('exit_reason','open'):20s}  \${pnl.get('pnl_usd','?')}\")
"
```

For å kjøre scoring-tester:
```bash
python3 tests/test_c1_fix.py
python3 tests/test_cot_analytics.py
```
