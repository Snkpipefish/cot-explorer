# COT Explorer – Markedspuls

Live: https://snkpipefish.github.io/cot-explorer  
Repo: https://github.com/Snkpipefish/cot-explorer

---

## Hva er dette?

En statisk nettside (GitHub Pages) som viser:
- **Trading Setups** med entry/SL/T1/T2 og konfluens-score (7 punkter)
- **Makro-panel** med Dollar Smile-modell og VIX-regime
- **COT-posisjoner** for 500+ markeder fra CFTC
- **Kalender** og **Priser** (Yahoo Finance)

Alt drives av JSON-filer i `data/` som genereres lokalt og pushes til GitHub.

---

## Filstruktur

```
cot-explorer/
├── index.html                  # Hele frontend (én fil, vanilla JS)
├── fetch_cot.py                # Laster ned COT-data fra CFTC → data/timeseries/
├── build_combined.py           # Bygger data/combined/latest.json fra timeseries
├── fetch_all.py                # Henter priser fra Yahoo + bygger data/macro/latest.json
├── fetch_prices.py             # Enklere pris-fetcher (backup)
└── data/
    ├── timeseries/             # ~500+ JSON-filer, én per marked
    │   ├── index.json          # Oversikt over alle markets (symbol, navn, kategori)
    │   └── {symbol}_{report}.json   # Historiske COT-data per marked
    ├── combined/
    │   └── latest.json         # COT-tab: liste med alle markeder + siste netto
    └── macro/
        └── latest.json         # Setups + makro + priser (hoveddatafil)
```

---

## Datafiler – format

### `data/timeseries/{symbol}_{report}.json`
```json
{
  "symbol": "020601",
  "market": "U.S. Treasury Bonds",
  "navn_no": "US T-Bond 30Y",
  "kategori": "renter",
  "report": "tff",
  "data": [
    {"date": "2025-12-30", "spec_net": -339694, "spec_long": 45000, "spec_short": 384694, "oi": 529597}
  ]
}
```
- `report`: `tff` | `legacy` | `disaggregated` | `supplemental`
- `spec_net`: netto spekulantposisjon (positivt = bull, negativt = bear)
- `oi`: open interest

### `data/combined/latest.json`
Liste brukt av COT-tab i nettleseren:
```json
[
  {
    "symbol": "020601",
    "market": "U.S. Treasury Bonds",
    "navn_no": "US T-Bond 30Y",
    "kategori": "renter",
    "report": "tff",
    "date": "2025-12-30",
    "spekulanter": {"net": -339694, "long": 45000, "short": 384694},
    "open_interest": 529597,
    "change_spec_net": -12000
  }
]
```

### `data/macro/latest.json`
Hoveddatafil. Struktur:
```json
{
  "date": "2026-03-22 15:41 UTC",
  "cot_date": "2025-12-30",
  "prices": {
    "VIX":    {"price": 18.5, "chg1d": -2.1, "chg5d": -5.3, "chg20d": -8.0},
    "SPX":    {"price": 6506, "chg1d":  0.3, "chg5d":  1.2, "chg20d":  3.1},
    "EURUSD": {"price": 1.1575, "chg1d": 0.1, "chg5d": 0.8, "chg20d": 2.0},
    "Gold":   {"price": 4574, "chg1d": 0.4, "chg5d": 1.1, "chg20d": 4.2}
  },
  "vix_regime": {
    "value": 18.5,
    "label": "Normalt – full størrelse",
    "color": "bull",
    "regime": "normal"
  },
  "dollar_smile": {
    "position": "midten",
    "usd_bias": "SVAKT",
    "usd_color": "bear",
    "desc": "Goldilocks – svak USD",
    "inputs": {"vix": 18.5, "hy_stress": false, "brent": 106.4, "tip_trend_5d": 0.2, "dxy_trend_5d": -0.5}
  },
  "trading_levels": {
    "EURUSD": {
      "name": "EUR/USD",
      "label": "Valuta",
      "class": "v",
      "current": 1.1575,
      "atr14": 0.0099,
      "sma200": 1.08,
      "sma200_pos": "over",
      "chg5d": 0.8,
      "chg20d": 2.0,
      "dir_color": "bull",
      "grade": "B",
      "grade_color": "warn",
      "score": 5,
      "score_pct": 71,
      "score_details": [
        {"kryss": "Over SMA200", "verdi": true},
        {"kryss": "5d trend opp", "verdi": true},
        {"kryss": "COT Long bias", "verdi": false},
        {"kryss": "COT ikke short", "verdi": true},
        {"kryss": "Støtte nær", "verdi": true},
        {"kryss": "Motstand fritt", "verdi": false},
        {"kryss": "Momentum 20d", "verdi": true}
      ],
      "resistances": [{"name":"R1","level":1.1620,"dist_atr":0.5}],
      "supports":    [{"name":"S1","level":1.1490,"dist_atr":0.9}],
      "setup_long": {
        "entry": 1.1575, "sl": 1.1450, "t1": 1.1825, "t2": 1.1950,
        "rr_t1": 2.0, "rr_t2": 3.0, "min_rr": 2.0,
        "entry_dist_atr": 0.0, "entry_name": "Nåpris",
        "note": "SL under støtte (1.149). ATR=0.0099"
      },
      "setup_short": {
        "entry": 1.1575, "sl": 1.1620, "t1": 1.1485, "t2": 1.1395,
        "rr_t1": 2.0, "rr_t2": 4.0, "min_rr": 2.0,
        "entry_dist_atr": 0.0, "entry_name": "Nåpris",
        "note": "SL over motstand (1.162). ATR=0.0099"
      },
      "session": {"active": true, "label": "24h"},
      "binary_risk": [],
      "dxy_conf": "medvind",
      "pos_size": "Full",
      "vix_spread_factor": 1.0,
      "cot": {
        "bias": "LONG", "color": "bull",
        "net": 45000, "chg": 3000, "pct": 8.5,
        "date": "2025-12-30", "report": "legacy"
      },
      "combined_bias": "LONG"
    }
  },
  "calendar": [
    {"date": "2026-03-25T14:30:00Z", "title": "Fed Meeting Minutes", "country": "US", "impact": "High", "forecast": "-"}
  ]
}
```

---

## Workflow – oppdater data

```bash
cd ~/cot-explorer

# 1. Hent nye COT-data fra CFTC (ukentlig, fredager)
python3 fetch_cot.py

# 2. Bygg COT-samlefil
python3 build_combined.py

# 3. Hent priser + bygg setups
python3 fetch_all.py

# 4. Push
git add data/
git commit -m "oppdater data $(date +%Y-%m-%d)"
git push origin main
```

---

## Setup-kalkulator – logikk

**Score (7 punkter):**
1. Over SMA200
2. 5d trend opp
3. COT Long bias (spec_net/OI > 4%)
4. COT ikke short (spec_net/OI > -4%)
5. Støtte nær (< 2x ATR unna)
6. Motstand fritt (> 1.5x ATR til neste)
7. Momentum 20d positivt

**Grade:** A+ = 6-7p | B = 4-5p | C = 0-3p

**Entry/SL/Target:**
- Entry = nåpris
- SL Long = nærmeste støtte − 0.2×ATR
- SL Short = nærmeste motstand + 0.2×ATR
- T1 = entry ± risk×2.0
- T2 = entry ± risk×3.0

**VIX-regime posisjonsstørrelse:**
- VIX < 20 → Full størrelse
- VIX 20-30 → Halv størrelse
- VIX > 30 → Kvart størrelse

---

## Instruments i fetch_all.py

| Key | Navn | Yahoo-symbol |
|-----|------|-------------|
| EURUSD | EUR/USD | EURUSD=X |
| USDJPY | USD/JPY | JPY=X |
| GBPUSD | GBP/USD | GBPUSD=X |
| USDCHF | USD/CHF | CHFUSD=X |
| AUDUSD | AUD/USD | AUDUSD=X |
| Gold | Gull | GC=F |
| Silver | Sølv | SI=F |
| Brent | Brent | BZ=F |
| WTI | WTI | CL=F |
| SPX | S&P 500 | ^GSPC |
| NAS100 | Nasdaq | ^NDX |
| VIX | VIX | ^VIX |
| DXY | DXY | DX-Y.NYB |

---

## Tech stack

- **Frontend:** Vanilla HTML/CSS/JS, én fil (`index.html`), ingen bundler
- **Backend:** Python 3, ingen dependencies utover stdlib
- **Hosting:** GitHub Pages (statisk)
- **Data:** CFTC (COT) + Yahoo Finance (priser)
