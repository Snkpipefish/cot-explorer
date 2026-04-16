# COT Explorer – Markedspuls

Live: https://snkpipefish.github.io/cot-explorer
Repo: https://github.com/Snkpipefish/cot-explorer

---

## Hva er dette?

En statisk nettside (GitHub Pages) med tre dashboards som viser daglige trading-ideer og markedsintelligens. Navigasjonen har **5 hovedtaber** som deler seg over to HTML-filer:

- **🏠 Markedspuls** (`index.html`) — Oversikt, Setups & Trades, Makro & COT, Priser & Kalender
- **⛽ Energi & Shipping** (`metals-intel.html#energy`) — Olje/gass-priser, COT, segment-scoring, shipping, Mapbox-kart
- **🏦 Metaller** (`metals-intel.html#metals`) — COMEX lager, metall-COT, geo-intel, Mapbox-kart
- **🌾 Avlinger** (`metals-intel.html#agri`) — Avlings-analyse, vær, vekstsyklus, agri-COT, Mapbox-kart
- **₿ Krypto Intel** (`crypto-intel.html`) — Markedsbildet, Signaler, Store investorer, Nyheter

---

## Markedspuls (`index.html`)

4 under-faner:

### 🏠 Oversikt (standard) — "Dumbass-oversikt"
Én scrollbar side som forklarer alt i klarspråk:

- **Stemningsbanner** — 🟢/🟡/🔴 basert på VIX-nivå med forklaring
- **4 nøkkeltall** — VIX, Dollar-retning, Nyhetssentiment, Neste store hendelse
- **Hva skjer nå?** — 6 kort: Aksjer (SPX), Gull, Olje (Brent), Dollar (DXY), Store investorer (COT), Boten (win-rate + åpne trades)
- **Topp signaler** — Maks 3 beste setups med entry/SL/TP i klarspråk

### 💡 Setups & Trades
- **VIX-regime** + posisjonsstørrelse + aktive A/A+-signaler
- **Setup-kort** med expandable detaljer (12-punkt konfluens, SMC-analyse, nivåer)
- **Signal-logg** med stats + trade-tabell fra boten

### 🌐 Makro & COT
- **Dollar Smile-modell** + VIX-regime + Safe-haven hierarki
- **Makroindikatorer** — HYG, TIP, TNX, IRX, Kobber, EEM
- **Rente & Kreditt** — realrenter, spreader, vekst
- **VIX term-struktur** — contango/backwardation
- **COT-posisjoner** — 600+ markeder med søk, accordion-grupper, klikk for historikkgraf

### 💹 Priser & Kalender
- **Markedspriser** — Indekser, Valuta, Råvarer med 1d/5d/20d endring
- **Økonomisk kalender** — High/Medium impact events (filtrerer bort passerte)
- **Korrelasjonstabell** — 20-dagers Pearson (responsiv for mobil)

---

## Energi & Shipping (`metals-intel.html#energy`)

- **Oversiktsbanner** med Brent, WTI, NatGas, Baltic Dry Index, overordnet signal
- **Sammendragstabell** — alle 5 instrumenter med pris, 1d endring, COT bias, momentum og signal
- **Instrumentkort** med doble sparklines (pris 15d + COT 8 uker)
- **Brent-WTI spread** beregnet løpende
- **8 segmenter** scoret: OPEC, US supply, Russland, Midtøsten, LNG, raffineri, etterspørsel, fornybar
- **Overall signal** — majoritetsstemme over alle 5 instrumenter vektet med segment-risiko (ikke hardkodet)
- **Brent COT** — OI-vektet kombinasjon av ICE Futures Europe + CFTC
- **Heating Oil** — bruker ICE Gasoil COT direkte
- **Baltic-indekser** — BDI, BCI, BPI, BSI
- **8 shippingruter** med disrupsjonsvarsling
- **COT stacked bar charts** — total/long/short kontrakter med datoer
- **Mapbox-kart** — pipelines, shippingruter, chokepoints (ikke zoombart)

---

## Metaller (`metals-intel.html#metals`)

- **Oversiktsbanner** med Gull, Sølv, Kobber, COMEX stress
- **COMEX lagerbeholdning** — registrert vs. eligible for gull, sølv, kobber med stress-indeks
- **Intel Feed** — Google News RSS for metaller/geopolitikk
- **COT stacked bar charts** — metall-relaterte COT med total/long/short
- **Mapbox-kart** — gruver (26 stk), seismisk aktivitet, COMEX-lokasjon

---

## Avlinger (`metals-intel.html#agri`)

- **Oversiktsbanner** med Mais, Hvete, Kaffe, ENSO-fase
- **10 avlinger**: Mais, Hvete, Soyabønner, Canola, Bomull, Sukker, Kaffe, Kakao, Palmeolje, Ris
- **14 regioner** med Open-Meteo vær-scoring og COT-kombinasjon (CFTC + Euronext)
- **ENSO-indikator** (El Niño/La Niña) fra NOAA CPC med impakt-mapping per region
- **Vekstsyklus-deteksjon**: visuell tidslinje fra Såing → Vekst → Blomstring → Modning → Høsting
- **Historisk sesongvær**: GDD (Growing Degree Days) og nedbør-akkumulering
- **Yield-kvalitetsestimat**: Utmerket/God/Middels/Svak/Kritisk
- **Integrert outlook**: vær + COT + yield + ENSO → STERKT BULLISH → STERKT BEARISH
- **Bot-priser** for Coffee, Cotton, Sugar, Cocoa, Corn, Soybean, Wheat (oppdatert hver time)
- **COT stacked bar charts** — landbruk + lumber med total/long/short
- **Mapbox-kart** — landbruksregioner med vær-overlay

---

## Krypto Intel (`crypto-intel.html`)

Designet for brukere uten kryptoerfaring — alt forklares på norsk i klartekst.

### 🏠 Oversikt (standard)
Dashboard med 4 kort: Markedsbildet, Signaler, Store investorer, Nyheter

### 💡 Markedsbildet
- Stemningsbanner (🟢/🟡/🔴) med klarspråklig forklaring
- 3 signalkort: markedsverdi, Bitcoin-dominans, Fear & Greed
- Prisoversikt: BTC, ETH, SOL, XRP, BNB, ADA, DOGE, AVAX

### 🔍 Signaler
- Korrelasjoner mot S&P 500 og gull forklart i dagligspråk

### 🏦 Store investorer
- Bitcoin COT fra CME futures
- COT stacked bar charts med total/long/short kontrakter og datoer (ikke "u1-u7")
- Posisjonsbar og 8-ukers sparkline

### 📰 Nyheter
- Krypto-nyheter kategorisert: Bitcoin, Ethereum, Regulering, Makro, Altcoins

---

## Workflow — automatisk oppdatering (systemd timer)

To timers kjører på serveren:

**`cot-prices.timer`** — hvert hele time på XX:40
Kjører `update_prices.sh`: henter bot-priser → patcher JSON → `rescore.py` (oppdaterer sma200, momentum_20d, d1_4h_congruent + graduert DXY-penalty) → `push_signals.py --scalp-only` → git push

**`cot-explorer.timer`** — 6× daglig hverdager (00/04/08/12/16/20 CET) + **lørdag 00:00**
Kjører `update.sh`: full pipeline (se tabell under)

`Persistent=true` sikrer at missede kjøringer kjøres automatisk ved oppstart.

> **Prisflyt:** Bot sender priser kl. XX:35 → `update_prices.sh` kjører XX:40 → git push → GitHub Pages oppdatert ~XX:42
>
> **COT-publiseringstider:** CFTC slipper kl. 21:30 EDT (ca. 03:30 CEST) på fredager. ICE slipper kl. 19:30 EDT (ca. 01:30 CEST) på fredager. Lørdag 00:00-kjøringen henter begge garantert etter publisering.
>
> Kjør manuelt: `bash ~/cot-explorer/update.sh`
> Logg: `tail -f ~/cot-explorer/logs/update.log`
> Prislogg: `tail -f ~/cot-explorer/logs/prices.log`

### Hva update.sh gjør (i rekkefølge)

| # | Script | Beskrivelse |
|---|--------|-------------|
| 0 | git fetch/rebase | Synkroniser med GitHub |
| 1 | `fetch_calendar.py` | ForexFactory-kalender |
| 2 | `fetch_cot.py` | CFTC COT-data — kun lørdag 00:00–04:00 |
| 3 | `build_combined.py` | Kombinert COT-datasett — kun lørdag 00:00–04:00 (og onsdag etter Euronext) |
| 4 | `fetch_ice_cot.py` | ICE Futures Europe COT (Brent, Gasoil, TTF) — kun fredag ≥20:00 og lørdag 00:00 |
| 5 | `fetch_euronext_cot.py` | Euronext MiFID II COT (hvete, raps, mais) — kun onsdag ≥12:00 |
| 6 | `fetch_fundamentals.py` | FRED makrodata (maks 1× per 12t) |
| 7 | `fetch_all.py` | Full analyse: priser, SMC, nivåer, score, setups, VIX, korrelasjoner, ADR |
| 8 | `fetch_comex.py` | COMEX lagerbeholdning |
| 9 | `fetch_seismic.py` | USGS seismiske data |
| 10 | `fetch_intel.py` | Google News RSS for metaller |
| 11 | `fetch_agri.py` | Vær + COT for 10 avlinger / 14 regioner |
| 12 | `fetch_shipping.py` | Baltic-indekser + rute-scoring |
| 13 | `fetch_oilgas.py` | Energipriser + segment-scoring |
| 14 | `fetch_crypto.py` | Krypto-priser, Fear & Greed, COT, korrelasjoner |
| 15 | `push_signals.py` | Genererer `signals.json` (tekniske + agri merget), pusher alt via `/push-alert` |
| 16 | `push_agri_signals.py` | Genererer `agri_signals.json` (leses av push_signals.py) |
| 17 | git push | Oppdaterer GitHub Pages |

---

## Signal-varsling og trading bot

`push_signals.py` sender de beste tradingideene til Telegram, Discord og Flask-server via én `/push-alert` endpoint. Tekniske og agri-signaler merges inn i samme `signals.json` og samme Flask-push. Agri-signaler merkes med `source: "agri_fundamental"` slik at boten kan rekalibrere entry/SL/T1 med live ATR.

`push_agri_signals.py` genererer fundamentale agri-setups basert på outlook (vær + COT + yield + ENSO) og skriver til `agri_signals.json`. Ingen separat Flask-push — `push_signals.py` merger dette inn.

Alle scoring-konstanter og delte funksjoner (SCORE_WEIGHTS, GRADE_THRESHOLDS, HORIZON_CONFIGS, determine_horizon, calculate_weighted_score, get_grade) er samlet i `scoring_config.py` og importert av `fetch_all.py`, `rescore.py` og `push_signals.py`.

### Filtrering
- Horisont-basert: score ≥ terskel for instrumentets horisont (SCALP 3.0 / SWING 4.5 / MAKRO 5.5)
- WATCHLIST pushes aldri — kun synlig på dashboardet
- Kun klare retninger: `dir_color` er `bull` eller `bear`
- Sortert etter horisont-prioritet (MAKRO > SWING > SCALP), deretter score
- **DXY ekskludert** (ikke-tradeable indeks)
- **Oil war-spread beskyttelse**: Brent +15% 20d ELLER krig-nøkkelord → `oil_geo_warning=true`
- **Olje supply-disruption**: Når Hormuz/Midtøsten har HIGH risk i shipping/oilgas-data → olje SHORT blokkeres automatisk, dir_color tvinges bull

### signals.json — global_state og rules

```json
{
  "generated": "2026-04-01 08:00 UTC",
  "global_state": {
    "geo_active": true,
    "vix_regime": {"regime": "elevated"},
    "oil_geo_warning": true,
    "oil_warning_reason": "Brent +27% 20d · krig/angrep i nyheter"
  },
  "rules": {
    "risk_pct_full": 1.0,
    "risk_pct_half": 0.5,
    "risk_pct_quarter": 0.25,
    "geo_spike_atr_multiplier": 2.0,
    "oil_max_spread_mult": 3.0,
    "oil_min_sl_pips": 25
  },
  "signals": [...]
}
```

### Signal-logg

`trading_bot.py` skriver direkte til `data/signal_log.json` ved trade-hendelser. `push_signals.py` skriver ikke til loggen.

### Miljøvariabler

| Variabel | Beskrivelse |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot-token fra @BotFather |
| `TELEGRAM_CHAT_ID` | Chat-ID som skal motta meldinger |
| `DISCORD_WEBHOOK` | Discord webhook-URL |
| `PUSH_MIN_SCORE` | Fallback minimum score (brukes ikke lenger — erstattet av horisont-terskler) |
| `PUSH_MAX_SIGNALS` | Maks antall signaler per kjøring (standard: 5) |
| `FLASK_URL` | URL til signal_server.py |
| `SCALP_API_KEY` | API-nøkkel til Flask `/push-alert` og `/push-prices` |
| `FRED_API_KEY` | FRED makrodata (**påkrevd** — sett i `~/.cot-env`) |
| `TWELVEDATA_API_KEY` | Forex + gull OHLC |
| `FINNHUB_API_KEY` | Sanntidspris for indekser/råvarer |

> Miljøvariabler lagres i `~/.cot-env` (chmod 600). `update.sh` sourcer denne filen automatisk slik at systemd-tjenesten får tilgang uten å laste `~/.bashrc`.

---

## Slik beregnes trading-ideer

### Retningsbestemmelse (dir_color)

Sammensatt score som bestemmer bull/bear-retning per instrument:

| Signal | Vekt | Forklaring |
|--------|------|------------|
| SMA200 | ±1.5 | Tyngst — definerer langsiktig trend |
| chg5d | ±0.5/1.0 | Kort momentum (kun hvis \|chg5\| > 0.1/0.3%) |
| chg20d | ±0.5/1.0 | Mellomlang momentum (kun hvis \|chg20\| > 0.3/1.0%) |
| COT bias | ±1.0 | Store aktørers posisjonering (LONG/SHORT) |
| COT momentum | ±0.5 | Ukentlig endring forsterker |
| DXY-bias | ±0.5 | Kun USD-par: XXXUSD invers, USDXXX følger DXY |
| Momentum-divergens | -0.5 | Straff hvis chg5 og chg20 peker motsatt |

Hysterese: bull krever > 0.5, bear < -0.5. Mellom → SMA200 bestemmer.

### Vektet konfluens-score (9 kriterier)

Kun reelle setup-faktorer — boten håndterer entry-timing, event-risiko og ADR selv.

| # | Kriterium | SCALP | SWING | MAKRO | Beskrivelse |
|---|-----------|-------|-------|-------|-------------|
| 1 | `sma200` | 1.0 | 1.0 | 1.0 | Over SMA200 (D1 trend) |
| 2 | `momentum_20d` | 1.0 | 1.0 | 1.0 | chg20 > 0.5% i SMA200-retning |
| 3 | `cot_confirms` | — | 1.0 | 1.0 | COT bekrefter retning |
| 4 | `cot_strong` | — | 0.5 | 1.0 | COT sterk posisjonering (>10% av OI) |
| 5 | `cot_momentum` | — | 1.0 | 1.0 | COT ukentlig endring bekrefter retning |
| 6 | `htf_level_weight` | 1.0 | 1.0 | 1.0 | HTF-nivå D1/Ukentlig i nærheten (weight ≥ 3) |
| 7 | `d1_4h_congruent` | 1.0 | 1.0 | 1.0 | D1 + 4H EMA9 kongruent |
| 8 | `fred_fundamental` | — | — | 1.0 | Fundamental (FRED) bekrefter retning |
| 9 | `smc_confirms` | 1.0 | 1.0 | 1.0 | BOS + SMC markedsstruktur bekrefter |
| | **Maks** | **5.0** | **7.5** | **9.0** | |

Fjernet (boten sin jobb): `price_at_level` (entry-overvåking), `no_event_risk` (binary risk filter), `adr_utilization` (entry-timing), `news_sentiment` (upålitelig kilde), `vix_term_structure` (dekket av VIX-regime sizing).

### Score-justeringer (etter vekting)

| Justering | Penalty | Når |
|-----------|---------|-----|
| DXY-konflikt | -0.5 til -2.0 (graduert etter DXY momentum) | USD-par med retning motstridende DXY. Penalty = base × clamp(\|DXY chg5d\| / 2.0%, 0.25, 1.0). Base: 2.0 (SWING/MAKRO), 1.0 (SCALP) |
| Signal-flip | Nedgradering 1 nivå | Retning eller horisont endret siden forrige kjøring |

### Olje supply-disruption override

Leser `data/shipping/latest.json` og `data/oilgas/latest.json` ved oppstart:

| Kilde | Trigger | Betingelse |
|-------|---------|------------|
| Shipping | Hormuz-stredet | `risk = HIGH` |
| Shipping | Suez/Rødehavet | `risk = HIGH` (tilleggsinfo) |
| Oilgas | Midtøsten-konflikt | `risk = HIGH` |

Når aktiv:
- `dir_color` tvinges til `bull` for Brent og WTI (supply-squeeze = bullish)
- SHORT-signaler blokkeres i `push_signals.py`
- `oil_supply_disruption = true` og `oil_supply_reason` synlig i output
- Deaktiveres automatisk når shipping/oilgas risk synker under HIGH

### Horisont-bestemmelse

Krever **både** rå bool-telling OG minimum vektet score for kvalitetssikring:

| Horisont | Rå telling | Tilleggskrav | Min vektet score |
|----------|-----------|--------------|-----------------|
| MAKRO | ≥ 6/9 treff | COT + weight ≥ 4 | ≥ 7.0 (av 9.0) |
| SWING | ≥ 5/9 treff | weight ≥ 3 | ≥ 5.0 (av 7.5) |
| SCALP | ≥ 3/9 treff | — | — |
| WATCHLIST | < 3 treff | — | — |

SCALP utenfor optimal sesjon → WATCHLIST automatisk.

### Grade per horisont

| Horisont | A+ | A | B | C |
|----------|----|---|---|---|
| MAKRO | ≥ 8.0 | ≥ 7.0 | ≥ 5.5 | < 5.5 |
| SWING | ≥ 6.5 | ≥ 5.5 | ≥ 4.0 | < 4.0 |
| SCALP | ≥ 4.5 | ≥ 3.5 | ≥ 2.5 | < 2.5 |

### Push-terskler (til boten)

| Horisont | Minimum vektet score |
|----------|---------------------|
| SCALP | 3.0 |
| SWING | 4.5 |
| MAKRO | 5.5 |
| WATCHLIST | Pushes aldri |

### Signal-stabilitet

`signal_stability.json` lagrer forrige kjørings horisont, retning, score og grade per instrument. Neste kjøring sammenligner:
- Retning flippet (bull → bear) → nedgradér horisont 1 nivå
- Horisont flippet (SWING → SCALP → SWING) → nedgradér horisont 1 nivå
- Nedgradering: MAKRO → SWING → SCALP → WATCHLIST

### VIX-regime og posisjonsstørrelse

| VIX | Posisjonsstørrelse |
|-----|--------------------|
| < 20 | Full |
| 20–30 | Halv |
| > 30 | Kvart |

### Nivåhierarki

| Weight | Nivå |
|--------|------|
| 5 | PWH / PWL |
| 4 | PDH / PDL |
| 3 | D1 swing / PDC / SMC 1H |
| 2 | 4H swing / SMC 4H |
| 1 | 15m pivot / SMC 15m |

### Entry-seleksjon per horisont

| Horisont | Strategi | Maks avstand |
|----------|----------|-------------|
| SCALP | Nærmeste nivå (tight entry) | 1.0×ATR(D1) |
| SWING | Sterkeste weight innen 3×ATR(D1) | 3.0×ATR(D1) |
| MAKRO | Sterkeste weight innen 5×ATR(D1) | 5.0×ATR(D1) |

SWING/MAKRO prioriterer sterke nivåer (PWH/PWL, PDH/PDL) over nære svake nivåer (15m). SCALP bruker nærmeste for tight entry.

### SL-buffer per kategori

| Kategori | Buffer |
|----------|--------|
| Valuta | 0.15×ATR(D1) |
| Råvarer | 0.25×ATR(D1) |
| Aksjer | 0.20×ATR(D1) |

### T1/T2-cap per horisont

| Horisont | T1 maks | T2 maks | Min R:R |
|----------|---------|---------|---------|
| SCALP | 2.0×ATR(D1) | 3.0×ATR(D1) | 1.0 |
| SWING | 5.0×ATR(D1) | 8.0×ATR(D1) | 1.3 |
| MAKRO | Ingen cap | Ingen cap | 1.5 |

### Timeout per horisont

| Horisont | Partial timeout | Hard close |
|----------|----------------|------------|
| SCALP | 8 candles (40 min) | 16 candles (80 min) |
| SWING | 96 candles (8 timer) | 120 timer (5 dager) |
| MAKRO | 288 candles (24 timer) | 360 timer (15 dager) |

### Trail ATR-multiplikator

SCALP bruker 15m ATR, SWING/MAKRO bruker 1H ATR:

| Gruppe | SCALP (15m ATR) | SWING (1H ATR) | MAKRO (1H ATR) |
|--------|-----------------|----------------|----------------|
| FX | 2.0 | 3.0 | 5.0 |
| Gold | 2.5 | 4.0 | 6.0 |
| Silver | 2.5 | 4.0 | 6.0 |
| Oil | 2.5 | 3.5 | 5.5 |
| Index | 2.0 | 3.0 | 5.0 |

### Give-back parametere per gruppe

| Gruppe | Peak threshold | Exit threshold |
|--------|---------------|----------------|
| FX | 0.85 | 0.30 |
| Gold | 0.90 | 0.45 |
| Silver | 0.88 | 0.42 |
| Oil | 0.90 | 0.45 |
| Indices | 0.85 | 0.35 |
| Agri | 0.85-0.88 | 0.35 |

### Regime-baserte korrelasjonsgrenser

Basert på VIX-nivå strammes maks samtidige posisjoner:

| Regime | VIX | Precious | Indices | Energy | USD pairs | Total maks |
|--------|-----|----------|---------|--------|-----------|------------|
| Normal | < 25 | 2 | 1 | 1 | 2 | 6 |
| Risk-off | 25–35 | 1 | 1 | 1 | 1 | 3 |
| Crisis | > 35 | 1 | 1 | 1 | 1 | 2 |

### Weekend gate

- **Fredag 20:00 CET**: SCALP-posisjoner lukkes automatisk
- **Fredag 19:00 CET**: SWING/MAKRO SL strammes til 1.5×ATR fra nåpris (kun strammere, aldri videre)
- **Mandag 00:00–01:00 CET**: Entry blokkeres hvis gap > 2×ATR fra fredags close

### Daglig tapsgrense

2% av kontoverdi (med 500 NOK som gulv). Når grensen nås, blokkeres nye entries resten av dagen.

### Geo R:R minimum

Under geo-events: min R:R = 1.5 (senket fra 2.0). Per-horizon minimum gjelder fortsatt (SCALP 1.0, SWING 1.3, MAKRO 1.5).

---

## Instruments

### Tradeable (scores + signaler via fetch_all.py)

| Key | Priskilde | COT-marked | Klasse |
|-----|-----------|------------|--------|
| EURUSD | Bot (Skilling) | CFTC euro fx | A |
| USDJPY | Bot (Skilling) | CFTC japanese yen | A |
| GBPUSD | Bot (Skilling) | CFTC british pound | A |
| AUDUSD | Bot (Skilling) | — | A |
| Gold | Bot (Skilling) | CFTC gold | B |
| Silver | Bot (Skilling) | CFTC silver | B |
| Brent | Bot (Skilling) | ICE+CFTC (OI-vektet) | B |
| WTI | Bot (Skilling) | CFTC crude oil | B |
| SPX | Bot (Skilling) | CFTC s&p 500 | C |
| NAS100 | Bot (Skilling) | CFTC nasdaq mini | C |
| DXY | Bot (Skilling) | CFTC usd index | A (kun display, ikke tradeable) |
| VIX | Yahoo Finance | — | C (kun posisjonsstørrelse) |

### Kun priser (prices_only — vises på dashboard, ikke scoret)

| Key | Priskilde | Merknad |
|-----|-----------|---------|
| USDCHF | Bot (Skilling) | Korrelasjonsinstrument |
| USDNOK | Bot (Skilling) | Korrelasjonsinstrument |

### Kun bot pris-feed (ikke i fetch_all.py)

| Key | Priskilde | Merknad |
|-----|-----------|---------|
| USDCAD | Bot (Skilling) | Pris-feed til dashboard |
| NZDUSD | Bot (Skilling) | Pris-feed til dashboard |
| EURGBP | Bot (Skilling) | Pris-feed til dashboard |
| BTC/ETH/SOL/XRP/ADA/DOGE | Bot (Skilling) | Crypto dashboard |
| NatGas | Bot (Skilling) | Energi dashboard |

### Agri-instrumenter (signaler via fetch_agri.py + push_agri_signals.py)

| Key | Priskilde | Merknad |
|-----|-----------|---------|
| Coffee/Cotton/Sugar/Cocoa | Bot (Skilling) | Fundamental scoring (vær/yield/ENSO) |
| Corn/Soybean/Wheat | Bot (Skilling) | Fundamental scoring (vær/yield/ENSO) |

---

## Datakilder

| Data | Kilde | API-nøkkel |
|------|-------|------------|
| Live priser (primær) | Trading-bot via Skilling → `~/scalp_edge/live_prices.json` | Nei |
| COT (aksjer/forex/råvarer) | CFTC.gov | Nei |
| COT Brent/Gasoil/TTF | ICE Futures Europe | Nei |
| COT hvete/raps/mais | Euronext (MiFID II) | Nei |
| Daglige OHLC | Stooq (fallback) | Nei |
| Intradag 15m/1H | Yahoo Finance (fallback) | Nei |
| Forex + gull | Twelvedata | Ja |
| Sanntidspris (indekser/råvarer) | Finnhub | Ja |
| Fundamentals | FRED | Ja |
| Fear & Greed (krypto) | alternative.me | Nei |
| Nyhetssentiment | Google News RSS + BBC RSS | Nei |
| Kalender | ForexFactory JSON | Nei |
| Landbruksvær (7d varsel) | Open-Meteo Forecast API | Nei |
| Landbruksvær (sesong-historikk) | Open-Meteo Archive API | Nei |
| ENSO-fase (El Niño/La Niña) | NOAA CPC ONI | Nei |
| COMEX lager | CME Group | Nei |
| Seismisk aktivitet | USGS Earthquake API | Nei |
| Baltic shipping-indekser | Stooq | Nei |
| Shipping-nyheter | Google News RSS | Nei |
| Krypto markedsdata | CoinGecko API | Nei |

---

## Datafiler

| Fil | Innhold | Oppdatering |
|-----|---------|-------------|
| `data/macro/latest.json` | Priser, SMC, nivåer, score, kalender | Hver time + 6× daglig |
| `data/macro/signal_stability.json` | Forrige kjørings horisont/retning/score per instrument | 6× daglig |
| `data/prices/bot_history.json` | Rullerende prishistorikk (500 entries/symbol) for chg1d/5d/20d | Hver time |
| `data/signals.json` | Aktive signaler (tekniske + agri merget) + global state + horizon_config | 6× daglig + hver time (SCALP) |
| `data/agri_signals.json` | Agri-fundamentale trading-setups (leses av push_signals.py for merge) | 6× daglig |
| `data/combined/latest.json` | Kombinert CFTC COT-datasett | 6× daglig |
| `data/ice_cot/latest.json` | ICE Futures Europe COT (Brent, Gasoil, TTF) | 6× daglig |
| `data/ice_cot/history.json` | ICE COT 26-ukers historikk | 6× daglig |
| `data/euronext_cot/latest.json` | Euronext MiFID II COT (hvete, raps, mais) | 6× daglig |
| `data/euronext_cot/history.json` | Euronext COT 26-ukers historikk | 6× daglig |
| `data/signal_log.json` | Bot-trade historikk | Ved trade |
| `data/fundamentals/latest.json` | FRED makrodata | 2× daglig |
| `data/comex/latest.json` | COMEX lagerbeholdning + stress-indeks | 6× daglig |
| `data/agri/latest.json` | Avlings-analyse: vær, COT, ENSO, vekstsyklus, yield + bot-priser | 6× daglig + hver time (priser) |
| `data/agri/season_cache.json` | Cache for arkivvær + ENSO (maks 1× per dag) | 1× daglig |
| `data/shipping/latest.json` | Baltic-indekser, rute-scoring, nyheter | 6× daglig |
| `data/oilgas/latest.json` | Energipriser, COT, segment-scoring + bot-priser | 6× daglig + hver time (priser) |
| `data/crypto/latest.json` | Krypto-priser, Fear & Greed, COT, korrelasjoner | 6× daglig + hver time (priser) |
| `data/geointel/seismic.json` | USGS seismiske hendelser | 6× daglig |
| `data/geointel/intel.json` | Google News RSS metallnyheter | 6× daglig |
| `data/geointel/shipping_lanes.json` | Globale shippingruter | Statisk |
| `data/geointel/pipelines.json` | Oljeledninger | Statisk |
| `data/geointel/chokepoints.json` | 6 chokepoints | Statisk |
| `data/geointel/mines.json` | 26 gruver | Statisk |
| `~/scalp_edge/live_prices.json` | Live priser fra bot (21 symboler) | Hvert 58. min |
| `scoring_config.py` | Delte scoring-konstanter og funksjoner (SCORE_WEIGHTS, GRADE_THRESHOLDS, HORIZON_CONFIGS, DXY_MOMENTUM_THRESHOLD, CORRELATION_REGIME_CONFIGS) | — |
| `utils.py` | Delt verktøybibliotek (logging, retry, stooq, news, freshness) | — |
| `logs/` | Python-loggfiler per script | Ved kjøring |

---

## Kjente begrensninger / gotchas

- `data/euronext_cot/` opprettes kun etter at `fetch_euronext_cot.py` har kjørt (onsdag). `git add data/` (ikke `-u`) brukes for å fange nye filer.
- `update.sh` bruker `flock` for å unngå samtidig kjøring med bot-push. Lock-fil: `.git/bot_push.lock`.
- `trading_bot.py` pusher `signal_log.json` direkte til git ved trade-lukking. Bot-push bør alltid inkludere `git fetch + git rebase` før `git push` for å unngå konflikter med `update.sh`.
- `fetch_agri.py` og `fetch_oilgas.py` bruker `(x.get("cot") or {})` i stedet for `.get("cot", {})` for å håndtere `cot: null` i COT-data.
- GitHub Pages har aggressiv caching — bruk Ctrl+Shift+R etter push for å se endringer umiddelbart.
- Mapbox-kart i råvare-tabene er satt til `interactive: false` (ikke zoombare) med Mercator-projeksjon og utvidet høyde (650px) for å vise polområder.
- COT momentum bruker `change_spec_net` fra ukentlige COT-rapporter (`data/tff/`, `data/disaggregated/`), ikke timeseries-filer (som er utdaterte).
- Agri-signaler bruker Yahoo Finance som fallback når bot-priser mangler (`bot_history.json`).

---

## Robusthet og datakvalitet

### Delt verktøybibliotek (`utils.py`)

Felles hjelpefunksjoner som eliminerer kodeduplisering på tvers av fetch-scripts:

| Funksjon | Beskrivelse |
|----------|-------------|
| `get_logger(name)` | Logger med fil- og konsoll-output til `logs/` |
| `fetch_url()` / `fetch_json()` | HTTP med retry (eksponentiell backoff, 3 forsøk) |
| `fetch_stooq(symbol)` | Prisdata fra Stooq (brukes av oilgas, shipping, crypto) |
| `fetch_google_news()` | Google News RSS (brukes av oilgas, shipping, crypto, intel) |
| `save_json_with_meta()` | Lagrer JSON med `_meta`-felt for freshness-tracking |
| `validate_price()` | Validerer numeriske prisverdier (NaN, negative, range) |
| `check_data_freshness()` | Sjekker filens alder mot maks tillatt |

### Freshness-tracking (`_meta`)

Alle JSON-outputfiler inneholder et `_meta`-felt:

```json
{
  "_meta": {
    "generated_at": "2026-04-16T09:13:00Z",
    "script": "fetch_oilgas.py"
  }
}
```

`push_signals.py` sjekker freshness ved oppstart og advarer hvis upstream-data er for gammel:
- `macro/latest.json` — maks 6 timer
- `shipping/latest.json` — maks 24 timer
- `oilgas/latest.json` — maks 24 timer
- `fundamentals/latest.json` — maks 48 timer

### Signal-aldring (entry distance)

Signaler der prisen har beveget seg for langt fra entry-nivået avvises automatisk:

| Horisont | Maks avstand (×ATR) |
|----------|---------------------|
| SCALP | 1.5 |
| SWING | 2.5 |
| MAKRO | 4.0 |

### FRED-fallback

`fetch_fundamentals.py` har retry-logikk (3 forsøk med backoff) og bruker forrige kjøring som fallback hvis færre enn 3 indikatorer ble hentet.

### Prisvalidering i signal server

`/push-prices` avviser NaN, negative verdier og urealistisk høye priser (>10M). Ugyldig data logges med advarsel.

### Auto-refresh dashboard

Alle tre dashboards (`index.html`, `crypto-intel.html`) poller hvert 60. sekund og oppdaterer kun ved ny data.

### Frontend-optimalisering

`index.html` laster alle 5 JSON-filer parallelt med `Promise.all()` i stedet for sekvensielt — ~2-3× raskere initial lasting.

---

## Tech stack

| Komponent | Teknologi |
|-----------|-----------|
| Frontend | Vanilla HTML/CSS/JS — `index.html`, `metals-intel.html`, `crypto-intel.html` |
| Navigasjon | 5 hovedtaber i `nav-main` (Markedspuls, Energi & Shipping, Metaller, Avlinger, Krypto Intel) |
| Kart | Mapbox GL JS med satelitt/mørkt tema — per-tab overlays (pipelines, gruver, landbruk) |
| Grafer | Chart.js (COT-historikk modal, stacked bar charts) |
| Tidssoner | `toNO()` helper konverterer UTC-timestamps til norsk tid (Europe/Oslo) |
| Backend | Python 3 + `requests` + `openpyxl` + `utils.py` (delt verktøybibliotek) |
| Hosting | GitHub Pages (statisk) |
| Automatisering | `cot-prices.timer` (XX:40 hver time) + `cot-explorer.timer` (6× daglig man-fre + lør 00:00) |
| Prisintegrasjon | `signal_server.py` Flask — `POST /push-prices`, `GET /prices` → `update_prices.sh` patcher JSON |
| Scoring-config | `scoring_config.py` — delte konstanter og funksjoner (importert av fetch_all, rescore, push_signals) |
| Varsling | Telegram / Discord webhook / Flask REST API |
| Trading bot | `scalp_edge/trading_bot.py` — cTrader Open API, pusher priser hvert 58. min |
| SMC-motor | `smc.py` — Python-port av FluidTrades SMC Lite |

### COT-kildelogikk

| Instrument | Primær | Fallback | Kombinering |
|---|---|---|---|
| Brent | ICE Futures Europe | CFTC | OI-vektet snitt når begge ferske |
| Hvete / Raps / Mais | Euronext (MiFID II) | CFTC | OI-vektet snitt når begge ferske |
| Alle andre | CFTC | — | — |

Uenighet mellom to kilder → `momentum=BLANDET`, `cot_confirms=False`, `cot_strong=False`

### Olje overall_signal logikk

Bruker majoritetsstemme over alle 5 instrumenter (Brent, WTI, NatGas, RBOB, Heating Oil). Hvert instrument har et kombinert pris+COT-signal. Dersom ≥3 segmenter har HIGH risiko, tillegges ekstra bullish bias. Ingen hardkodede terskler — alt er dynamisk basert på faktisk data.
