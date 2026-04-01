# COT Explorer – Markedspuls

Live: https://snkpipefish.github.io/cot-explorer
Repo: https://github.com/Snkpipefish/cot-explorer

---

## Hva er dette?

En statisk nettside (GitHub Pages) som viser daglige trading-ideer basert på:

- **Level-til-level setups** — entry ved faktisk strukturnivå, T1/T2 er neste reelle nivå
- **Konfluens-score (12 punkter)** inkl. SMA200, momentum, COT, HTF-nivå, sesjon, BOS, SMC-struktur, nyheter, fundamentals
- **SMC-analyse på tre tidshorisonter** — 15m, 1H og 4H: supply/demand soner, BOS, HH/LH/HL/LL
- **Makro-panel** med Dollar Smile-modell, VIX-regime, yield curve og konflikt-flagging
- **VIX term-struktur** — spot vs. 9D vs. 3M, contango/backwardation-regime
- **Korrelasjonstabell** — 20-dagers Pearson-korrelasjon mellom EUR/USD, XAU/USD, US100 og Brent
- **COT-posisjoner** for 600+ markeder fra CFTC (siste uke) med 8-ukers sparkline, gruppert i accordion-kategorier
- **COT-historikk** med prisgraf (klikk på marked i COT-fanen)
- **Fundamentals-panel** — FRED-data: GDP, CPI, PPI, PCE, NFP, jobbtall (USD-bias-score)
- **Nyhetssentiment** — RSS fra Google News + BBC, risk-on/risk-off-scoring
- **Makroindikatorer** — HYG, TIP, TNX (10Y), IRX (3M), Kobber, EEM (alle inkl. chg20d)
- **Gjennomsnittlig daglig range (ADR)** — 20-dagers snitt per instrument
- **Økonomisk kalender** med binær risiko-varsling
- **Timeframe bias** — MAKRO / SWING / SCALP / WATCHLIST per instrument
- **Signal-logg** — historikk over bot-utførte trades med resultat (win/loss/managed)
- **Råvare Intel** — Geo-Intel kart (MapLibre GL), landbruksregioner med værvarsling, COMEX lager, nyhetsstrøm, Råvare COT, Avlings-analyse
- **Krypto Intel** — Priser, markedsdominans, Fear & Greed, Bitcoin COT, makrokorrelasjoner og nyheter

Alt drives av JSON-filer i `data/` som genereres lokalt og pushes til GitHub.

---

## Workflow — automatisk oppdatering (systemd timer)

Scriptet `update.sh` kjøres automatisk via systemd timer hvert 4. time hele døgnet:

| Tid (CET) |
|-----------|
| 00:00 |
| 04:00 |
| 08:00 |
| 12:00 |
| 16:00 |
| 20:00 |

Timer-oppsett: `/etc/systemd/system/cot-explorer.timer`
Service-oppsett: `/etc/systemd/system/cot-explorer.service`

`Persistent=true` sikrer at missede kjøringer (f.eks. server i dvale) kjøres automatisk når maskinen våkner.

> Kjør manuelt ved behov: `bash ~/cot-explorer/update.sh`

For å se logg: `tail -f ~/cot-explorer/logs/update.log`

### Hva update.sh gjør (i rekkefølge)

0. `git fetch origin main && git rebase origin/main` — synkroniserer med GitHub før kjøring for å unngå divergens ved push
1. `fetch_calendar.py` — henter ForexFactory-kalender (binær risiko per instrument)
2. `fetch_cot.py` — henter CFTC COT-data
3. `build_combined.py` — bygger kombinert COT-datasett (legacy + TFF + disaggregated)
4. `fetch_fundamentals.py` — henter FRED makrodata (kun hvis > 12 timer siden sist)
5. `fetch_all.py` — full analyse: priser, SMC (15m/1H/4H), nivåer, score, setup-generering, VIX term-struktur, korrelasjonmatrise, ADR
6. `fetch_comex.py` — henter COMEX lagerbeholdning (gull/sølv/kobber)
7. `fetch_seismic.py` — henter USGS seismiske data for gruveregioner
8. `fetch_intel.py` — henter nyheter fra Google News RSS (gull, sølv, kobber, geopolitikk)
9. `fetch_agri.py` — henter Open-Meteo værvarsling for 14 landbruksregioner, beregner tørkestress/flomrisiko, kombinerer med COT → `data/agri/latest.json`
10. `fetch_crypto.py` — henter krypto-priser, markedsdata, Fear & Greed, Bitcoin COT, korrelasjoner og nyheter
11. `push_signals.py` — genererer `data/signals.json`, oil war-spread sjekk, DXY-eksklusjon
11. `git push` — oppdaterer GitHub Pages med nye JSON-filer

`logs/update.log` er ikke tracket av git (lagt til `.gitignore`).

---

## Signal-varsling og trading bot

`push_signals.py` sender de beste tradingideene til Telegram, Discord og/eller en lokal Flask-server etter hver analyse.

### Filtrering

- Kun setups med score ≥ `PUSH_MIN_SCORE` (standard: **7** av 12)
- Kun klare retninger: `dir_color` er `bull` eller `bear`
- **DXY ekskludert** (ikke-tradeable indeks)
- **Oil war-spread beskyttelse**: hvis Brent +15% siste 20 dager ELLER krig/Iran-nøkkelord i nyheter → `oil_geo_warning=true` i `signals.json`. Boten øker minimum SL og krever bredere spread-kontroll for oljeinstrumenter.

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

### Signal-logg (bot → JSON)

`trading_bot.py` skriver direkte til `~/cot-explorer/data/signal_log.json` ved hver trade-hendelse:

- `_log_trade_opened(state)` — kalles i `_on_execution` etter ordrebekreftelse
- `_log_trade_closed(state, reason, close_price)` — kalles ved GEO-SPIKE, KILL, EMA9, 8-CANDLE
- `_git_push_log()` — kalles etter hver skriving, committer og pusher `signal_log.json` til GitHub umiddelbart

`push_signals.py` skriver **ikke** til `signal_log.json` — kun `trading_bot.py` gjør det. Signal-loggen viser kun bot-utførte trades, ikke auto-genererte signaler.

Kolonner i loggen: Åpnet, Instrument, Retning, Entry, SL, T1, Størrelse, Exit-grunn, Resultat.

### Miljøvariabler

| Variabel | Beskrivelse |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot-token fra @BotFather |
| `TELEGRAM_CHAT_ID` | Chat-ID som skal motta meldinger |
| `DISCORD_WEBHOOK` | Discord webhook-URL |
| `PUSH_MIN_SCORE` | Minimum konfluens-score (standard: **7**) |
| `PUSH_MAX_SIGNALS` | Maks antall signaler per kjøring (standard: 5) |
| `FLASK_URL` | URL til signal_server.py (standard: `http://localhost:5000`) |
| `SCALP_API_KEY` | API-nøkkel til Flask-endepunktet `/push-alert` |

---

## Råvare Intel (`metals-intel.html`)

Eget panel med fire faner:

### Geo-Intel Kart
- **MapLibre GL v4** — WebGL-basert kart med CartoDB Dark Matter tiles og smooth zoom
- 9 lag: shipping lanes, pipelines (aktiv/stiplet), infrastruktur, seismisk, landbruksregioner, chokepoints, gruver
- Hvert lag kan skrus av/på via checkbox-panel
- **26 gruver** (gull/sølv/kobber) med status, selskap, produksjon og risikoflagg
- **6 chokepoints** (Hormuz, Malacca, Suez, Bab-el-Mandeb, Panama, Kapp det gode håp)
- **Landbruksregioner** — klikk for popup med Open-Meteo 7-dagers værvarsling (temperatur, nedbør, vind) for kornbelte, Amazonas m.fl.
- **Seismisk aktivitet** — USGS M≥4.5 nær gruveregioner

### COMEX Dashboard
- Registrert vs. eligible lagerbeholdning for gull, sølv og kobber
- Stress-indeks per metall (0–100)

### Intel Feed
- Nyhetsstrøm fra Google News RSS (4 kategorier: gull, sølv, kobber, geopolitikk)

### Råvare COT
- COT-posisjoner filtrert på råvarer og landbruk fra `data/combined/latest.json`

### Avlings-analyse
- **10 avlinger**: Mais, Hvete, Soyabønner, Canola/Raps, Bomull, Sukker, Kaffe, Kakao, Palmeolje, Ris
- **14 regioner**: USA Corn Belt, Great Plains, Brazil Mato Grosso, Argentina Pampas, Ukraina, EU, Canada, Australia, India, Sørøst-Asia, Vest-Afrika, m.fl.
- **Vær-scoring**: tørke (< 8mm / > 25°C) → +2, flom (> 70mm) → +2, frost i plantetid → +2, normalt → 0
- **Sesongvekting**: kritisk sesong (planting/vekst) gir 1.5× vekting på vær-score
- **COT-score**: spekulant-netto som % av open interest + momentum → −2 til +2
- **Prisretning**: vær-score + COT-score → STERKT BULLISH / BULLISH / NØYTRAL / BEARISH / STERKT BEARISH
- Oppdateres fra `data/agri/latest.json` (6× daglig)

### Datafiler

| Fil | Innhold | Oppdatering |
|-----|---------|-------------|
| `data/geointel/shipping_lanes.json` | Globale shippingruter | Statisk |
| `data/geointel/pipelines.json` | Oljeledninger | Statisk |
| `data/geointel/infrastructure.json` | Terminals og raffineri | Statisk |
| `data/geointel/agri_regions.json` | Landbruksregioner med koordinater | Statisk |
| `data/geointel/chokepoints.json` | 6 chokepoints | Statisk |
| `data/geointel/mines.json` | 26 gruver | Statisk |
| `data/geointel/seismic.json` | USGS seismiske hendelser | 6× daglig |
| `data/geointel/intel.json` | Google News RSS feed | 6× daglig |
| `data/comex/latest.json` | COMEX lagerbeholdning + stress-indeks | 6× daglig |
| `data/agri/latest.json` | Avlings-analyse: vær, COT, prisretning per avling | 6× daglig |

---

## Slik beregnes trading-ideer

### Nivåhierarki (weight-skala)

| Weight | Nivå | Beskrivelse |
|--------|------|-------------|
| 5 | PWH / PWL | Forrige ukes høy/lav (sterkest) |
| 4 | PDH / PDL | Forrige dags høy/lav |
| 3 | D1 swing / PDC / SMC 1H | Daglige swing-nivåer, forrige close, SMC supply/demand 1H |
| 2 | 4H swing / SMC 4H | 4H swing-nivåer, SMC supply/demand 4H |
| 1 | 15m pivot / SMC 15m | Lokale intradag-nivåer (svakest) |

Nivåer innen 0.5×ATR av hverandre slås sammen — høyest weight beholder posisjonen.

### Level-til-Level setup (L2L)

- Entry = faktisk strukturnivå (MÅ være innen 0.3–1.0×ATR(D1) avhengig av weight)
- SL = strukturell stop loss (zone_bottom/top ± buffer, eller nivå ± 0.3–0.5×ATR)
- T1 = neste faktiske nivå med høyest HTF-weight (R:R ≥ 1.5 kreves)
- T2 = neste nivå etter T1, eller T1 + 1×risk

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

---

## Instruments

| Key | Stooq | COT-marked | Klasse | Sesjon |
|-----|-------|------------|--------|--------|
| EURUSD | eurusd | euro fx | A | London 08:00–12:00 CET |
| USDJPY | usdjpy | japanese yen | A | London 08:00–12:00 CET |
| GBPUSD | gbpusd | british pound | A | London 08:00–12:00 CET |
| AUDUSD | audusd | — | A | London 08:00–12:00 CET |
| Gold | xauusd | gold | B | London Fix 10:30 / NY Fix 15:00 CET |
| Silver | xagusd | silver | B | London Fix 10:30 / NY Fix 15:00 CET |
| Brent | co.f | crude oil, light sweet | B | London Fix 10:30 / NY Fix 15:00 CET |
| WTI | cl.f | crude oil, light sweet | B | London Fix 10:30 / NY Fix 15:00 CET |
| SPX | ^spx | s&p 500 consolidated | C | NY Open 14:30–17:00 CET |
| NAS100 | ^ndx | nasdaq mini | C | NY Open 14:30–17:00 CET |
| DXY | dxy.f | usd index | A | — (kun display, ikke tradeable) |
| VIX | ^vix | — | C | NY Open 14:30–17:00 CET |
| USDCHF | usdchf | — | A | London 08:00–12:00 CET |
| USDNOK | usdnok | — | A | London 08:00–12:00 CET |

VIX brukes kun for posisjonsstørrelse. DXY vises men ekskluderes fra trade-setups (ikke-tradeable indeks). USDCHF og USDNOK er kun priser (ingen COT/SMC-analyse).

---

## Datakilder

| Data | Kilde | API-nøkkel | Frekvens |
|------|-------|------------|----------|
| COT | CFTC.gov | Nei | Ukentlig fredag 21:30 CET |
| Daglige OHLC (primær) | Stooq | Nei | Ved kjøring |
| Intradag 15m / 1H | Yahoo Finance | Nei | Ved kjøring |
| Forex + gull OHLC | Twelvedata | Ja (`TWELVEDATA_API_KEY`) | Ved kjøring, maks 800/dag |
| Sanntidspris (indekser/råvarer) | Finnhub | Ja (`FINNHUB_API_KEY`) | Ved kjøring |
| Renter (10Y, 3M T-bill) | FRED | Nei | Ved kjøring |
| Fundamentals (GDP, CPI, NFP m.fl.) | FRED | Ja (`FRED_API_KEY`) | Maks 1× per 12 timer |
| Fear & Greed | CNN dataviz API | Nei | Ved kjøring |
| Nyhetssentiment | Google News RSS + BBC RSS | Nei | Ved kjøring |
| Kalender | ForexFactory JSON | Nei | Ved kjøring |
| Landbruksvær | Open-Meteo API | Nei | Ved klikk i kart |
| SMC supply/demand/BOS | Beregnet lokalt (smc.py) | — | Ved kjøring |
| Korrelasjoner + ADR | Beregnet fra daily-data | — | Ved kjøring |
| COMEX lager | CME Group → fallback | Nei | 6× daglig |
| Seismisk aktivitet | USGS Earthquake API | Nei | 6× daglig |
| Krypto-priser | Yahoo Finance | Nei | 6× daglig |
| Krypto markedsdata | CoinGecko API | Nei | 6× daglig |
| Krypto Fear & Greed | alternative.me | Nei | 6× daglig |

### Pris-fallback-kjede

```
Twelvedata (forex/gull, hvis API-nøkkel + gratis-symbol)
    → Stooq (daglig, alle symboler, ingen nøkkel)
        → Yahoo Finance (intradag + alt Stooq ikke dekker)

Finnhub: oppdaterer siste bar med sanntidspris (indekser, råvarer)
```

**NB:** Når intradag 15m-pris brukes som `curr`, sammenlignes den mot siste daglige Stooq-close (`daily[-1]`) — ikke `daily[-2]`. Dette sikrer at `chg1d` viser endring fra gårsdagens slutt, ikke to dager tilbake.

---

## Tech stack

| Komponent | Teknologi |
|-----------|-----------|
| Frontend | Vanilla HTML/CSS/JS, `index.html` + `metals-intel.html` + `crypto-intel.html` |
| Kart | MapLibre GL v4 med CartoDB Dark Matter tiles (WebGL, smooth zoom) |
| Grafer | Chart.js (COT-historikk modal) |
| Backend | Python 3, ingen dependencies utover stdlib |
| Hosting | GitHub Pages (statisk) |
| Automatisering | systemd timer (6× daglig hvert 4. time) |
| Varsling | Telegram bot / Discord webhook / Flask REST API (valgfritt) |
| Trading bot | `scalp_edge/trading_bot.py` — cTrader Open API (Python/Linux) |
| SMC-motor | `smc.py` — Python-port av FluidTrades SMC Lite |
