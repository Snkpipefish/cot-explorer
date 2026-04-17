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
Kjører `update_prices.sh`: henter bot-priser → patcher JSON → `rescore.py` (full driver-matrix re-evaluering med ferske priser, schema 2.0) → trade-log sync → git push. *Ikke push av nye signaler — det skjer kun i `update.sh`.*

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

### Hva update_prices.sh gjør (i rekkefølge — hver time)

| # | Steg | Beskrivelse |
|---|------|-------------|
| 1 | `fetch_prices.py` | Bygger `data/macro/latest.json` fra bot-priser + Yahoo-fallback. Bevarer `trading_levels`, `calendar`, `cot_date`, `macro_indicators` fra forrige kjøring. |
| 2 | `fetch_oilgas.py` | Oppdaterer `data/oilgas/latest.json` med bot-priser + segment-scoring + nyheter |
| 3 | Inline agri-patch | Oppdaterer `data/agri/latest.json` med bot-priser (Corn, Wheat, Soy, Coffee, Cotton, Sugar, Cocoa) |
| 4 | Inline crypto-patch | Oppdaterer `data/crypto/latest.json` med bot-priser |
| 5 | `rescore.py` | Full driver_matrix re-evaluering med ferske priser (schema 2.0). Rekalkulerer dir_color, TREND-signaler, MACRO-regime + per-asset POSITIONING fra cot_analytics-cache. Gjenbruker COT/fundamentals/SMC fra fetch_all (data som ikke endrer seg intratime). |
| 6 | Sync trade-log | Kopierer `~/scalp_edge/signal_log.json` → `data/signal_log.json` hvis endret |
| 7 | git add+commit+push | `git add -u data/` fanger alle modifiserte filer + flock-vern mot bot-push |

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
| 7 | `fetch_all.py` | Full analyse: priser, SMC, nivåer, 6-familie driver matrix-scoring (`max_score` = sum av faktiske horisont-vekter: SCALP=4.2, SWING=5.0, MAKRO=5.2), setups, VIX, korrelasjoner, ADR. Bygger `data/cot_analytics/latest.json` via `cot_analytics.py` ved ny COT-date (~35 s), ellers cache-hit |
| 8 | `fetch_comex.py` | COMEX lagerbeholdning |
| 9 | `fetch_seismic.py` | USGS seismiske data |
| 10 | `fetch_intel.py` | Google News RSS for metaller |
| 11 | `fetch_agri.py` | Vær + COT for 10 avlinger / 14 regioner |
| 12 | `fetch_shipping.py` | Baltic-indekser + rute-scoring |
| 13 | `fetch_oilgas.py` | Energipriser + segment-scoring |
| 14 | `fetch_crypto.py` | Krypto-priser, Fear & Greed, COT, korrelasjoner |
| 15 | `fetch_conab.py` | Conab avlingsestimater Brasil (grains + café) — stale-gate 20 t |
| 16 | `fetch_unica.py` | UNICA halvmånedlig sukkerrør-crush + mix — stale-gate 12 t |
| 17 | `push_signals.py` | Genererer `signals.json` (tekniske + agri merget), pusher alt via `/push-alert` |
| 18 | `push_agri_signals.py` | Genererer `agri_signals.json` (leser Conab + UNICA for shock-drivere) |
| 19 | git push | Oppdaterer GitHub Pages |

---

## Signal-varsling og trading bot

`push_signals.py` sender de beste tradingideene til Telegram, Discord og Flask-server via én `/push-alert` endpoint. Tekniske og agri-signaler merges inn i samme `signals.json` og samme Flask-push. Agri-signaler merkes med `source: "agri_fundamental"` slik at boten kan rekalibrere entry/SL/T1 med live ATR. Agri-signaler pushes til Flask uavhengig av om det finnes tekniske signaler i samme kjøring (Telegram/Discord-meldingen hopper over når kun agri er tilstede). Begge typer signaler dropper ut hvis live pris har vandret > N×ATR fra entry (SCALP 1.5, SWING 2.5, MAKRO 4.0).

`push_agri_signals.py` genererer fundamentale agri-setups basert på outlook (vær + COT + yield + ENSO) og skriver til `agri_signals.json`. Ingen separat Flask-push — `push_signals.py` merger dette inn. Agri-signaler propagerer `data_quality` (`fresh`/`degraded`/`stale`) basert på Conab/UNICA-staleness; en avling som scorer A med manglende Conab-data flagges som `degraded` med `quality_notes` slik at brukeren ser hvilken kilde som mangler.

**Scoring-arkitektur (schema 2.0 — 6-familie driver matrix):**
- `driver_matrix.py` — 6-familie scoring (TREND, POSITIONING, MACRO, FUNDAMENTAL, RISK/EVENT, STRUCTURE) med confluens-gate som fikser C1 korrelasjons-bias
- `driver_group_mapping.py` — asset-klasse-routing (FX/metaller/energi/indekser/grains/softs/crypto → riktig data per familie)
- `cot_analytics.py` — disaggregerte COT sub-signaler (MM-percentile 52w, MM-Commercial divergens-z, OI-regime, Index Investor-flow) med cache i `data/cot_analytics/latest.json`
- `scoring_config.py` — delte konstanter: PUSH_THRESHOLDS, HORIZON_CONFIGS, DXY_MOMENTUM_THRESHOLD, CORRELATION_REGIME_CONFIGS, korrelasjons-grupper. **Inneholder ikke lenger scoring-logikk** — alt det er flyttet til `driver_matrix.py`.

Både `fetch_all.py` (hver 4. time) og `rescore.py` (hver time via update_prices.sh) bruker `driver_matrix.score_asset()` som **eneste scoring-motor**. Legacy 9-kriterie-systemet er fullstendig fjernet (commit 349a2b7) — én konsistent scoring-skala (0-6) på tvers av hele pipelinen.

### Filtrering
- Horisont-basert: score ≥ terskel for instrumentets horisont (SCALP 1.5 / SWING 2.5 / MAKRO 3.5 — 0-6 skala fra driver matrix)
- WATCHLIST pushes aldri — kun synlig på dashboardet
- Kun klare retninger: `dir_color` er `bull` eller `bear`
- Sortert etter horisont-prioritet (MAKRO > SWING > SCALP), deretter score
- **DXY ekskludert** (ikke-tradeable indeks)
- **Oil war-spread beskyttelse**: Brent +15% 20d ELLER krig-nøkkelord → `oil_geo_warning=true`
- **Olje supply-disruption**: Når Hormuz/Midtøsten har HIGH risk i shipping/oilgas-data → olje SHORT blokkeres automatisk, dir_color tvinges bull

### Flask-payload til /push-alert

```json
{
  "schema_version": "2.0",
  "generated": "2026-04-17 16:00 UTC",
  "global_state": {
    "geo_active": true,
    "vix_regime": "elevated",
    "correlation_regime": "normal",
    "correlation_config": {...}
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
      "data_quality": "fresh",
      "quality_notes": [],
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

- `schema_version` — schema 2.0 inkluderer `driver_groups` per signal. Bot validerer; ukjent versjon gir WARN (ikke block). Signal-server sjekker at alle `driver_groups.*.score` ∈ [0, 1].
- `vix_regime` — string enum `{normal, elevated, extreme}`.
- `created_at` — per-signal TTL-sjekk i bot (SCALP 15min / SWING 4t / MAKRO 24t).

### signals.json (GitHub Pages)

Samme skjema som over, pluss alle score-detaljer og SMC-analyse per instrument. Leses av dashbordet.

### Outbox ved feilet Flask-push

Hvis `/push-alert` feiler (nettverk, 5xx), lagres payload i `data/outbox/push-YYYYMMDD-HHMMSS.json`. Neste `push_signals.py`-kjøring tømmer outboxen først. 4xx-responser beholdes i 24t for debugging, deretter droppes. `data/outbox/` er gitignored.

### Signal-logg

`trading_bot.py` (scalp_edge) skriver trade-hendelser til `~/scalp_edge/signal_log.json` (lokalt på bot-host). `update.sh` (hver 4t) og `update_prices.sh` (hver time) kopierer fila inn i `data/signal_log.json` før sin egen git-push. Bot gjør ingen git-operasjoner i reactor-loopen (K5). `push_signals.py` skriver ikke til loggen.

### Miljøvariabler

| Variabel | Beskrivelse |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot-token fra @BotFather |
| `TELEGRAM_CHAT_ID` | Chat-ID som skal motta meldinger |
| `DISCORD_WEBHOOK` | Discord webhook-URL |
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

### 6-familie driver matrix (schema 2.0)

Scoring skjer i `driver_matrix.score_asset()` som aggregerer 6 uavhengige driver-familier. **C1-prinsippet**: grade krever confluens på tvers av uavhengige datakildefamilier, ikke flere signaler fra samme kilde.

| # | Familie | Datakilder | Kommentar |
|---|---|---|---|
| 1 | **TREND** | SMA200, 20d momentum, D1+4H EMA9 kongruens | Teknisk trend, composite 0-1 |
| 2 | **POSITIONING** | COT (CFTC/ICE/TFF), Managed Money-percentile 52w, MM-Commercial divergens-z, OI-regime, Index Investor-flow | Se dedikert seksjon under |
| 3 | **MACRO** | DXY chg5d, VIX-regime, real yields (DFII10), yield curve (DGS10-DGS2), Fear & Greed | Global regime — asset-class-agnostisk |
| 4 | **FUNDAMENTAL** | Asset-spesifikk: COMEX (metaller), shipping+oilgas (energi), Conab (grains), UNICA (softs), FRED instrument-score (FX/indekser) | Kilde per asset-klasse |
| 5 | **RISK/EVENT** | USDA blackout, geo-risk, kalender-events, VIX-spike | NON_SCORING — brukes kun som grade-gate |
| 6 | **STRUCTURE** | HTF-nivå-vekt, SMC-sone-bekreftelse, BOS, fibo-zone | Teknisk struktur |

Hver familie returnerer 0-1 score. Weighted total per horisont: SCALP max=4.2, SWING max=5.0, MAKRO max=5.2.

### POSITIONING sub-signaler (cot_analytics.py)

POSITIONING-familien utnytter disaggregerte CFTC-rapporter + ICE COT. Sub-signaler beregnes én gang per COT-release (fredag) og cachres i `data/cot_analytics/latest.json`.

| Sub-signal | Kilde | Aktivering |
|---|---|---|
| COT bias align | disaggregated/TFF spekulanter.net / OI | LONG/SHORT bias matcher dir_color (±4 % terskel) |
| COT momentum | `change_spec_net` | Uke-endring i retning |
| MM-percentile 52w | rolling rank fra `data/history/<report>/YYYY.json` | bull + pctile ≤ 10 → contrarian-bull 1.0; bear + pctile ≥ 90 → contrarian-bear 1.0 |
| MM-Commercial divergens-z | (MM_net − Commercial_net) median/MAD z-score | bear + z ≥ 1.5 → topp-signal; bull + z ≤ -1.5 → bunn-signal |
| OI-regime | 4w-snitt av change_oi vs retning | stigende OI i retning = confirmation (+0.5); mot retning = warning (−0.3) |
| Index Investor-bias | supplemental `indeksfond.net / OI` | Kun agri: > 5 % net = structural_long/short (+0.3) |

**Asset → rapport-mapping:**
- FX (EURUSD, GBPUSD, USDJPY, AUDUSD) → TFF (Leveraged Funds)
- Metaller, energi, indekser → disaggregated (Managed Money)
- Grains/softs → disaggregated + supplemental (Index Investor-flow)
- Brent → ICE Brent Crude + CFTC Crude Oil (OI-vektet)

**Graceful degradation:** < 26 ukers historikk → sub-signal returnerer None og teller ikke. Fallback til legacy `cot_pct/25`-styrke hvis MM-percentile mangler.

### Retningsbestemmelse (dir_color) — i `fetch_all.py`

Sammensatt score bestemmer bull/bear-retning per instrument **før** driver-matrisen scorer styrken:

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

`driver_matrix.determine_horizon()` velger høyeste horisont hvor både score- og familie-krav er møtt:

| Horisont | Min unweighted score | Min aktive familier | Tilleggskrav |
|----------|---------------------|--------------------|--------------|
| MAKRO | ≥ 3.5 | 4 | fundamental + macro ≥ 0.7 |
| SWING | ≥ 2.5 | 3 | — |
| SCALP | ≥ 1.5 | 2 | London/NY-sesjon |
| WATCHLIST | under dette | — | — |

SCALP utenfor optimal sesjon → WATCHLIST automatisk.

### Grade per horisont (prosent-basert)

Grade-terskler uttrykt som prosent av max-score per horisont — A i SCALP = A i SWING = A i MAKRO i relativ edge:

| Grade | Min % av max | Min aktive familier |
|-------|-------------|---------------------|
| A+ | 75 % | 4 |
| A | 55 % | 3 |
| B | 35 % | 2 |
| C | under dette | — |

Konkret per horisont: A+ krever score ≥ 3.15 (SCALP) / ≥ 3.75 (SWING) / ≥ 3.9 (MAKRO).

C1-fiksen bevares: POSITIONING alene med alle 7 sub-signaler på maks gir fortsatt grade=C. Kan ikke nå A uten 3+ uavhengige familier.

### Staleness-gate (data_quality)

`GroupResult` inkluderer felt `data_quality` ∈ {fresh, degraded, stale} basert på `_fallback`-flagg og `_age_hours` på kritiske inputs (DFII10, term_spread, COT-alder):

| data_quality | Grade-cap | Trigger |
|---|---|---|
| fresh | ingen | alle kritiske inputs < TTL |
| degraded | max A (ikke A+) | én kritisk input arvet fra cache (`_fallback=True`) |
| stale | max B | COT > 20d gammel, eller input > 7d cache-stale |

`_risk_gate_grade` tar både event-risk og data_quality inn — strengeste cap vinner.

### Score-justeringer (etter familie-score)

| Justering | Effekt | Når |
|-----------|---------|-----|
| DXY-konflikt | -0.5 til -2.0 (graduert) | USD-par med retning motstridende DXY. Penalty = base × clamp(\|DXY chg5d\| / 2.0%, 0.25, 1.0) |
| Signal-flip | Nedgradering 1 nivå | Retning eller horisont endret siden forrige kjøring |
| USDA blackout | Max A (ikke A+) | Innen ±3h av Crop Progress / Export Sales for agri |
| VIX ekstrem + event | Max B | risk_factors ≥ 5 |

### Push-terskler (til boten)

| Horisont | Min score (0-6 skala) |
|----------|----------------------|
| SCALP | 1.5 |
| SWING | 2.5 |
| MAKRO | 3.5 |
| WATCHLIST | Pushes aldri |

(Legacy 9-kriterie-systemet brukte 3.0/4.5/5.5 på 0-9 skala — fullstendig fjernet i schema 2.0. Driver-matrix er eneste scoring-motor.)

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

2% av kontoverdi, med 500 NOK som gulv via `max()` (H6). State persisteres til `~/scalp_edge/daily_loss_state.json` slik at bot-restart ikke nullstiller dagens tap. Tidlig-gate i `_process_watchlist_signal` dropper signaler før confirmation-layer når grensen er passert.

### Geo R:R minimum

Under geo-events: min R:R = 1.5 (senket fra 2.0). Per-horizon minimum gjelder fortsatt (SCALP 1.0, SWING 1.3, MAKRO 1.5).

### Kontrakt-rollover (H10)

Futures-baserte CFDer får `close_before_rollover=true` i signalet: GOLD, SILVER, OIL BRENT, OIL WTI, Corn, Wheat, Soybean, Sugar, Coffee, Cocoa, Cotton. Boten blokkerer nye entries de siste 3 kalenderdagene av måneden for å unngå prishopp ved broker-rull. Eksisterende posisjoner fortsetter under normal SL/trail-logikk.

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
| Brasil avlingsestimater (grains + café) | Conab gov.br PDF | Nei |
| Brasil sukkerrør-crush + mix (sugar/etanol) | UNICA unicadata.com.br PDF | Nei |
| COMEX lager | CME Group | Nei |
| Seismisk aktivitet | USGS Earthquake API | Nei |
| Baltic shipping-indekser | Stooq | Nei |
| Shipping-nyheter | Google News RSS | Nei |
| Krypto markedsdata | CoinGecko API | Nei |

---

## Datafiler

| Fil | Innhold | Oppdatering |
|-----|---------|-------------|
| `data/macro/latest.json` | Priser, SMC, nivåer, driver-familie-scores, grade, horisont, data_quality | Hver time + 6× daglig |
| `data/macro/signal_stability.json` | Forrige kjørings horisont/retning/score per instrument | 6× daglig |
| `data/prices/bot_history.json` | Rullerende prishistorikk (500 entries/symbol) for chg1d/5d/20d + GS-ratio-z-beregning | Hver time |
| `data/signals.json` | Aktive signaler (tekniske + agri merget) + global state + horizon_config | 6× daglig + hver time (SCALP) |
| `data/agri_signals.json` | Agri-fundamentale trading-setups (leses av push_signals.py for merge) | 6× daglig |
| `data/combined/latest.json` | Kombinert CFTC COT-datasett | 6× daglig |
| `data/ice_cot/latest.json` | ICE Futures Europe COT (Brent, Gasoil, TTF) | 6× daglig |
| `data/ice_cot/history.json` | ICE COT 26-ukers historikk | 6× daglig |
| `data/euronext_cot/latest.json` | Euronext MiFID II COT (hvete, raps, mais) | 6× daglig |
| `data/euronext_cot/history.json` | Euronext COT 26-ukers historikk | 6× daglig |
| `data/disaggregated/` + `data/tff/` + `data/supplemental/` + `data/legacy/` | Ukentlige CFTC COT-rapporter (Managed Money, Hedge Funds, Index Investors) | Ukentlig (fredager) |
| `data/history/<report_type>/YYYY.json` | 16 års CFTC-arkiv (2010-2025) — grunnlag for MM-percentile 52w + divergens-z | Statisk |
| `data/cot_analytics/latest.json` | Per-asset analytics-cache: MM-percentile, MM-Comm-z, OI-regime, Index Investor-bias | Ukentlig (rekomputeres ved ny COT-date) |
| `data/signal_log.json` | Bot-trade historikk | Ved trade |
| `data/fundamentals/latest.json` | FRED makrodata + market_rates (DGS10, DGS2, DFII10, term_spread) med `_fallback` / `_age_hours` / `_fresh` staleness-metadata | 2× daglig |
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
| `scoring_config.py` | Delte konstanter: PUSH_THRESHOLDS, HORIZON_CONFIGS, DXY_MOMENTUM_THRESHOLD, CORRELATION_REGIME_CONFIGS. (Legacy 9-kriterie-scoring fjernet — driver_matrix er eneste scoring-motor.) | — |
| `utils.py` | Delt verktøybibliotek (logging, retry, stooq, news, freshness) | — |
| `logs/` | Python-loggfiler per script | Ved kjøring |

---

## Kjente begrensninger / gotchas

- `data/euronext_cot/` opprettes kun etter at `fetch_euronext_cot.py` har kjørt (onsdag). `git add data/` (ikke `-u`) brukes for å fange nye filer.
- `update.sh` bruker `flock` for å unngå samtidig kjøring med bot-push. Lock-fil: `.git/bot_push.lock`.
- `trading_bot.py` gjør IKKE lenger git-operasjoner i hot-path (K5). Bot skriver `signal_log.json` lokalt i `~/scalp_edge/`, og `update.sh` / `update_prices.sh` kopierer fila inn før sin egen git-push.
- Alle Flask-endepunkter krever nå `X-API-Key` (K1) — også `/signals`, `/kill`, `/prices`. Unntak: `/health` er åpen for uptime-sjekker.
- `fetch_agri.py` og `fetch_oilgas.py` bruker `(x.get("cot") or {})` i stedet for `.get("cot", {})` for å håndtere `cot: null` i COT-data.
- `utils.fetch_url` har per-host circuit-breaker (M6): 3 strake feil på en kilde åpner kretsen i 5 min — forhindrer at én død RSS/API-endepunkt bremser hele pipelinen.
- `fetch_all.py` har assert som sikrer at DXY iterer først (H8) — dxy_conflict-beregningen avhenger av at DXY-direction er satt før USD-parene passeres.
- GitHub Pages har aggressiv caching — bruk Ctrl+Shift+R etter push for å se endringer umiddelbart.
- Mapbox-kart i råvare-tabene er satt til `interactive: false` (ikke zoombare) med Mercator-projeksjon og utvidet høyde (650px) for å vise polområder.
- COT momentum bruker `change_spec_net` fra ukentlige COT-rapporter (`data/tff/`, `data/disaggregated/`), ikke timeseries-filer (som er utdaterte).
- Agri-signaler bruker Yahoo Finance som fallback når bot-priser mangler (`bot_history.json`).
- `fetch_fundamentals.py` cache-fallback: hvis FRED returnerer 5xx på DGS2/DGS10/DFII10, arves verdien fra forrige run og merkes `_fallback=True`. Scoring-laget ser dette via `_meta_*`-felt og kapper grade til A (ikke A+) for å signalisere degraded data.
- `cot_analytics.build_cache()` tar ~35 s engangs per uke — leser 16 års arkiv fra `data/history/`. Cache-hit i alle andre kjøringer er ~0 ms.
- Staleness-gate: COT > 20 d → `data_quality="stale"` → grade max B. COT > 10 d → `degraded` → max A.

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

`/push-prices` avviser NaN, negative verdier og urealistisk høye priser (>10M). Ugyldig data logges med advarsel. `live_prices.json` skrives atomisk via temp-fil + `os.replace()` (M9) slik at samtidige lesere ikke får trunkert JSON.

### Signal Server / Trading Bot (scalp_edge) — forsvarslag

| Mekanisme | Hensikt | Lokasjon |
|-----------|---------|----------|
| X-API-Key på read-endpoints (K1) | Holder posisjonsinfo ute av uautoriserte lokale prosesser | `signal_server.py` |
| Per-signal TTL (K2) | SCALP 15min / SWING 4t / MAKRO 24t stale-drop i bot | `trading_bot.py` |
| Reconcile leser broker-TP (K3) | Gjenopprettede posisjoner får full T1/BE/trail-flyt | `trading_bot.py` |
| Auth-FATAL + reconnect-storm (K4) | Bot FATAL-exiter i stedet for evig loop ved token-død | `trading_bot.py` |
| VIX-enum harmonisert (K6) | `{normal, elevated, extreme}` på tvers av alle komponenter | alle |
| INSTRUMENT_MAP-validering (K7) | WARN/FATAL ved broker-rename eller delisting | `trading_bot.py` |
| Signal-fetch retry (H3) | 3 forsøk, 1s/3s backoff, eskalerende log | `trading_bot.py` |
| Spread-cold-start-vern (H4) | Ingen entry før ≥10 spread-samples innsamlet | `trading_bot.py` |
| Per-symbol silence-detektor (H5) | WARN hvis ett symbol stille mens andre strømmer | `trading_bot.py` |
| Daily-loss persist + tidlig-gate (H6) | Overlever bot-restart; skipper confirmation når passert | `trading_bot.py` |
| Rotating log handlers (L3) | Bot 50MB tak, server 25MB tak | begge |
| Confirmation-stats (M7) | Empirisk kalibrering av `min_score` via JSON-fil | `trading_bot.py` |
| `/health` (L5) | 200 ved ferske signaler, 503 hvis >25t | `signal_server.py` |
| Partial-fill-håndtering (M1) | Bruker `deal.filledVolume` ved mismatch | `trading_bot.py` |
| Adaptiv poll (H1) | 20s når SCALP aktiv, 60s ellers | `trading_bot.py` |

### Auto-refresh dashboard

Alle tre dashboards (`index.html`, `metals-intel.html`, `crypto-intel.html`) poller hvert 60. sekund og oppdaterer kun ved ny data.

### Frontend-optimalisering

`index.html` laster alle 5 JSON-filer parallelt med `Promise.all()` i stedet for sekvensielt — ~2-3× raskere initial lasting.

### Schema 2.0-visualisering på dashboardet

Setups & Trades-taben (og Topp signaler-kortene på Oversikt) viser per instrument:

- **Grade-badge** (A+/A/B/C) + **score-brøk** (f.eks. "A 2.77/5.0")
- **Data-quality-badge** ●Fresh / ●Degraded / ●Stale ved siden av grade — viser om scoring bygger på ferske eller arvet/stale data. Tooltip viser konkrete `quality_notes`.
- **Driver-familier-seksjon** (per setup-kort, åpent): 6 horisontale barer (TREND / POSITIONING / MACRO / FUNDAMENTAL / STRUCTURE / RISK/EVENT) med score 0-1, fargekodet (grønn ≥ 0.7, gul ≥ 0.3, svak ellers, inaktiv ved 0). Topp 3 driver-strenger per familie vises i klartekst under baren.
- **"N aktive av 5"** confluens-teller i header
- **Mini driver-indikator** på Topp signaler-kortene: 6 små fargede bokstaver (T·P·M·F·S·R) med tooltip per familie

Driver-strenger fra `driver_matrix` oversettes via `translateDriver()`-funksjon i `index.html` til klarspråk norsk. Eksempler:
- `MM percentile 5 (bunn — contra-bull)` → "MM-fond historisk lav (5 pctile) — contrarian-bull"
- `MM/Comm divergens z=+2.0 (topp-signal)` → "Fond ekstrem long vs hedgere ekstrem short — klassisk toppsignal"
- `OI stigende mot retning (advarsel)` → "Nye posisjoner bygger mot vår retning — advarsel"
- `Real yields negative` → "Negative realrenter — støtter gull/safe-havens"

Den gamle `score-items`-griden (6 dots med kryss-tekst fra 9-kriterie-tiden) er fjernet — Driver-familier-seksjonen erstatter den med rikere visualisering.

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
| Scoring-motor | `driver_matrix.py` (6 driver-familier, schema 2.0) + `driver_group_mapping.py` (asset-routing) |
| COT-analytics | `cot_analytics.py` (MM-percentile 52w, divergens-z, OI-regime, Index Investor) — cache i `data/cot_analytics/` |
| Scoring-config | `scoring_config.py` — PUSH_THRESHOLDS, HORIZON_CONFIGS, DXY-penalty, korrelasjonsgrenser |
| Varsling | Telegram / Discord webhook / Flask REST API |
| Trading bot | `scalp_edge/trading_bot.py` — cTrader Open API (Twisted/Protobuf), pusher priser hver time kl XX:35 CET |
| SMC-motor | `smc.py` — Python-port av FluidTrades SMC Lite |
| Tester | `tests/test_c1_fix.py` (19 tester — driver matrix + familie-omplassering + data-quality) + `tests/test_cot_analytics.py` (12 tester — percentile, z-score, OI-regime, build_asset_analytics) |

### COT-kildelogikk

| Instrument | Primær | Fallback | Kombinering |
|---|---|---|---|
| Brent | ICE Futures Europe | CFTC | OI-vektet snitt når begge ferske |
| Hvete / Raps / Mais | Euronext (MiFID II) | CFTC | OI-vektet snitt når begge ferske |
| Alle andre | CFTC | — | — |

Uenighet mellom to kilder → `momentum=BLANDET`, `cot_confirms=False`, `cot_strong=False`

### Olje overall_signal logikk

Bruker majoritetsstemme over alle 5 instrumenter (Brent, WTI, NatGas, RBOB, Heating Oil). Hvert instrument har et kombinert pris+COT-signal. Dersom ≥3 segmenter har HIGH risiko, tillegges ekstra bullish bias. Ingen hardkodede terskler — alt er dynamisk basert på faktisk data.

---

## Tester

To test-suiter dekker scoring-kjernen. Alle tester kjøres uten nettverk/filsystem-avhengigheter (rene funksjoner).

```bash
python3 tests/test_c1_fix.py        # 19 tester — driver matrix
python3 tests/test_cot_analytics.py # 12 tester — COT analytics
```

**`tests/test_c1_fix.py` (19 tester)**
- C1-regresjon: trend+COT alene = max B (kan ikke nå A uten 3 uavhengige familier)
- 4-familier confluence gir A-grade
- Risk-gate kapper grade ved USDA blackout
- Horisont-auto-determination (SCALP/SWING/MAKRO)
- FRED-score kun i FUNDAMENTAL (ikke dobbelttelt i MACRO)
- Real yields flyter inn til metals MACRO
- Fear & Greed aktiverer metals (safe-haven) og indices (contrarian bear)
- Data-quality-gate: `_fallback=True` → max A; COT > 20d → max B
- Grade pct-scaling: samme input → samme relative grade på tvers av horisonter
- POSITIONING v2 sub-signaler: MM percentile, MM-Comm divergens, OI-regime, Index Investor
- Bakoverkompatibilitet: compute_positioning_v2 uten nye kwargs = legacy-oppførsel

**`tests/test_cot_analytics.py` (12 tester)**
- rank_percentile: edges (0/100), insufficient history (<26 uker), midt-verdi
- rolling_z: robust mot outliers (median/MAD), None ved konstant historikk
- oi_regime: confirmation/warning/liquidation/stable-klassifisering
- index_investor_bias: structural_long/short terskel-logikk (>5 % av OI)
- build_asset_analytics: graceful degradation, fresh-output med realistiske verdier
