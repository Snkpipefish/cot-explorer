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
Kjører `update_prices.sh`: henter bot-priser fra `~/scalp_edge/live_prices.json` → patcher `macro/latest.json`, `oilgas/latest.json`, `agri/latest.json`, `crypto/latest.json` → git push

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
| 15 | `push_signals.py` | Genererer `signals.json` med horisont-basert filtrering, pusher varsler |
| 16 | `push_agri_signals.py` | Genererer `agri_signals.json` med fundamentale agri-setups, pusher til bot |
| 17 | git push | Oppdaterer GitHub Pages |

---

## Signal-varsling og trading bot

`push_signals.py` sender de beste tradingideene til Telegram, Discord og/eller Flask-server. Inkluderer `horizon_config` per signal med bekreftelse-TF, entry zone margin, exit-regler og sizing per horisont.

`push_agri_signals.py` genererer fundamentale agri-setups basert på outlook (vær + COT + yield + ENSO) og pusher til Flask `/push-agri-alert`. Boten henter disse separat via `/agri-signals`.

### Filtrering
- Horisont-basert: score ≥ terskel for instrumentets horisont (SCALP 5.5 / SWING 7.5 / MAKRO 8.5)
- WATCHLIST pushes aldri — kun synlig på dashboardet
- Kun klare retninger: `dir_color` er `bull` eller `bear`
- Sortert etter horisont-prioritet (MAKRO > SWING > SCALP), deretter score
- **DXY ekskludert** (ikke-tradeable indeks)
- **Oil war-spread beskyttelse**: Brent +15% 20d ELLER krig-nøkkelord → `oil_geo_warning=true`

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

### Vektet konfluens-score (14 kriterier)

Hvert kriterium har ulik vekt avhengig av horisont (SCALP/SWING/MAKRO). Maks score varierer per horisont.

| # | Kriterium | Beskrivelse |
|---|-----------|-------------|
| 1 | `sma200` | Over SMA200 (D1 trend) |
| 2 | `momentum_20d` | chg20 > 0.5% i SMA200-retning (ikke-sirkulært) |
| 3 | `cot_confirms` | COT bekrefter retning |
| 4 | `cot_strong` | COT sterk posisjonering (>10% av OI) |
| 5 | `cot_momentum` | COT ukentlig endring (`change_spec_net`) bekrefter retning |
| 6 | `price_at_level` | Pris VED HTF-nivå nå (innen 1.5×ATR) |
| 7 | `htf_level_weight` | HTF-nivå D1/Ukentlig i nærheten (weight ≥ 3) |
| 8 | `d1_4h_congruent` | D1 + 4H EMA9 kongruent (ekte 4H, ikke 15m) |
| 9 | `no_event_risk` | Ingen event-risiko (innen 4 timer) |
| 10 | `news_sentiment` | Nyhetssentiment med sterk konsensus (\|score\| ≥ 0.5) |
| 11 | `fred_fundamental` | Fundamental (FRED) bekrefter retning |
| 12 | `smc_confirms` | BOS + SMC markedsstruktur bekrefter retning (begge kreves) |
| 13 | `vix_term_structure` | VIX contango + VIX < 20 (risk assets) / backwardation (safe havens) |
| 14 | `adr_utilization` | ADR-utnyttelse < 70% (dagens range vs ATR, default False) |

### Score-justeringer (etter vekting)

| Justering | Penalty | Når |
|-----------|---------|-----|
| DXY-konflikt | -2.0 (SWING/MAKRO) / -1.0 (SCALP) | USD-par med retning motstridende DXY |
| Nyhetsmotvind | -1.0 | Sterk nyhetssentiment (\|score\| ≥ 0.4) mot retning |
| Signal-flip | Nedgradering 1 nivå | Retning eller horisont endret siden forrige kjøring |

### Horisont-bestemmelse

Krever **både** rå bool-telling OG minimum vektet score for kvalitetssikring:

| Horisont | Rå telling | Tilleggskrav | Min vektet score |
|----------|-----------|--------------|-----------------|
| MAKRO | ≥ 8 treff | COT + weight ≥ 4 | ≥ 8.0 (av 13.0) |
| SWING | ≥ 6 treff | weight ≥ 3 | ≥ 6.0 (av 11.5) |
| SCALP | ≥ 4 treff | price_at_level + i sesjon | — |
| WATCHLIST | < 4 treff | — | — |

SCALP utenfor optimal sesjon → WATCHLIST automatisk.

### Grade per horisont

| Horisont | A+ | A | B | C |
|----------|----|---|---|---|
| MAKRO | ≥ 11.5 | ≥ 9.5 | ≥ 7.5 | < 7.5 |
| SWING | ≥ 10.0 | ≥ 8.5 | ≥ 6.5 | < 6.5 |
| SCALP | ≥ 8.0 | ≥ 6.5 | ≥ 4.5 | < 4.5 |

### Push-terskler (til boten)

| Horisont | Minimum vektet score |
|----------|---------------------|
| SCALP | 5.5 |
| SWING | 7.5 |
| MAKRO | 8.5 |
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

---

## Instruments

| Key | Priskilde | COT-marked | Klasse |
|-----|-----------|------------|--------|
| EURUSD | Bot (Skilling) | CFTC euro fx | A |
| USDJPY | Bot (Skilling) | CFTC japanese yen | A |
| GBPUSD | Bot (Skilling) | CFTC british pound | A |
| AUDUSD | Bot (Skilling) | — | A |
| USDCHF | Bot (Skilling) | — | A |
| USDNOK | Bot (Skilling) | — | A |
| USDCAD | Bot (Skilling) | — | A |
| NZDUSD | Bot (Skilling) | — | A |
| Gold | Bot (Skilling) | CFTC gold | B |
| Silver | Bot (Skilling) | CFTC silver | B |
| Brent | Bot (Skilling) | ICE+CFTC (OI-vektet) | B |
| WTI | Bot (Skilling) | CFTC crude oil | B |
| SPX | Bot (Skilling) | CFTC s&p 500 | C |
| NAS100 | Bot (Skilling) | CFTC nasdaq mini | C |
| DXY | Bot (Skilling) | CFTC usd index | A (kun display) |
| VIX | Yahoo Finance | — | C (kun posisjonsstørrelse) |
| BTC/ETH/SOL/XRP | Bot (Skilling) | — | — |
| Coffee/Cotton/Sugar/Cocoa | Bot (Skilling) | — | — (agri-priser) |
| Corn/Soybean/Wheat | Bot (Skilling) | — | — (agri-priser) |

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
| `data/signals.json` | Aktive signaler + global state + horizon_config | 6× daglig |
| `data/agri_signals.json` | Agri-fundamentale trading-setups (outlook + yield + vær + ENSO) | 6× daglig |
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

---

## Kjente begrensninger / gotchas

- `data/euronext_cot/` opprettes kun etter at `fetch_euronext_cot.py` har kjørt (onsdag). `git add data/` (ikke `-u`) brukes for å fange nye filer.
- `update.sh` bruker `flock` for å unngå samtidig kjøring med bot-push. Lock-fil: `/tmp/cot-explorer-git.lock`.
- `trading_bot.py` pusher `signal_log.json` direkte til git ved trade-lukking. Bot-push bør alltid inkludere `git fetch + git rebase` før `git push` for å unngå konflikter med `update.sh`.
- `fetch_agri.py` og `fetch_oilgas.py` bruker `(x.get("cot") or {})` i stedet for `.get("cot", {})` for å håndtere `cot: null` i COT-data.
- GitHub Pages har aggressiv caching — bruk Ctrl+Shift+R etter push for å se endringer umiddelbart.
- Mapbox-kart i råvare-tabene er satt til `interactive: false` (ikke zoombare) med Mercator-projeksjon og utvidet høyde (650px) for å vise polområder.
- COT momentum bruker `change_spec_net` fra ukentlige COT-rapporter (`data/tff/`, `data/disaggregated/`), ikke timeseries-filer (som er utdaterte).
- Agri-signaler krever pris fra bot (`bot_history.json`) — uten bot-priser genereres ingen setups for det instrumentet.

---

## Tech stack

| Komponent | Teknologi |
|-----------|-----------|
| Frontend | Vanilla HTML/CSS/JS — `index.html`, `metals-intel.html`, `crypto-intel.html` |
| Navigasjon | 5 hovedtaber i `nav-main` (Markedspuls, Energi & Shipping, Metaller, Avlinger, Krypto Intel) |
| Kart | Mapbox GL JS med satelitt/mørkt tema — per-tab overlays (pipelines, gruver, landbruk) |
| Grafer | Chart.js (COT-historikk modal, stacked bar charts) |
| Tidssoner | `toNO()` helper konverterer UTC-timestamps til norsk tid (Europe/Oslo) |
| Backend | Python 3 + `requests` + `openpyxl` |
| Hosting | GitHub Pages (statisk) |
| Automatisering | `cot-prices.timer` (XX:40 hver time) + `cot-explorer.timer` (6× daglig man-fre + lør 00:00) |
| Prisintegrasjon | `signal_server.py` Flask — `POST /push-prices`, `GET /prices` → `update_prices.sh` patcher JSON |
| Agri-signaler | `signal_server.py` Flask — `POST /push-agri-alert`, `GET /agri-signals` |
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
