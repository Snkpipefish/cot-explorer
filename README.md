# COT Explorer – Markedspuls

Live: https://snkpipefish.github.io/cot-explorer
Repo: https://github.com/Snkpipefish/cot-explorer

---

## Hva er dette?

En statisk nettside (GitHub Pages) som viser daglige trading-ideer basert på:
- **Level-til-level setups** — entry ved faktisk nivå, T1/T2 er neste reelle nivå
- **Konfluens-score (7 punkter)** inkl. COT, EMA9, SMA200, sesjon, sentiment
- **SMC-analyse** — supply/demand soner, BOS, HH/LH/HL/LL fra 15m data
- **Makro-panel** med Dollar Smile-modell, VIX-regime og konflikt-flagging
- **COT-posisjoner** for 366 markeder fra CFTC (siste uke)
- **COT-historikk** med prisgraf (klikk på marked i COT-fanen)
- **Økonomisk kalender** med binær risiko-varsling
- **Timeframe bias** — D1 + 4H retning vises per instrument
- **COT momentum** — endring i netto-posisjon siste uke

Alt drives av JSON-filer i data/ som genereres lokalt og pushes til GitHub.

---

## Workflow — automatisk oppdatering (crontab)

Scriptet `update.sh` kjøres automatisk via crontab på hverdager (man–fre):

| Tid   | Beskrivelse |
|-------|-------------|
| 07:45 | Morgen |
| 12:30 | Middag |
| 14:15 | Ettermiddag |
| 17:15 | Stenging |

Crontab-oppsettet:
```
45 7  * * 1-5 cd /home/user/cot-explorer && bash update.sh
30 12 * * 1-5 cd /home/user/cot-explorer && bash update.sh
15 14 * * 1-5 cd /home/user/cot-explorer && bash update.sh
15 17 * * 1-5 cd /home/user/cot-explorer && bash update.sh
```

> **Merk:** Hvis PC-en sover på kjøretidspunktet hoppes jobben over.
> Kjør manuelt ved behov: `bash ~/cot-explorer/update.sh`

For å se logg: `tail -f ~/cot-explorer/logs/update.log`

### Hva update.sh gjør (i rekkefølge)
1. `fetch_calendar.py` — henter ForexFactory-kalender
2. `fetch_cot.py` — henter CFTC COT-data
3. `build_combined.py` — bygger kombinert datasett
4. `fetch_all.py` — kjører full analyse (priser, SMC, setup-generering)
5. `push_signals.py` — pusher topp-setups til Telegram/Discord (valgfritt)
6. `git push` — oppdaterer GitHub Pages med nye JSON-filer

---

## Signal-varsling (valgfritt)

`push_signals.py` sender de beste tradingideene til Telegram og/eller Discord etter hver analyse.

Konfigureres med miljøvariabler:

| Variabel | Beskrivelse |
|----------|-------------|
| `TELEGRAM_TOKEN` | Bot-token fra @BotFather |
| `TELEGRAM_CHAT_ID` | Chat-ID som skal motta meldinger |
| `DISCORD_WEBHOOK` | Discord webhook-URL |
| `PUSH_MIN_SCORE` | Minimum konfluens-score for å pushe (standard: 5) |
| `PUSH_MAX_SIGNALS` | Maks antall signaler per kjøring (standard: 5) |

Sett variablene i `~/.bashrc` eller `~/.profile`:
```bash
export TELEGRAM_TOKEN="din-token"
export TELEGRAM_CHAT_ID="din-chat-id"
```

---

## Slik beregnes trading-ideer

### Nivåhierarki
1. SMC supply/demand POI-er (15m)
2. Intradag topper/bunner (15m)
3. PDH / PDL
4. PWH / PWL
5. PDC
6. Swing-nivåer daglig

### Level-til-Level setup
- Entry = nåpris ved nivå (MÅ være innen 0.3×ATR 15m)
- SL = strukturelt nivå bak entry (supply/demand sone eller swing)
- T1 = neste faktiske nivå (HTF-prioritet: D1+ > 4H/SMC > 15m)
- T2 = nivå etter T1
- Dropp hvis R:R < 1.5
- T1 merkes med `?` i frontend hvis kun svakt 15m-nivå finnes

### SL-typer
- **Strukturell SL** — bak supply/demand sone eller swing high/low
- Fallback: 1×ATR(15m) bak entry

### Konfluens-score (7 punkter)
1. Over SMA200
2. D1 + 15m regime likt (EMA9)
3. COT bekrefter retning
4. Pris VED nivå nå
5. Riktig sesjon aktiv
6. Momentum 20d
7. Sentiment (Fear&Greed < 35)

Grade: A+ = 6-7p / B = 4-5p / C = 0-3p

### VIX-regime
- VIX < 20 → Full posisjonsstørrelse
- VIX 20-30 → Halv posisjonsstørrelse
- VIX > 30 → Kvart posisjonsstørrelse

---

## Instruments

| Key | Yahoo | COT | Klasse | Sesjon |
|-----|-------|-----|--------|--------|
| EURUSD | EURUSD=X | 099741 | A | London 08-12 CET |
| USDJPY | JPY=X | 096742 | A | London 08-12 CET |
| GBPUSD | GBPUSD=X | 092741 | A | London 08-12 CET |
| AUDUSD | AUDUSD=X | 232741 | A | London 08-12 CET |
| Gold | GC=F | 088691 | B | London Fix / NY Fix |
| Silver | SI=F | 084691 | B | London Fix / NY Fix |
| Brent | BZ=F | 023651 | B | London Fix / NY Fix |
| WTI | CL=F | 067651 | B | London Fix / NY Fix |
| SPX | ^GSPC | 133741 | C | NY 14:30-17:00 |
| NAS100 | ^NDX | 209742 | C | NY 14:30-17:00 |
| DXY | DX-Y.NYB | 098662 | A | London 08-12 CET |
| VIX | ^VIX | — | C | NY 14:30-17:00 |

---

## Datakilder

| Data | Kilde | Frekvens |
|------|-------|----------|
| COT | CFTC.gov | Ukentlig fredag 21:30 CET |
| Priser, ATR, SMA200, EMA9, PDH/PDL/PWH/PWL | Yahoo Finance | Ved kjøring |
| Fear & Greed | CNN dataviz API | Ved kjøring |
| Kalender | ForexFactory JSON | Ved kjøring |
| SMC supply/demand/BOS | Beregnet fra 15m | Ved kjøring |

---

## Tech stack

- Frontend: Vanilla HTML/CSS/JS, én fil (index.html)
- Backend: Python 3, ingen dependencies utover stdlib
- Hosting: GitHub Pages (statisk)
- Automatisering: crontab (4× daglig, hverdager)
- Varsling: Telegram bot / Discord webhook (valgfritt)
