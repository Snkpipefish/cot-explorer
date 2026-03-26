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
6. `push_signals.py` — pusher topp-setups til Telegram/Discord/Flask (valgfritt)
7. `git push` — oppdaterer GitHub Pages med nye JSON-filer

---

## Signal-varsling og trading bot (valgfritt)

`push_signals.py` sender de beste tradingideene til Telegram, Discord og/eller en lokal Flask-server etter hver analyse.

### Miljøvariabler

| Variabel | Beskrivelse |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot-token fra @BotFather |
| `TELEGRAM_CHAT_ID` | Chat-ID som skal motta meldinger |
| `DISCORD_WEBHOOK` | Discord webhook-URL |
| `PUSH_MIN_SCORE` | Minimum konfluens-score for å pushe (standard: 5) |
| `PUSH_MAX_SIGNALS` | Maks antall signaler per kjøring (standard: 5) |
| `FLASK_URL` | URL til signal_server.py (standard: `http://localhost:5000`) |
| `SCALP_API_KEY` | API-nøkkel til Flask-endepunktet `/push-alert` |

Sett variablene i `~/.bashrc` eller `~/.profile`:
```bash
export TELEGRAM_TOKEN="din-token"
export TELEGRAM_CHAT_ID="din-chat-id"
export SCALP_API_KEY="din-api-nøkkel"
```

### Flask /push-alert

`scalp_edge/signal_server.py` tilbyr et REST-endepunkt for trading bot-integrasjon.

```
POST http://localhost:5000/push-alert
Headers: X-API-Key: <SCALP_API_KEY>
         Content-Type: application/json

Body: {
  "generated": "2026-03-25 12:00 UTC",
  "signals": [
    {
      "key": "eurusd",
      "name": "EUR/USD",
      "timeframe_bias": "SWING",
      "direction": "bull",
      "grade": "A",
      "score": 8,
      "setup": { "entry": 1.1617, "sl": 1.1480, "t1": 1.1780, "t2": 1.1920,
                 "risk_atr_d": 1.2, "sl_type": "zone", "rr_t1": 1.19, "rr_t2": 2.21,
                 "t1_source": "D1" },
      "cot": { "bias": "LONG", "momentum": "ØKER", "pct": 68.4 }
    }
  ]
}
```

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

- Entry = faktisk strukturnivå (MÅ være innen 0.3–0.45×ATR(15m) avhengig av weight)
- SL = strukturell stop loss:
  - SMC supply/demand-sone: SL = zone_bottom/top ± 0.15×ATR(D1) buffer
  - Linjnivå: SL = nivå ± 0.3–0.5×ATR(D1)
- T1 = neste faktiske nivå med høyest HTF-weight (R:R ≥ 1.5 kreves)
- T2 = neste nivå etter T1, eller T1 + 1×risk hvis ingen nivåer finnes
- T1 merkes som "weak" i frontend hvis kun svak 15m-kilde

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
| Frontend | Vanilla HTML/CSS/JS, én fil (`index.html`) |
| Backend | Python 3, ingen dependencies utover stdlib |
| Hosting | GitHub Pages (statisk) |
| Automatisering | systemd timer (6× daglig hvert 4. time, hverdager) |
| Varsling | Telegram bot / Discord webhook / Flask REST API (valgfritt) |
| SMC-motor | `smc.py` — Python-port av FluidTrades SMC Lite |
