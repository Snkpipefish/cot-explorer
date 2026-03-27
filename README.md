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
- **COT-posisjoner** for 366 markeder fra CFTC (siste uke)
- **COT-historikk** med prisgraf (klikk på marked i COT-fanen)
- **Fundamentals-panel** — FRED-data: GDP, CPI, PPI, PCE, NFP, jobbtall (USD-bias-score)
- **Nyhetssentiment** — RSS fra Google News + BBC, risk-on/risk-off-scoring
- **Makroindikatorer** — HYG, TIP, TNX (10Y), IRX (3M), Kobber, EEM
- **Økonomisk kalender** med binær risiko-varsling
- **Timeframe bias** — MAKRO / SWING / SCALP / WATCHLIST per instrument
- **COT momentum** — ØKER / SNUR / STABIL basert på ukeendring i netto-posisjon
- **Metals & Macro Intel** — Geo-Intel kart (mines/chokepoints/seismisk), COMEX lagerbeholdning, nyhetsstrøm

Alt drives av JSON-filer i `data/` som genereres lokalt og pushes til GitHub.

---

## Workflow — automatisk oppdatering (systemd timer)

Scriptet `update.sh` kjøres automatisk via systemd timer på hverdager (man–fre), hvert 4. time hele døgnet:

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

`Persistent=true` sikrer at missede kjøringer (f.eks. PC i dvale) kjøres automatisk når maskinen våkner.

> Kjør manuelt ved behov: `bash ~/cot-explorer/update.sh`

For å se logg: `tail -f ~/cot-explorer/logs/update.log`

### Hva update.sh gjør (i rekkefølge)

1. `fetch_calendar.py` — henter ForexFactory-kalender (binær risiko per instrument)
2. `fetch_cot.py` — henter CFTC COT-data
3. `build_combined.py` — bygger kombinert COT-datasett (legacy + TFF + disaggregated)
4. `fetch_fundamentals.py` — henter FRED makrodata (kun hvis > 12 timer siden sist)
5. `fetch_all.py` — full analyse: priser, SMC (15m/1H/4H), nivåer, score, setup-generering
6. `fetch_comex.py` — henter COMEX lagerbeholdning (gull/sølv/kobber) til `data/comex/latest.json`
7. `fetch_seismic.py` — henter USGS seismiske data for gruveregioner til `data/geointel/seismic.json`
8. `fetch_intel.py` — henter nyheter fra Google News RSS (gull, sølv, kobber, geopolitikk) til `data/geointel/intel.json`
9. `push_signals.py` — genererer alltid `data/signals.json`, pusher topp-setups til Telegram/Discord/Flask (valgfritt)
10. `git push` — oppdaterer GitHub Pages med nye JSON-filer

---

## Signal-varsling og trading bot (valgfritt)

`push_signals.py` sender de beste tradingideene til Telegram, Discord og/eller en lokal Flask-server etter hver analyse.

**Kjøres alltid** (ikke gated av env-variabler) og skriver alltid `data/signals.json` som pushes til GitHub Pages.

### Filtrering

- Kun setups med score ≥ `PUSH_MIN_SCORE` (standard: **7** av 12)
- Kun klare retninger: `dir_color` er `bull` eller `bear`
- Kun instrumenter med aktiv setup (entry/SL/T1 kalkulert) — watchlist-instrumenter ekskluderes
- Boten mottar **kun** riktig retnings-setup (ikke begge): LONG-entry hvis bull, SHORT-entry hvis bear
- Sortert: MAKRO > SWING > SCALP, deretter score

### Miljøvariabler

| Variabel | Beskrivelse |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot-token fra @BotFather |
| `TELEGRAM_CHAT_ID` | Chat-ID som skal motta meldinger |
| `DISCORD_WEBHOOK` | Discord webhook-URL |
| `PUSH_MIN_SCORE` | Minimum konfluens-score for å pushe (standard: **7**) |
| `PUSH_MAX_SIGNALS` | Maks antall signaler per kjøring (standard: 5) |
| `FLASK_URL` | URL til signal_server.py (standard: `http://localhost:5000`) |
| `SCALP_API_KEY` | API-nøkkel til Flask-endepunktet `/push-alert` |

Sett variablene i `~/.bashrc` eller `~/.profile`:
```bash
export TELEGRAM_TOKEN="din-token"
export TELEGRAM_CHAT_ID="din-chat-id"
export SCALP_API_KEY="din-api-nøkkel"
```

`SCALP_API_KEY` leses automatisk fra `~/.bashrc` som fallback hvis den ikke er satt i shell-miljøet.

### data/signals.json

Genereres ved **hver** kjøring og pushes til GitHub Pages. Kan leses av eksterne bots direkte fra GitHub.

```json
{
  "generated": "2026-03-27 12:00 UTC",
  "cot_date": "2026-03-21",
  "signals": [
    {
      "key": "gold",
      "name": "Gold",
      "action": "BUY",
      "timeframe": "MAKRO",
      "grade": "A+",
      "score": 11,
      "current": 3012.5,
      "entry": 2985.0,
      "sl": 2940.0,
      "t1": 3050.0,
      "t2": 3120.0,
      "rr_t1": 1.44,
      "rr_t2": 2.98,
      "sl_type": "structural",
      "cot_bias": "LONG",
      "cot_pct": 72.3
    }
  ]
}
```

### Flask /push-alert

`scalp_edge/signal_server.py` tilbyr et REST-endepunkt for trading bot-integrasjon.

```
POST http://localhost:5000/push-alert
Headers: X-API-Key: <SCALP_API_KEY>
         Content-Type: application/json

Body: {
  "generated": "2026-03-27 12:00 UTC",
  "signals": [
    {
      "key": "gold",
      "name": "Gold",
      "timeframe_bias": "MAKRO",
      "direction": "bull",
      "grade": "A+",
      "score": 11,
      "setup": { "entry": 2985.0, "sl": 2940.0, "t1": 3050.0, "t2": 3120.0,
                 "risk_atr_d": 0.9, "sl_type": "structural", "rr_t1": 1.44, "rr_t2": 2.98,
                 "t1_source": "D1" },
      "cot": { "bias": "LONG", "momentum": "ØKER", "pct": 72.3 }
    }
  ]
}
```

---

## Metals & Macro Intel (`metals-intel.html`)

Eget panel med tre faner:

### Geo-Intel (kart)
- Interaktivt Leaflet.js-kart med CartoDB Dark Matter tiles
- Viser **26 gruver** (gull/sølv/kobber) med status, selskap, produksjon og risikoflagg
- Viser **6 forsyningskjede-chokepoints** (Hormuz, Malacca, Suez, Bab-el-Mandeb, Panama, Kapp det gode håp)
- Viser **seismisk aktivitet** (USGS M≥4.5) nær gruveregioner, oppdatert ukentlig
- Klikk på markør for popup med detaljer

### COMEX Dashboard
- Registrert vs. eligible lagerbeholdning for gull, sølv og kobber
- Stress-indeks per metall (0–100): lav registered-dekning + synkende trend øker stress
- Oppdateres fra `data/comex/latest.json`

### Intel Feed
- Nyhetsstrøm fra Google News RSS (4 kategorier: gull, sølv, kobber, geopolitikk)
- Oppdateres fra `data/geointel/intel.json`

### Datafiler (Geo-Intel)

| Fil | Innhold | Oppdatering |
|-----|---------|-------------|
| `data/geointel/mines.json` | 26 gruver manuelt kuratert | Statisk |
| `data/geointel/chokepoints.json` | 6 chokepoints | Statisk |
| `data/geointel/seismic.json` | USGS seismiske hendelser | 6× daglig |
| `data/geointel/intel.json` | Google News RSS feed | 6× daglig |
| `data/comex/latest.json` | COMEX lagerbeholdning + stress-indeks | 6× daglig |

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
- SL = strukturell stop loss:
  - SMC supply/demand-sone: SL = zone_bottom/top ± 0.15×ATR(D1) buffer
  - Linjnivå: SL = nivå ± 0.3–0.5×ATR(D1)
- T1 = neste faktiske nivå med høyest HTF-weight (R:R ≥ 1.5 kreves)
  - Hvis ingen strukturell T1 finnes: T1 projiseres ved entry ± min_t1_dist, merket som `t1_quality: "weak"`
- T2 = neste nivå etter T1, eller T1 + 1×risk hvis ingen nivåer finnes
- T1 merkes som "weak" i frontend hvis kun svak 15m-kilde eller projisert

### SMC-analyse (smc.py)

Kjøres parallelt på tre tidshorisonter:

| Tidshorisont | Swing-lengde | Bruk |
|---|---|---|
| 15m | 5 bars | Lokal entry-presisjon, intradag soner |
| 1H | 10 bars | Institusjonell struktur (dager), BOS-bekreftelse |
| 4H | 5 bars | Swing-struktur (uker), overordnet retning |

Outputter: supply/demand soner, BOS-nivåer (opp/ned), swing high/low, markedsstruktur (BULLISH / BEARISH / MIXED).

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

### Timeframe bias

| Label | Kriterium | Typisk holdtid |
|-------|-----------|----------------|
| MAKRO | Score ≥ 6 + COT bekrefter + HTF-nivå | Dager til uker |
| SWING | Score ≥ 4 + HTF-nivå | Timer til dager |
| SCALP | Score ≥ 2 + pris ved nivå nå + aktiv sesjon | Minutter |
| WATCHLIST | Ikke klar ennå | — |

### VIX-regime og posisjonsstørrelse

| VIX | Posisjonsstørrelse |
|-----|--------------------|
| < 20 | Full |
| 20–30 | Halv |
| > 30 | Kvart |

---

## Instruments

| Key | Yahoo | COT-marked | Klasse | Sesjon |
|-----|-------|------------|--------|--------|
| EURUSD | EURUSD=X | euro fx | A | London 08:00–12:00 CET |
| USDJPY | JPY=X | japanese yen | A | London 08:00–12:00 CET |
| GBPUSD | GBPUSD=X | british pound | A | London 08:00–12:00 CET |
| AUDUSD | AUDUSD=X | — | A | London 08:00–12:00 CET |
| Gold | GC=F | gold | B | London Fix 10:30 / NY Fix 15:00 CET |
| Silver | SI=F | silver | B | London Fix 10:30 / NY Fix 15:00 CET |
| Brent | BZ=F | crude oil, light sweet | B | London Fix 10:30 / NY Fix 15:00 CET |
| WTI | CL=F | crude oil, light sweet | B | London Fix 10:30 / NY Fix 15:00 CET |
| SPX | ^GSPC | s&p 500 consolidated | C | NY Open 14:30–17:00 CET |
| NAS100 | ^NDX | nasdaq mini | C | NY Open 14:30–17:00 CET |
| DXY | DX-Y.NYB | usd index | A | London 08:00–12:00 CET |
| VIX | ^VIX | — | C | NY Open 14:30–17:00 CET |
| USDCHF | CHF=X | — | A | London 08:00–12:00 CET |
| USDNOK | NOK=X | — | A | London 08:00–12:00 CET |

VIX brukes kun for posisjonsstørrelse. USDCHF og USDNOK vises kun i priser-fanen — ingen COT/SMC-analyse.

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
| SMC supply/demand/BOS | Beregnet fra 15m, 1H, 4H | — | Ved kjøring |
| COMEX lager (gull/sølv/kobber) | CME Group → fallback | Nei | 6× daglig |
| Seismisk aktivitet | USGS Earthquake API | Nei | 6× daglig |
| Metals nyheter | Google News RSS | Nei | 6× daglig |

### Pris-fallback-kjede (per instrument)

```
Twelvedata (forex/gull, hvis API-nøkkel + gratis-symbol)
    → Stooq (daglig, alle symboler, ingen nøkkel)
        → Yahoo Finance (intradag + alt Stooq ikke dekker)

Finnhub: oppdaterer siste bar med sanntidspris (indekser, råvarer)
```

---

## Fundamentals (fetch_fundamentals.py)

Henter FRED-serier og beregner USD fundamental bias-score (−2 til +2 per indikator).

| Kategori | Indikatorer | Vekt |
|----------|-------------|------|
| Economic Growth | GDP QoQ, Retail Sales MoM, UoM Consumer Sentiment, mPMI, sPMI | 25% |
| Inflation | CPI YoY, PPI YoY, PCE YoY, Fed Funds Rate | 40% |
| Jobs Market | NFP, Arbeidsledighet, Initial Claims, ADP, JOLTS | 35% |

PMI hentes fra ForexFactory-kalenderen (ISM er ikke tilgjengelig på FRED).
Oppdateres maks én gang per 12 timer (FRED-data er månedlig/ukentlig).

---

## Makroindikatorer

Hentes av `fetch_all.py` ved hver kjøring:

| Indikator | Symbol | Kilde | Beskrivelse |
|-----------|--------|-------|-------------|
| TNX | DGS10 | FRED → Yahoo | 10-årig statsrente USA |
| IRX | DTB3 | FRED → Yahoo | 3-måneds T-bill |
| HYG | HYG | Twelvedata → Yahoo | High Yield Corp Bond ETF (kredittrisiko) |
| TIP | TIP | Twelvedata → Yahoo | TIPS Bond ETF (inflasjonsforventninger) |
| Copper | HG=F | Yahoo | Kobber — ledende vekstindikator |
| EEM | EEM | Twelvedata → Yahoo | Emerging Markets ETF (risikoappetitt) |

Yield curve (TNX − IRX) brukes i konflikt-detektor. HYG ned > 1.5% siste 5 dager = kredittpress (hy_stress).

---

## Tech stack

| Komponent | Teknologi |
|-----------|-----------|
| Frontend | Vanilla HTML/CSS/JS, `index.html` + `metals-intel.html` |
| Kart | Leaflet.js med CartoDB Dark Matter tiles |
| Backend | Python 3, ingen dependencies utover stdlib |
| Hosting | GitHub Pages (statisk) |
| Automatisering | systemd timer (6× daglig hvert 4. time, hverdager) |
| Varsling | Telegram bot / Discord webhook / Flask REST API (valgfritt) |
| SMC-motor | `smc.py` — Python-port av FluidTrades SMC Lite |
