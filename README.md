# COT Explorer – Markedspuls

Live: https://snkpipefish.github.io/cot-explorer
Repo: https://github.com/Snkpipefish/cot-explorer

---

## Hva er dette?

En statisk nettside (GitHub Pages) med tre dashboards som viser daglige trading-ideer og markedsintelligens:

- **🏠 Markedspuls** (`index.html`) — Setups, COT, Makro, Kalender, Signal-logg, Priser
- **🛢️ Råvare Intel** (`metals-intel.html`) — Geo-Intel Kart, COMEX Lager, Intel Feed, Råvare COT, Avlings-analyse, Shipping, Olje & Gass
- **₿ Krypto Intel** (`crypto-intel.html`) — Markedsbildet, Signaler, Store investorer, Nyheter

Alle tre sider har en **to-nivås navigasjon**: øverste rad bytter mellom de tre dashboardene, nederste rad viser under-faner for gjeldende side.

---

## Markedspuls (`index.html`)

### 🏠 Oversikt (standard)
Dashboard-visning med 6 kort som lenker til under-fanene:
- **Setups** — antall aktive signaler, VIX-regime, geo-varsler
- **Makro** — Fear & Greed score, nyhetssentiment, dollar-fase
- **COT** — bull/bear-fordeling på tvers av alle COT-markeder
- **Signal-logg** — wins/losses/åpne trades fra bot-historikk
- **Kalender** — antall high-impact hendelser denne uken
- **Priser** — EURUSD, Gold, Brent, USDJPY med daglig endring

### 💡 Setups
- **Level-til-level setups** med entry ved faktisk strukturnivå, T1/T2 er neste reelle nivå
- **Konfluens-score (12 punkter)** inkl. SMA200, momentum, COT, HTF-nivå, sesjon, BOS, SMC-struktur, nyheter, fundamentals
- **SMC-analyse på tre tidshorisonter** — 15m, 1H og 4H: supply/demand soner, BOS, HH/LH/HL/LL
- **Binær risiko-varsling** — High-impact kalender-events innen 4 timer vises som ⚠️ på setup-kortet
  - Vanlige nøkkeltall (CPI, NFP, renter): risiko utløper **30 min** etter hendelsen
  - Taler, pressekonferanser, FOMC Minutes: risiko utløper **60 min** etter hendelsen
  - Utløp sjekkes i **sanntid i nettleseren** mot UTC-tidspunktet fra kalenderen

### 🌐 Makro
- Dollar Smile-modell, VIX-regime, yield curve og konflikt-flagging
- VIX term-struktur — spot vs. 9D vs. 3M, contango/backwardation-regime
- Makroindikatorer — HYG, TIP, TNX (10Y), IRX (3M), Kobber, EEM (alle inkl. chg20d)
- Fundamentals-panel — FRED-data: GDP, CPI, PPI, PCE, NFP, jobbtall (USD-bias-score)
- Nyhetssentiment — RSS fra Google News + BBC, risk-on/risk-off-scoring

### 📊 COT
- COT-posisjoner for 600+ markeder fra CFTC (siste uke) med 8-ukers sparkline, gruppert i accordion-kategorier
- COT-historikk med prisgraf (klikk på marked)

### 🔗 Korrelasjoner
- 20-dagers Pearson-korrelasjon mellom EUR/USD, XAU/USD, US100 og Brent

### 📋 Signal-logg
- Historikk over bot-utførte trades med resultat (win/loss/managed)

### 📅 Kalender
- Økonomisk kalender med high-impact hendelser

### 💹 Priser
- Live-priser med daglig og 20-dagers endring

---

## Råvare Intel (`metals-intel.html`)

### 🏠 Oversikt (standard)
Dashboard med 7 kort som lenker til under-fanene:
- Geo-Intel Kart, COMEX Lager, Intel Feed, Råvare COT, Avlings-analyse, Shipping, Olje & Gass

### 🗺️ Geo-Intel Kart
- **MapLibre GL v4** — WebGL-basert kart med CartoDB Dark Matter tiles
- 9 lag: shipping lanes, pipelines (aktiv/stiplet), infrastruktur, seismisk, landbruksregioner, chokepoints, gruver
- **26 gruver** (gull/sølv/kobber) med status, selskap, produksjon og risikoflagg
- **6 chokepoints** med HIGH/MEDIUM/LOW risiko-badge
- **Landbruksregioner** med Open-Meteo 7-dagers værvarsling ved klikk
- **Seismisk aktivitet** — USGS M≥4.5 nær gruveregioner

### 🏦 COMEX Lager
- Registrert vs. eligible lagerbeholdning for gull, sølv og kobber
- Stress-indeks per metall (0–100)

### 📰 Intel Feed
- Nyhetsstrøm fra Google News RSS (gull, sølv, kobber, geopolitikk)

### 📊 Råvare COT
- COT-posisjoner filtrert på råvarer og landbruk

### 🌾 Avlings-analyse
- **10 avlinger**: Mais, Hvete, Soyabønner, Canola, Bomull, Sukker, Kaffe, Kakao, Palmeolje, Ris
- **14 regioner** med Open-Meteo vær-scoring og COT-kombinasjon
- Prisretning: STERKT BULLISH → STERKT BEARISH

### 🚢 Shipping
- **Baltic-indekser**: BDI, BCI, BPI, BSI fra Stooq
- **8 ruter** scoret med keyword-basert disrupsjonsvarsling: trans-Pacific, Asia-Europa, Hormuz, Svartehavet, Panama, Sør-Amerika, Australia bulk, Malacca
- **Nyheter** fra 5 Google RSS-strømmer (container, tanker, bulk, chokepoints, havner)
- Overall risiko: HIGH / MEDIUM / LOW
- Datafil: `data/shipping/latest.json`

### ⛽ Olje & Gass
- **Priser og COT** for WTI, Brent, NatGas, RBOB, Heating Oil
- **Brent-WTI spread** beregnet løpende
- **8 segmenter** scoret: OPEC, US supply, Russland, Midtøsten, LNG, raffineri, etterspørsel, fornybar
- **Kombinert signal** per instrument: STERKT BULLISH → STERKT BEARISH (pris + COT)
- Datafil: `data/oilgas/latest.json`

---

## Krypto Intel (`crypto-intel.html`)

Designet for brukere uten kryptoerfaring — alt forklares på norsk i klartekst.

### 🏠 Oversikt (standard)
Dashboard med 4 kort som lenker til under-fanene:
- **Markedsbildet** — stemningsemoji, F&G score og BTC/ETH/SOL priser
- **Signaler** — om krypto følger aksjer eller er selvstendig, BTC-dominans
- **Store investorer** — COT retning og netto-posisjon prosent
- **Nyheter** — antall artikler og 3 siste overskrifter

### 💡 Markedsbildet
- Stemningsbanner (🟢 Optimistisk / 🟡 Usikkert / 🔴 Nervøst) med klarspråklig forklaring
- 3 signalkort: samlet markedsverdi, Bitcoin-dominans, Fear & Greed
- Prisoversikt: BTC, ETH, SOL, XRP, BNB, ADA, DOGE, AVAX
- BTC-dominans-bar og Fear & Greed gauge med historikk

### 🔍 Signaler
- 3 innsiktkort: "Henger krypto med aksjer?", "Er Bitcoin som gull?", "Kan altcoins gjøre det bedre?"
- Korrelasjon mot S&P 500 og gull forklart i dagligspråk

### 🏦 Store investorer
- Bitcoin COT fra CME futures
- Stort emoji-kort: "De store investorene: Kjøper aktivt / Selger / Nøytrale"
- Posisjonsbar og 8-ukers sparkline

### 📰 Nyheter
- Krypto-nyheter kategorisert: Bitcoin, Ethereum, Regulering, Makro, Altcoins

---

## Workflow — automatisk oppdatering (systemd timer)

To timers kjører på serveren:

**`cot-prices.timer`** — hvert hele time (XX:00)
Kjører `update_prices.sh`: henter bot-priser → bygger `macro/latest.json` → kjører `fetch_all.py` → git push

**`cot-explorer.timer`** — 6× daglig hverdager (00/04/08/12/16/20 CET)
Kjører `update.sh`: full pipeline (se tabell under)

`Persistent=true` sikrer at missede kjøringer kjøres automatisk ved oppstart.

> Kjør manuelt: `bash ~/cot-explorer/update.sh`
> Logg: `tail -f ~/cot-explorer/logs/update.log`
> Prislogg: `tail -f ~/cot-explorer/logs/prices.log`

### Hva update.sh gjør (i rekkefølge)

| # | Script | Beskrivelse |
|---|--------|-------------|
| 0 | git fetch/rebase | Synkroniser med GitHub |
| 1 | `fetch_calendar.py` | ForexFactory-kalender |
| 2 | `fetch_cot.py` | CFTC COT-data |
| 3 | `build_combined.py` | Kombinert COT-datasett |
| 4 | `fetch_ice_cot.py` | ICE Futures Europe COT (Brent, Gasoil, TTF) |
| 5 | `fetch_euronext_cot.py` | Euronext MiFID II COT (hvete, raps, mais) |
| 6 | `fetch_fundamentals.py` | FRED makrodata (maks 1× per 12t) |
| 7 | `fetch_all.py` | Full analyse: priser, SMC, nivåer, score, setups, VIX, korrelasjoner, ADR |
| 8 | `fetch_comex.py` | COMEX lagerbeholdning |
| 9 | `fetch_seismic.py` | USGS seismiske data |
| 10 | `fetch_intel.py` | Google News RSS for metaller |
| 11 | `fetch_agri.py` | Vær + COT for 10 avlinger / 14 regioner |
| 12 | `fetch_shipping.py` | Baltic-indekser + rute-scoring |
| 13 | `fetch_oilgas.py` | Energipriser + segment-scoring |
| 14 | `fetch_crypto.py` | Krypto-priser, Fear & Greed, COT, korrelasjoner |
| 15 | `push_signals.py` | Genererer `signals.json`, pusher varsler |
| 16 | git push | Oppdaterer GitHub Pages |

---

## Signal-varsling og trading bot

`push_signals.py` sender de beste tradingideene til Telegram, Discord og/eller Flask-server.

### Filtrering
- Score ≥ `PUSH_MIN_SCORE` (standard: **7** av 12)
- Kun klare retninger: `dir_color` er `bull` eller `bear`
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
| `PUSH_MIN_SCORE` | Minimum konfluens-score (standard: 7) |
| `PUSH_MAX_SIGNALS` | Maks antall signaler per kjøring (standard: 5) |
| `FLASK_URL` | URL til signal_server.py |
| `SCALP_API_KEY` | API-nøkkel til Flask `/push-alert` og `/push-prices` |
| `FRED_API_KEY` | FRED makrodata (**påkrevd** — sett i `~/.cot-env`) |
| `TWELVEDATA_API_KEY` | Forex + gull OHLC |
| `FINNHUB_API_KEY` | Sanntidspris for indekser/råvarer |

> Miljøvariabler lagres i `~/.cot-env` (chmod 600). `update.sh` sourcer denne filen automatisk slik at systemd-tjenesten får tilgang uten å laste `~/.bashrc`.

---

## Slik beregnes trading-ideer

### Konfluens-score (12 punkter)

| # | Kriterium |
|---|-----------|
| 1 | Over SMA200 (D1 trend) |
| 2 | Momentum 20d bekrefter retning |
| 3 | COT bekrefter retning |
| 4 | COT sterk posisjonering (>10% av OI) |
| 5 | Pris VED HTF-nivå nå |
| 6 | HTF-nivå D1/Ukentlig i nærheten (weight ≥ 3) |
| 7 | D1 + 4H trend kongruent (EMA9) |
| 8 | Ingen event-risiko (innen 4 timer) |
| 9 | Nyhetssentiment bekrefter retning |
| 10 | Fundamental (FRED) bekrefter retning |
| 11 | BOS 1H/4H bekrefter retning |
| 12 | SMC 1H markedsstruktur bekrefter retning |

**Grade:** A+ = 11-12p / A = 9-10p / B = 6-8p / C = 0-5p

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
| Landbruksvær | Open-Meteo API | Nei |
| COMEX lager | CME Group | Nei |
| Seismisk aktivitet | USGS Earthquake API | Nei |
| Baltic shipping-indekser | Stooq | Nei |
| Shipping-nyheter | Google News RSS | Nei |
| Krypto markedsdata | CoinGecko API | Nei |

---

## Datafiler

| Fil | Innhold | Oppdatering |
|-----|---------|-------------|
| Fil | Innhold | Oppdatering |
|-----|---------|-------------|
| `data/macro/latest.json` | Priser, SMC, nivåer, score, kalender | Hver time + 6× daglig |
| `data/signals.json` | Aktive signaler + global state | Hver time + 6× daglig |
| `data/combined/latest.json` | Kombinert CFTC COT-datasett | 6× daglig |
| `data/ice_cot/latest.json` | ICE Futures Europe COT (Brent, Gasoil, TTF) | 6× daglig |
| `data/ice_cot/history.json` | ICE COT 26-ukers historikk | 6× daglig |
| `data/euronext_cot/latest.json` | Euronext MiFID II COT (hvete, raps, mais) | 6× daglig |
| `data/euronext_cot/history.json` | Euronext COT 26-ukers historikk | 6× daglig |
| `data/signal_log.json` | Bot-trade historikk | Ved trade |
| `data/fundamentals/latest.json` | FRED makrodata | 2× daglig |
| `data/comex/latest.json` | COMEX lagerbeholdning + stress-indeks | 6× daglig |
| `data/agri/latest.json` | Avlings-analyse: vær, COT, signal | 6× daglig |
| `data/shipping/latest.json` | Baltic-indekser, rute-scoring, nyheter | 6× daglig |
| `data/oilgas/latest.json` | Energipriser, COT, segment-scoring | 6× daglig |
| `data/crypto/latest.json` | Krypto-priser, Fear & Greed, COT, korrelasjoner | 6× daglig |
| `data/geointel/seismic.json` | USGS seismiske hendelser | 6× daglig |
| `data/geointel/intel.json` | Google News RSS metallnyheter | 6× daglig |
| `data/geointel/shipping_lanes.json` | Globale shippingruter | Statisk |
| `data/geointel/pipelines.json` | Oljeledninger | Statisk |
| `data/geointel/chokepoints.json` | 6 chokepoints | Statisk |
| `data/geointel/mines.json` | 26 gruver | Statisk |
| `~/scalp_edge/live_prices.json` | Live priser fra bot (20 symboler) | Hvert 58. min |

---

## Tech stack

| Komponent | Teknologi |
|-----------|-----------|
| Frontend | Vanilla HTML/CSS/JS — `index.html`, `metals-intel.html`, `crypto-intel.html` |
| Navigasjon | To-nivås nav: `nav-main` (mellom dashboards) + `nav` (under-faner) |
| Tidssoner | `toNO()` helper konverterer UTC-timestamps til norsk tid (Europe/Oslo) i alle sider |
| Kart | MapLibre GL v4 med CartoDB Dark Matter tiles |
| Grafer | Chart.js (COT-historikk modal) |
| Backend | Python 3 + `requests` + `openpyxl` |
| Hosting | GitHub Pages (statisk) |
| Automatisering | `cot-prices.timer` (hvert hele time) + `cot-explorer.timer` (6× daglig) |
| Prisintegrasjon | `signal_server.py` Flask-server — `POST /push-prices`, `GET /prices` |
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
