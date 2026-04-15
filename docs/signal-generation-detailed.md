# Detaljert: Hvordan Trading Setups Genereres

## Oversikt

Trading-setups genereres i en 4-stegs pipeline:

```
fetch_all.py        → data/macro/latest.json     (nivåer, score, setups)
push_signals.py     → data/signals.json          (filtrert, for bot)
                    → POST /push-alert            (til signal_server.py)
signal_server.py    → latest_signals.json         (oversatt til bot-format)
trading_bot.py      → cTrader (Skilling)          (entry, confirmation, exit)
```

---

## Steg 1: Datainnhenting (fetch_all.py)

### 1.1 Prisdata

For hvert av 10 instrumenter hentes prisdata fra 3 kilder (prioritert):

| Prioritet | Kilde | Tidsrom | Intervall |
|-----------|-------|---------|-----------|
| 1 | Trading-bot (live_prices.json) | Sanntid | Hvert 4. time |
| 2 | Yahoo Finance | 1 år | D1, 1H, 15min |
| 3 | Stooq | 1 år | D1 |

**Instrumenter:**

| Instrument | Klasse | Sesjon |
|-----------|--------|--------|
| EURUSD | A | London |
| GBPUSD | A | London |
| USDJPY | B | London/NY |
| AUDUSD | B | London/NY |
| Gold | B | London/NY |
| Silver | C | NY |
| Brent | C | NY |
| WTI | C | NY |
| SPX500 | C | NY |
| NAS100 | C | NY |

Klasse A = London-sesjon, B = London/NY, C = NY.

### 1.2 Beregninger per instrument

Fra prisdata beregnes:

- **ATR(14)** på D1 og 15min — volatilitetsmål
- **EMA(9)** på 15min — kortsiktig trend
- **SMA(200)** på D1 — langsiktig trend
- **PDH/PDL/PDC** — Previous Day High/Low/Close
- **PWH/PWL** — Previous Week High/Low
- **Endring** 1d, 5d, 20d i prosent

### 1.3 Nivåer (Support & Resistance)

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

### 1.4 COT-data (CFTC)

Fra `data/combined/latest.json` hentes:

- **Net posisjon** for Managed Money (spekulanter)
- **Net endring** siste uke
- **Net % av Open Interest**
- **Bias**: LONG hvis net > 0, SHORT hvis net < 0
- **Momentum**: Stigende/Synkende basert på ukesendring
- **Enighet**: Sjekker om TFF og Disaggregated rapporter er enige

Mapping mellom instrumenter og CFTC-kontrakter:
```
EURUSD  → "EURO FX"
GBPUSD  → "BRITISH POUND"
Gold    → "GOLD"
Brent   → ICE COT (Brent Crude)
etc.
```

### 1.5 Makro-indikatorer

- **VIX** — markedsvolatilitet (Fear & Greed)
- **DXY** — dollarindeks
- **10Y/3M yield** — rentekurve
- **HYG** — high yield credit spread
- **TIP** — inflasjonsforventninger
- **Fear & Greed Index** — CNN (0-100)

### 1.6 Nyhetssentiment

Hentes fra Finnhub:
- Siste 50 markedsnyheter
- Klassifiseres som `risk_on`, `risk_off`, eller `neutral`
- Sjekkes for krigs-/sanksjonsord → `geo_active`

### 1.7 Fundamentals

Fra `data/fundamentals/latest.json`:
- Instrument-spesifikk fundamental score (-1 til +1)
- Bias: bullish/bearish/neutral

### 1.8 Kalender

Fra `data/fundamentals/latest.json`:
- Neste 4 timers økonomiske hendelser
- Brukes som "binary risk" filter

---

## Steg 2: Scoring (fetch_all.py)

Hvert instrument scores 0-12 basert på 12 kryssjekker:

| # | Kriterie | Hva det sjekker |
|---|---------|-----------------|
| 1 | **Over SMA200** | Pris > 200-dagers snitt (D1 trend) |
| 2 | **Momentum 20d** | 20-dagers endring bekrefter retning |
| 3 | **COT bekrefter** | Spekulanter posisjonert i same retning |
| 4 | **COT sterk (>10%)** | Net posisjon > 10% av Open Interest |
| 5 | **Pris VED HTF-nivå** | Nåpris innenfor ATR-avstand fra nivå |
| 6 | **HTF-nivå D1/Ukentlig** | Nærmeste nivå har vekt ≥ 3 |
| 7 | **D1+4H kongruent** | Begge tidsrammer peker same vei |
| 8 | **Ingen event-risiko** | Ingen NFP/CPI/FOMC neste 4 timer |
| 9 | **Nyhetssentiment** | Risk-on/off bekrefter retning |
| 10 | **Fundamental** | Instrument fundamental score bekrefter |
| 11 | **BOS 1H/4H** | Break of Structure i riktig retning |
| 12 | **SMC 1H struktur** | Smart Money markedsstruktur bekrefter |

### Retningsbestemmelse

```
if pris > SMA200 AND 5d-endring > 0:
    retning = BULL
elif pris < SMA200 AND 5d-endring < 0:
    retning = BEAR
else:
    retning = BULL hvis over SMA200, ellers BEAR
```

### Grade

| Score | Grade | Farge |
|-------|-------|-------|
| ≥ 11 | A+ | bull |
| ≥ 9 | A | warn |
| ≥ 6 | B | bear |
| < 6 | C | bear |

### Timeframe-klassifisering

| Betingelse | Timeframe | Holdperiode |
|-----------|-----------|-------------|
| Score ≥ 6 + COT + HTF-nivå | MAKRO | Dager/uker |
| Score ≥ 4 + HTF-nivå | SWING | Timer/dager |
| Score ≥ 2 + ved nivå + aktiv sesjon | SCALP | Minutter |
| Ellers | WATCHLIST | Ingen trade |

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

**Hvis linjnivå (PDH/PDL/D1/PWH/PWL):**
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

### Eksempel LONG-setup

```
Gold @ 4813.31, ATR(D1) = 45.20
Støtte: 4790 [PWL, vekt=4] med zone_bottom=4785

Entry:  4790.00  (PWL støtte)
SL:     4778.22  (zone_bottom 4785 - 0.15×45.20 buffer)
Risk:   11.78
T1:     4830.00  (D1 motstand, vekt=3) → R:R = 3.40
T2:     4855.00  (ukentlig motstand)   → R:R = 5.52
```

---

## Steg 4: Filtrering (push_signals.py)

### Signal-filter

Fra alle 10 instrumenter filtreres kun de som har:

1. **Score ≥ 7** (av 12) — minimum kvalitet
2. **Klar retning** — `dir_color` er "bull" eller "bear"
3. **Aktiv setup** — `setup_long` (bull) eller `setup_short` (bear) eksisterer
4. **Tradeable** — DXY ekskludert

### Sortering

Sorteres etter:
1. Timeframe (MAKRO > SWING > SCALP > WATCHLIST)
2. Score (høyest først)

Maks 5 signaler per kjøring.

### Global State

```json
{
  "geo_active": true/false,     // Krig i nyheter ELLER Brent +15% 20d
  "vix_regime": "normal/half/quarter",
  "oil_geo_warning": true/false // Blokkerer smale SL på olje
}
```

**Geo-aktiv** trigges av:
- Krigs-/sanksjonsord i nyheter (iran, israel, attack, war, strike, sanction, invasion, escalat)
- Brent opp mer enn 15% over 20 dager

---

## Steg 5: Signal-server translate (signal_server.py)

Flask-serveren oversetter signaler til bot-format:

### Entry Zone
```
entry_zone = [entry - 0.15% margin, entry + 0.15% margin]
```
For olje med geo-warning: margin utvides til 0.4%.

### Session-tider

| Instrument | Session | CET |
|-----------|---------|-----|
| EURUSD, GBPUSD | London | 08:00-17:00 |
| USDJPY, AUDUSD | Tokyo/London | 02:00-17:00 |
| Gold | London/NY | 08:00-21:00 |
| Silver | NY | 14:00-21:00 |
| Brent, WTI | NY | 14:00-21:00 |
| SPX500, US100 | NY | 15:30-22:00 |

### Character (for bot størrelse)

| Grade + Score | Character | Lot-størrelse |
|--------------|-----------|---------------|
| A+/A, score ≥ 9 | A+ | Full (0.03) |
| B, score ≥ 6 | B | Halv (0.02) |
| C, score < 6 | C | Kvart (0.01) |

### Confirmation-regler

Bot-en bruker 3-punkt bekreftelse på 5min candle close:

| Test | Betingelse | Poeng |
|------|-----------|-------|
| **Body size** | Body ≥ 30% av ATR(5min) | 1 |
| **Wick rejection** | Pris avviser fra entry zone | 1 |
| **EMA9 gradient** | EMA9 heller i riktig retning | 1 |

Trenger ≥ 2/3 poeng (3/3 hvis motstridende USD-retning).
Maks 6 candles (30 min) for bekreftelse.

---

## Steg 6: Bot-eksekusjon (trading_bot.py)

### Livssyklus

```
WATCHLIST → AWAITING_CONFIRMATION → IN_TRADE → CLOSED
```

### Position Sizing

| Regime | Lots |
|--------|------|
| Normal (VIX < 20) | 0.03 |
| Halvparten (VIX 20-25, grade B, utenfor sesjon) | 0.02 |
| Kvart (VIX > 25, geo aktiv, grade C) | 0.01 |

For agri-instrumenter: halvparten av normal størrelse.

### Exit-regler

| Regel | Trigger | Handling |
|-------|---------|----------|
| **T1** | Pris ≥ T1 | Lukk 50%, SL → break-even, trail aktivert |
| **Trail** | Trail stop truffet (post-T1) | Lukk remaining |
| **EMA9** | EMA9 krysser pris (post-T1) | Lukk remaining |
| **8-candle** | 8×5min uten T1 | Lukk 50% |
| **16-candle** | 16×5min total | Lukk alt remaining |
| **Geo-spike** | Pris beveger > 2×ATR mot posisjon | Nødlukk alt |
| **Kill-switch** | Manuell /invalidate | Lukk alt |

### Trail Stop (etter T1)

Instrument-spesifikke trail-multiplikatorer:
```
FX:      2.5×ATR
Gold:    3.5×ATR
Silver:  3.5×ATR
Oil:     3.0×ATR
Indices: 2.8×ATR
```

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
               Yahoo/Stooq/Finnhub/FRED
                        │
                   fetch_all.py
                        │
                ┌───────┴───────┐
                │               │
          Prisdata         COT-data
          ATR/EMA/SMA      CFTC + ICE
                │               │
                └───────┬───────┘
                        │
               Nivå-identifisering
               (intraday/swing/SMC)
                        │
                   12-punkt score
                        │
                  Setup-generering
                  (make_setup_l2l)
                        │
              data/macro/latest.json
                        │
                  push_signals.py
                  (score ≥ 7 filter)
                        │
               ┌────────┴────────┐
               │                 │
       data/signals.json    POST /push-alert
       (GitHub Pages)       (signal_server.py)
                                 │
                          latest_signals.json
                                 │
                            trading_bot.py
                            (cTrader API)
                                 │
                          ┌──────┴──────┐
                          │             │
                     Entry zone    Confirmation
                     detection     (5min candle)
                          │             │
                          └──────┬──────┘
                                 │
                          Position opened
                                 │
                     ┌───────────┼───────────┐
                     │           │           │
                    T1         8-candle    Geo-spike
                   (50%)      timeout     emergency
                     │
                Trail/EMA9
                   exit
                     │
               signal_log.json
               (PnL + result)
```

---

## Nåværende aktive signaler

Kjøres hvert 58. minutt via `update_prices.sh` og hvert 4. time via `update.sh`.

For å se aktive signaler:
```bash
cat data/signals.json | python3 -m json.tool
```

For å se historikk:
```bash
cat data/signal_log.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
for e in d['entries']:
    sig = e.get('signal', {})
    pnl = e.get('pnl', {})
    print(f\"{e.get('timestamp','')}  {sig.get('instrument',''):8s}  {e.get('exit_reason','open'):20s}  \${pnl.get('pnl_usd','?')}\")
"
```
