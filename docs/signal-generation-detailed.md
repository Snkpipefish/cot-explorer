# Detaljert: Hvordan Trading Setups Genereres

## Oversikt

Trading-setups genereres i to parallelle pipelines — teknisk og agri-fundamental:

```
TEKNISK PIPELINE:
fetch_all.py        → data/macro/latest.json     (nivåer, score, setups)
push_signals.py     → data/signals.json          (horisont-filtrert, for bot)
                    → POST /push-alert            (til signal_server.py)
signal_server.py    → latest_signals.json         (oversatt til bot-format)
trading_bot.py      → cTrader (Skilling)          (entry, confirmation, exit)

AGRI-FUNDAMENTAL PIPELINE:
fetch_agri.py           → data/agri/latest.json       (vær, COT, yield, ENSO)
push_agri_signals.py    → data/agri_signals.json      (filtrert, grade A/B)
                        → POST /push-agri-alert        (til signal_server.py)
signal_server.py        → latest_agri_signals.json    (oversatt til bot-format)
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

| Instrument | Klasse | Sesjon | COT |
|-----------|--------|--------|-----|
| EURUSD | A | London 08:00–12:00 | CFTC Euro FX |
| USDJPY | A | London 08:00–12:00 | CFTC Japanese Yen |
| GBPUSD | A | London 08:00–12:00 | CFTC British Pound |
| AUDUSD | A | London 08:00–12:00 | — |
| Gold | B | London Fix / NY Fix | CFTC Gold |
| Silver | B | London Fix / NY Fix | CFTC Silver |
| Brent | B | London Fix / NY Fix | ICE+CFTC (OI-vektet) |
| WTI | B | London Fix / NY Fix | CFTC Crude Oil |
| SPX | C | NY Open 14:30–17:00 | CFTC S&P 500 |
| NAS100 | C | NY Open 14:30–17:00 | CFTC Nasdaq Mini |
| VIX | C | NY (kun posisjonsstørrelse) | — |
| DXY | A | London (kun display) | CFTC USD Index |
| USDCHF | A | London (kun pris) | — |
| USDNOK | A | London (kun pris) | — |

### 1.2 Beregninger per instrument

Fra prisdata beregnes:

- **ATR(14)** på D1, 4H og 15min — volatilitetsmål
- **EMA(9)** på D1, 4H og 15min — trend per tidsramme
- **SMA(200)** på D1 — langsiktig trend
- **PDH/PDL/PDC** — Previous Day High/Low/Close
- **PWH/PWL** — Previous Week High/Low
- **Endring** 1d, 5d, 20d i prosent

### 1.3 VIX Term-struktur

Hentes FØR instrument-loopen (VIX9D, VIX, VIX3M fra Yahoo Finance):

| Tilstand | Betingelse | Betydning |
|----------|-----------|-----------|
| Contango | VIX9D < VIX < VIX3M | Normalt — markedet rolig |
| Backwardation | VIX9D > VIX > VIX3M | Frykt — kortsiktig stress |
| Flat | Spreaden < 5% | Nøytralt |

Brukes som kriterium 13 i scoring, men **ikke gratis poeng**:
- **Risk assets**: contango gir kun poeng hvis VIX < 20 (ekte rolig marked)
- **Safe havens** (Gold, Silver, USDJPY, USDCHF): backwardation = bullish, contango + VIX < 18 = bearish

### 1.4 ADR-utnyttelse

Beregnes per instrument fra siste 26 bars med 15min-data (~6.5 timer):

```
today_range = 15min high - 15min low (siste 26 bars)
adr_utilization = today_range / ATR(D1)
```

ADR < 70% = OK for scalp (fortsatt rom for bevegelse). Manglende 15min-data gir **ikke** poeng (default False).

### 1.5 Nivåer (Support & Resistance)

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
| PDH/PDL | 3 | Previous Day High/Low |
| PDC | 2 | Previous Day Close |
| PWH/PWL | 4 | Previous Week High/Low |
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

### 1.6 COT-data

Fra `data/combined/latest.json` + ukentlige COT-filer:

- **Net posisjon** for Managed Money (spekulanter)
- **Net endring** siste uke
- **Net % av Open Interest**
- **Bias**: LONG hvis net > 0, SHORT hvis net < 0
- **Momentum**: Stigende/Synkende basert på ukesendring
- **Enighet**: Sjekker om TFF og Disaggregated rapporter er enige

**COT momentum** (nytt kriterium 5): Henter `change_spec_net` fra ukentlige COT-rapportfiler (`data/tff/`, `data/disaggregated/`). Positiv endring = bullish momentum, negativ = bearish. Bruker IKKE timeseries-filer (utdaterte).

COT-kilder per instrument:
| Instrument | Primær | Fallback | Kombinering |
|---|---|---|---|
| Brent | ICE Futures Europe | CFTC | OI-vektet snitt |
| Hvete / Raps / Mais | Euronext (MiFID II) | CFTC | OI-vektet snitt |
| Alle andre | CFTC | — | — |

### 1.7 Makro-indikatorer

- **VIX** — markedsvolatilitet
- **DXY** — dollarindeks
- **10Y/3M yield** — rentekurve
- **HYG** — high yield credit spread
- **TIP** — inflasjonsforventninger

### 1.8 Nyhetssentiment

Hentes fra Google News RSS + BBC RSS:
- Siste 30 overskrifter scores mot risk_on/risk_off nøkkelordlister
- Net score: (risk_on_count - risk_off_count) / total → -1.0 til +1.0
- Label: risk_on hvis ≥ 0.3, risk_off hvis ≤ -0.3, ellers neutral
- **Sterk konsensus krevd** for scoring-poeng: |score| ≥ 0.5
- **Nyhetsmotvind**: |score| ≥ 0.4 og mot retning → -1.0 score-penalty
- Sjekkes for krigs-/sanksjonsord → `geo_active`

### 1.9 Fundamentals

Fra `data/fundamentals/latest.json`:
- Instrument-spesifikk fundamental score (-1 til +1)
- Bias: bullish/bearish/neutral

### 1.10 Kalender

Fra `data/fundamentals/latest.json`:
- Neste 4 timers økonomiske hendelser
- Brukes som "binary risk" filter (kriterium 9)

---

## Steg 2: Retningsbestemmelse og Vektet Scoring (fetch_all.py)

### Sammensatt retningsbestemmelse (dir_color)

En vektet `dir_score` bestemmer bull/bear-retning per instrument:

| Signal | Vekt | Betingelse |
|--------|------|------------|
| SMA200 | ±1.5 | Over = bull, under = bear |
| chg5d | ±0.5 / ±1.0 | Kun hvis \|chg5\| > 0.1% / 0.3% |
| chg20d | ±0.5 / ±1.0 | Kun hvis \|chg20\| > 0.3% / 1.0% |
| COT bias | ±1.0 | LONG / SHORT |
| COT momentum | ±0.5 | Ukentlig change_spec_net |
| DXY-bias | ±0.5 | XXXUSD: invers DXY. USDXXX: følger DXY |
| Momentum-divergens | -0.5 | Straff når chg5 og chg20 peker motsatt (>0.3%) |

**Hysterese:** dir_score > 0.5 → bull, < -0.5 → bear, mellom → SMA200 avgjør. Forhindrer flip ved marginale endringer.

**Maks dir_score:** ±5.5 (alle signaler enige)

### 14 kriterier

Hvert instrument scores med **vektede kriterier** — ulik vekt per horisont:

| # | Kriterie | SCALP | SWING | MAKRO |
|---|---------|-------|-------|-------|
| 1 | **SMA200** — pris > 200d snitt | 1.0 | 1.0 | 1.0 |
| 2 | **Momentum 20d** — chg20 > 0.5% i SMA200-retning (ikke-sirkulært) | 1.0 | 1.0 | 1.0 |
| 3 | **COT bekrefter** — spekulanter i retning | 0 | 1.0 | 1.0 |
| 4 | **COT sterk >10%** — net > 10% av OI | 0 | 0.5 | 1.0 |
| 5 | **COT momentum Δ** — ukentlig endring bekrefter | 0 | 1.0 | 1.0 |
| 6 | **Pris VED nivå** — innenfor 1.5×ATR | 1.5 | 1.5 | 1.5 |
| 7 | **HTF-nivå weight≥3** — D1/ukentlig nærme | 1.0 | 1.0 | 1.0 |
| 8 | **D1+4H kongruent** — begge EMA9 peker likt (ekte 4H, ikke 15m) | 1.0 | 1.0 | 1.0 |
| 9 | **Ingen event-risiko** — ingen NFP/CPI neste 4t | 1.0 | 1.0 | 1.0 |
| 10 | **Nyhetssentiment** — risk-on/off bekrefter (krever \|score\| ≥ 0.5) | 0.5 | 0.5 | 0.5 |
| 11 | **Fundamental FRED** — fundamental bekrefter | 0 | 0.5 | 1.0 |
| 12 | **SMC bekrefter** — BOS + markedsstruktur (begge kreves) | 1.0 | 1.0 | 1.0 |
| 13 | **VIX term-struktur** — contango+VIX<20 (risk) / backwardation (safe haven) | 0 | 0.5 | 1.0 |
| 14 | **ADR-utnyttelse** — < 70% av daglig range (default False) | 1.0 | 0 | 0 |
| | **Maks total** | **9.0** | **11.5** | **13.0** |

### Score-justeringer (etter vekting)

| Justering | Penalty | Når |
|-----------|---------|-----|
| DXY-konflikt | -2.0 (SWING/MAKRO) / -1.0 (SCALP) | USD-par med retning motstridende DXY |
| Nyhetsmotvind | -1.0 | Sterk nyhetssentiment (\|score\| ≥ 0.4) mot retning |
| Signal-flip | Nedgradering 1 horisont-nivå | Retning eller horisont endret siden forrige kjøring |

### Horisont-bestemmelse

Krever **både** rå bool-telling OG minimum vektet score (kvalitetssikring):

| Betingelse | Tilleggskrav | Min vektet score | Horisont |
|-----------|--------------|-----------------|----------|
| ≥ 8 treff + COT + weight ≥ 4 | Vektet score ≥ 8.0 | 8.0/13.0 | **MAKRO** |
| ≥ 6 treff + weight ≥ 3 | Vektet score ≥ 6.0 | 6.0/11.5 | **SWING** |
| ≥ 4 treff + price_at_level + **i sesjon** | — | — | **SCALP** |
| Alt annet | — | — | **WATCHLIST** |

**SCALP utenfor optimal sesjon → WATCHLIST** automatisk.

Horisonten bestemmer:
1. Hvilke vekter som brukes for scoring
2. Grade-terskler
3. Push-terskler
4. Horizon_config (bekreftelses-TF, exit-regler, sizing)

### Signal-stabilitet

`signal_stability.json` lagrer forrige kjørings verdier per instrument. Ved neste kjøring:
- **Retning flippet** (bull → bear) → nedgradér 1 nivå (MAKRO→SWING→SCALP→WATCHLIST)
- **Horisont flippet** (SWING → SCALP → SWING) → nedgradér 1 nivå
- Score rekalkuleres for ny horisont

Dette forhindrer at ustabile signaler pushes til boten.

### Grade per horisont

| Horisont | A+ | A | B | C |
|----------|----|---|---|---|
| MAKRO | ≥ 11.5 | ≥ 9.5 | ≥ 7.5 | < 7.5 |
| SWING | ≥ 10.0 | ≥ 8.5 | ≥ 6.5 | < 6.5 |
| SCALP | ≥ 8.0 | ≥ 6.5 | ≥ 4.5 | < 4.5 |

---

## Steg 3: Setup-generering (fetch_all.py → make_setup_l2l)

Level-to-level setups — **strukturbasert**, ikke mekanisk ATR.

### Entry-valg

**LONG**: Nærmeste støttenivå under nåpris
- Må være maks 0.3-1.0×ATR(D1) unna (avhengig av vekt)
  - Vekt 1: maks 0.3×ATR
  - Vekt 2: maks 0.7×ATR
  - Vekt ≥ 3: maks 1.0×ATR

**SHORT**: Nærmeste motstandsnivå over nåpris (same logikk)

### Stop Loss — strukturbasert

SL plasseres **ved strukturen**, ikke mekanisk ATR fra nåpris:

**Hvis nivået har SMC demand/supply-sone:**
```
SL = zone_bottom - 0.15×ATR(D1) buffer    (LONG)
SL = zone_top + 0.15×ATR(D1) buffer       (SHORT)
```

**Hvis linjenivå (PDH/PDL/D1/PWH/PWL):**
```
SL = nivå - 0.3×ATR(D1)    (vekt < 4)
SL = nivå - 0.5×ATR(D1)    (vekt ≥ 4, sterkere nivå → bredere SL)
```

### Take Profit

**T1**: Nærmeste motstandsnivå (for LONG) med høyest HTF-vekt som gir R:R ≥ 1.5:
- Prioriterer høyere vekt (D1/ukentlig) over nærmere nivåer
- T1 kvalitet: `htf` (vekt ≥ 3), `4h` (vekt ≥ 2), `weak` (vekt < 2)

**T2**: Neste motstandsnivå etter T1, eller T1 + risk-avstand som fallback.

### R:R-beregning

```
risk = |entry - SL|
R:R_T1 = |T1 - entry| / risk    (minimum 1.5)
R:R_T2 = |T2 - entry| / risk
```

---

## Steg 4: Filtrering og Horizon Config (push_signals.py)

### Horisont-basert filtrering

Fra alle instrumenter filtreres kun de som passerer:

1. **Horisont-terskel** — vektet score ≥ terskel for sin horisont
2. **Klar retning** — `dir_color` er "bull" eller "bear"
3. **Aktiv setup** — `setup_long` (bull) eller `setup_short` (bear) eksisterer
4. **Tradeable** — DXY ekskludert
5. **Ikke WATCHLIST** — pushes aldri

### Push-terskler

| Horisont | Minimum vektet score |
|----------|---------------------|
| SCALP | 5.5 |
| SWING | 7.5 |
| MAKRO | 8.5 |
| WATCHLIST | Aldri |

### Sortering

Sorteres etter:
1. Horisont-prioritet (MAKRO > SWING > SCALP)
2. Score (høyest først)

Maks 5 signaler per kjøring.

### Horizon Config

Hvert signal inkluderer en `horizon_config` med parametre for boten:

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
  "exit_trail_atr_mult": {"fx": 3.0, "gold": 4.0, "oil": 3.5, "index": 3.0},
  "exit_ema_tf": "1H",
  "exit_be_timeout_hours": 48,
  "exit_timeout_full_hours": 120,
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
  "exit_trail_atr_mult": {"fx": 2.0, "gold": 2.5, "oil": 2.5, "index": 2.0},
  "exit_ema_tf": "D1",
  "exit_timeout_days": 15,
  "exit_score_deterioration": 6.0,
  "sizing_base_risk_usd": 60
}
```

### Global State

```json
{
  "geo_active": true,
  "vix_regime": "normal",
  "oil_geo_warning": true,
  "oil_warning_reason": "Brent +27% 20d · krig/angrep i nyheter"
}
```

**Geo-aktiv** trigges av:
- Krigs-/sanksjonsord i nyheter (iran, israel, attack, war, strike, sanction, invasion, escalat)
- Brent opp mer enn 15% over 20 dager

### Olje supply-disruption

Leser shipping og oilgas-data (Hormuz, Suez, Midtøsten-konflikt). Når noen av disse har `risk = HIGH`:

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

### Scoring per avling

| Komponent | Poeng | Hva det sjekker |
|-----------|-------|-----------------|
| Outlook total_score | 0–5 | Abs(vær + COT + yield) |
| Yield stress | 0–3 | Lav yield_score = prispress opp |
| Weather urgency | 0–2 | Akutt tørke/flom (wx_score ≥ 3) |
| ENSO risk | 0–2 | El Niño/La Niña-effekt (enso_adj) |
| **Total** | **0–12** | Sum av alle komponenter |

### Filtrering

- **Minimum score: 5.0** — under dette er signalet for svakt
- **Kun in-season avlinger** — utenfor sesong er data upålitelig
- **Kun tradeable instrumenter** — palmeolje og ris filtreres bort
- **Grade C droppes** — kun A (score ≥ 7) og B (score ≥ 5) sendes til bot

### Retning og horisont

| Grade | Score | Horisont |
|-------|-------|----------|
| A | ≥ 7 | MAKRO |
| B | ≥ 5 | SWING |
| C | < 5 | Sendes ikke |

Retning bestemmes av outlook-signal:
- BULLISH / STERKT BULLISH → BUY
- BEARISH / STERKT BEARISH → SELL
- NØYTRAL → ingen signal

### Entry/SL/T1-beregning

Basert på estimert ATR (prosent av pris per instrument):

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

**Boten rekalibrerer** entry/SL/T1 med live ATR(14) hvis estimat avviker > 30%.

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
For olje med geo-warning: margin utvides til 0.4%.

#### Character (for bot størrelse)

| Grade + Score | Character |
|--------------|-----------|
| A+/A | A+ |
| B | B |
| C | C |

### Agri-signaler (POST /push-agri-alert → GET /agri-signals)

Konverterer agri-format til standard bot-format:
- Entry/SL/T1/T2 direkte (ikke i setup-dict)
- `expiry_candles`: 48 (4 timer, vs 8 for tekniske)
- `confirmation_candle_limit`: 12 (1 time for bekreftelse)
- `source`: "agri_fundamental"
- `valid_until`: 24 timer fra generering

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

Confirmation skjer på horizon_config.confirmation_tf:

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

For agri-instrumenter: halvparten av normal størrelse.
Maks samtidige agri-posisjoner: 2.

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
| **Trail** | Trail stop truffet (3.0-4.0×ATR 1H) | Lukk remaining |
| **EMA9** | EMA9(1H) krysser pris (post-T1) | Lukk remaining |
| **BE timeout** | 48 timer uten T1 | Flytt SL → break-even |
| **Full timeout** | 120 timer total | Lukk alt remaining |
| **Event** | Høy-risiko event innen 2 timer | Lukk alt |
| **Geo-spike** | > 3.0×ATR mot posisjon | Nødlukk alt |

**MAKRO:**

| Regel | Trigger | Handling |
|-------|---------|----------|
| **T1** | Pris ≥ T1 | Lukk 25%, SL → break-even |
| **T2** | Pris ≥ T2 | Lukk 25%, trail aktivert |
| **Trail** | Trail stop truffet (2.0-2.5×ATR D1) | Lukk remaining |
| **EMA9** | EMA9(D1) krysser pris (post-T1) | Lukk remaining |
| **Score-forverring** | Score faller under 6.0 | Lukk alt |
| **Full timeout** | 15 dager total | Lukk alt remaining |
| **Geo-spike** | > 3.0×ATR mot posisjon | Nødlukk alt |

### Trail Stop (etter T1) — per instrument-gruppe

| Gruppe | SCALP | SWING | MAKRO |
|--------|-------|-------|-------|
| FX | 2.0×ATR | 3.0×ATR | 2.0×ATR |
| Gold | 2.5×ATR | 4.0×ATR | 2.5×ATR |
| Silver | 2.5×ATR | 4.0×ATR | 2.5×ATR |
| Oil | 2.5×ATR | 3.5×ATR | 2.5×ATR |
| Index | 2.0×ATR | 3.0×ATR | 2.0×ATR |

### Agri-spesifikke regler

- **Session-filter**: Trades avvises utenfor likvide timer (spread for vid)
- **Maks 2 samtidige agri-posisjoner**
- **Strengere spread-grense**: 1.5×normal_spread (vs 3.0× for standard)
- **ATR-rekalibrering**: Hvis estimert ATR avviker > 30% fra live ATR(14), justeres entry/SL/T1

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
               Yahoo/Stooq/Finnhub/FRED         Open-Meteo/NOAA/CFTC
                        │                                │
                   fetch_all.py                    fetch_agri.py
                        │                                │
                ┌───────┴───────┐                ┌───────┴───────┐
                │               │                │               │
          Prisdata         COT-data          Vær/ENSO        Agri COT
          ATR/EMA/SMA      CFTC + ICE       Yield/Vekst     Euronext
                │               │                │               │
                └───────┬───────┘                └───────┬───────┘
                        │                                │
               Nivå-identifisering                Outlook scoring
               (intraday/swing/SMC)              (yield+vær+ENSO+COT)
                        │                                │
                14-punkt vektet score             Agri signal score
                + horisont-bestemmelse            (A/B filtrering)
                        │                                │
                  Setup-generering                Entry/SL/T1-beregning
                  (make_setup_l2l)                (ATR%-basert)
                        │                                │
              data/macro/latest.json           data/agri/latest.json
                        │                                │
                  push_signals.py              push_agri_signals.py
                  (horisont-filtrering)        (score ≥ 5, grade A/B)
                        │                                │
               ┌────────┴────────┐              ┌────────┴────────┐
               │                 │              │                 │
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
                                    ┌───────┼───────┐
                                    │       │       │
                              Entry zone  Confirm  Session
                              detection   (tf)     filter
                                    │       │       │
                                    └───────┼───────┘
                                            │
                                     Position opened
                                            │
                              ┌─────────────┼─────────────┐
                              │             │             │
                        T1 (25-50%)    Trail/EMA9     Timeout
                        per horisont   per horisont   per horisont
                              │
                        signal_log.json
                        (PnL + result → git push)
```

---

## Nåværende aktive signaler

Kjøres 6× daglig via `update.sh` og priser oppdateres hver time via `update_prices.sh`.

For å se aktive signaler:
```bash
cat data/signals.json | python3 -m json.tool
cat data/agri_signals.json | python3 -m json.tool
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
