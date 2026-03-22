# COT Explorer – Markedspuls

Live: https://snkpipefish.github.io/cot-explorer  
Repo: https://github.com/Snkpipefish/cot-explorer

---

## Hva er dette?

En statisk nettside (GitHub Pages) som viser daglige trading-ideer basert på:
- **Level-til-level setups** — entry ved faktisk nivå, T1/T2 er neste reelle nivå
- **Konfluens-score (8 punkter)** inkl. COT, EMA9, SMA200, sentiment
- **Makro-panel** med Dollar Smile-modell, VIX-regime og konflikt-flagging
- **COT-posisjoner** for 366 markeder fra CFTC (siste uke)
- **Priser** med 1d/5d/20d endring fra Yahoo Finance

Alt drives av JSON-filer i data/ som genereres lokalt og pushes til GitHub.

---

## Viktig — datakilde for trading-ideer

**Trading-ideene bruker KUN siste ukes COT-data** fra data/combined/latest.json,
bygget fra data/{report}/latest.json.

**Timeseries brukes IKKE til trading-ideer** — kun til historikk-visning.

COT-dato vises øverst på Trading Setups-fanen. Typisk dato: tirsdag i rapport-uken
(CFTC publiserer fredag, data reflekterer tirsdag samme uke).

---

## Filstruktur
```
cot-explorer/
├── index.html                  # Hele frontend (én fil, vanilla JS)
├── fetch_cot.py                # Laster ned COT-data fra CFTC
├── build_combined.py           # Bygger data/combined/latest.json fra siste uke
├── fetch_all.py                # Henter priser + bygger data/macro/latest.json
└── data/
    ├── tff/latest.json         # Siste ukes TFF-rapport (76 markeder)
    ├── legacy/latest.json      # Siste ukes Legacy-rapport (290 markeder)
    ├── disaggregated/latest.json
    ├── supplemental/latest.json
    ├── timeseries/             # Historiske COT-data (KUN historikk-fanen)
    ├── combined/latest.json    # COT-tab: 366 markeder fra siste uke
    └── macro/latest.json       # Hoveddatafil: setups + makro + priser
```

---

## Setup-logikk — Level-til-Level

**Kjerneprinsipp:** Entry MÅ være ved et faktisk nivå. T1/T2 er neste reelle nivå.

### Nivåhierarki
1. PWH / PWL — forrige ukes range
2. PDH / PDL — gårsdagens range
3. SMA200 — strukturell trend
4. PDC — psykologisk magnet
5. Tekniske topper/bunner fra 4H
6. EMA9 — lokal momentum

### Entry / SL / T1 / T2
- Entry = nåpris ved nivå (MÅ være ≤1×ATR fra nivå for status "aktiv")
- SL Long = støtte − spread-buffer
- SL Short = motstand + spread-buffer
- T1 = neste faktiske nivå i retningen
- T2 = nivå etter T1
- Dropp setup hvis R:R T1 < 1.5

### Status
- Aktiv — pris ≤1×ATR fra entry-nivå
- Watchlist — pris >1×ATR unna

### Konfluens-score (8 punkter)
1. Over SMA200
2. 5d trend opp
3. COT long bias (spec_net/OI > 4%)
4. COT ikke short (spec_net/OI > -4%)
5. Støtte nær (≤1×ATR)
6. Motstand fritt (>1.5×ATR)
7. Momentum 20d positivt
8. Sentiment bekrefter (Fear&Greed < 35)

Grade: A+ = 7-8p | B = 5-6p | C = 0-4p

### VIX-regime
- VIX < 20 → Full størrelse
- VIX 20-30 → Halv størrelse
- VIX > 30 → Kvart størrelse

---

## Instruments

| Key    | Navn    | Yahoo     | Klasse | Sesjon |
|--------|---------|-----------|--------|--------|
| EURUSD | EUR/USD | EURUSD=X  | A | London 08:00-12:00 CET |
| USDJPY | USD/JPY | JPY=X     | A | London 08:00-12:00 CET |
| GBPUSD | GBP/USD | GBPUSD=X  | A | London 08:00-12:00 CET |
| AUDUSD | AUD/USD | AUDUSD=X  | A | London 08:00-12:00 CET |
| Gold   | Gull    | GC=F      | B | London Fix 10:30 / NY Fix 15:00 CET |
| Silver | Sølv    | SI=F      | B | London Fix 10:30 / NY Fix 15:00 CET |
| Brent  | Brent   | BZ=F      | B | London Fix 10:30 / NY Fix 15:00 CET |
| WTI    | WTI     | CL=F      | B | London Fix 10:30 / NY Fix 15:00 CET |
| SPX    | S&P 500 | ^GSPC     | C | NY Open 14:30-17:00 CET |
| NAS100 | Nasdaq  | ^NDX      | C | NY Open 14:30-17:00 CET |
| DXY    | DXY     | DX-Y.NYB  | A | London 08:00-12:00 CET |

---

## Workflow — ukentlig oppdatering
```bash
cd ~/cot-explorer
python3 fetch_cot.py        # fredag etter 21:30 CET
python3 build_combined.py   # bygg COT-samlefil
python3 fetch_all.py        # hent priser + setups
git add data/
git commit -m "ukesoppdatering $(date +%Y-%m-%d)"
git push origin main
```

---

## Datakilder

| Data | Kilde | Frekvens |
|------|-------|----------|
| COT-posisjoner | CFTC.gov | Ukentlig (fredag 21:30 CET) |
| Priser, ATR, SMA200, EMA9, PDH/PDL/PWH/PWL | Yahoo Finance | Ved kjøring |
| Fear & Greed | CNN dataviz API | Ved kjøring |

---

## Tech stack

- Frontend: Vanilla HTML/CSS/JS, én fil (index.html), ingen bundler
- Backend: Python 3, ingen dependencies utover stdlib
- Hosting: GitHub Pages (statisk)
