# Agri-signaler → Trading Bot — Integrasjonsguide

## Oversikt

`push_agri_signals.py` genererer fundamentalbaserte trading-setups for agri-råvarer basert på avlingsdata (vær, yield, COT, ENSO). Disse sendes til `signal_server.py` via `/push-agri-alert` og serveres til boten via `GET /agri-signals`.

Boten må hente og prosessere disse **separat** fra tekniske signaler (`/signals`).

---

## Dataflyt

```
fetch_agri.py          → data/agri/latest.json      (vær, yield, COT, ENSO)
push_agri_signals.py   → data/agri_signals.json      (trading-setups)
                       → POST /push-agri-alert        (til Flask)
signal_server.py       → latest_agri_signals.json     (på disk)
                       → GET /agri-signals             (bot henter)
```

Kjøres i `update.sh` etter `push_signals.py`.

---

## Endpoint: GET /agri-signals

Returnerer agri-signaler i bot-kompatibelt format. Ingen autentisering nødvendig (kun localhost).

### Responsformat

```json
{
  "generated": "2026-04-14 15:42 UTC",
  "valid_until": "2026-04-15T15:42:00+00:00",
  "source": "agri_fundamental",
  "enso_phase": "Nøytral",
  "global_state": {
    "geo_active": false,
    "vix_regime": "normal",
    "max_positions": 2,
    "stop_multiplier": 3.0
  },
  "rules": {
    "risk_pct_full": 1.0,
    "risk_pct_half": 0.5,
    "risk_pct_quarter": 0.25,
    "min_rr_normal": 1.33,
    "min_rr_geo": 1.5,
    "confirmation_candle_limit": 12,
    "geo_spike_atr_multiplier": 2.0
  },
  "signals": [ ... ],
  "invalidated_signals": []
}
```

### Signal-objekt (etter translate)

```json
{
  "id": "SOYBEAN-BUY-1776181455",
  "instrument": "Soybean",
  "direction": "buy",
  "status": "watchlist",
  "character": "A+",
  "confluences": 7.8,
  "entry_zone": [1166.37, 1169.87],
  "alert_level": 1168.12,
  "stop": 1143.49,
  "t1": 1200.97,
  "t2_informational": 1217.60,
  "size": "full",
  "session": "soybean",
  "session_start": "15:00",
  "session_end": "21:00",
  "confirmation_primary": "close_beyond",
  "confirmation_direction": "bullish",
  "expiry_candles": 48,
  "confirmation_candle_limit": 12,
  "close_before_rollover": false,
  "xau_4h_confirmation": false,
  "source": "agri_fundamental",
  "drivers": [
    "Værstress i USA Corn Belt (vått)",
    "COT: spekulanter øker long (net +18% av OI)",
    "Yield kritisk (tidlig) — risiko for lav produksjon",
    "Prognose El Niño: Gunstig regn"
  ],
  "yield_score": 34,
  "weather_outlook": "vått"
}
```

---

## Forskjeller fra tekniske signaler

| Egenskap | Tekniske (/signals) | Agri (/agri-signals) |
|----------|--------------------|-----------------------|
| `source` | (ikke satt) | `"agri_fundamental"` |
| `expiry_candles` | 8 (40 min) | **48** (4 timer) |
| `confirmation_candle_limit` | 6 (30 min) | **12** (1 time) |
| `valid_until` | +16 timer | **+24 timer** |
| `min_rr_normal` | 1.5 | **1.33** |
| Entry-basis | Teknisk S/R-nivå | ATR-prosent estimat |
| SL-basis | Struktur + ATR | 1.5× estimert ATR |
| Ekstra felter | — | `drivers`, `yield_score`, `weather_outlook` |

---

## Støttede instrumenter

| Instrument | cTrader-navn | Session (CET) |
|------------|-------------|----------------|
| Corn | `Corn` | 15:00–21:00 |
| Wheat | `Wheat` | 15:00–21:00 |
| Soybean | `Soybean` | 15:00–21:00 |
| Coffee | `Coffee` | 15:00–19:00 |
| Cotton | `Cotton` | 15:00–21:00 |
| Sugar | `Sugar` | 14:30–18:00 |
| Cocoa | `Cocoa` | 15:00–19:00 |

Boten har allerede prisfeeder for alle disse (definert i `PRICE_FEED_MAP`). De er nå klargjort for trading.

---

## Hva boten trenger å gjøre

### 1. Hent agri-signaler

Poll `GET /agri-signals` med samme intervall som `/signals` (hvert 60. sekund). Hold dem i en separat liste fra tekniske signaler.

```python
def _fetch_agri_signals(self):
    try:
        resp = requests.get(f"{FLASK_URL}/agri-signals", timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except: pass
    return {"signals": []}
```

### 2. Juster ATR-nivåer med live data

**Viktig:** Entry/SL/T1 i agri-signaler er basert på **estimert ATR** (prosent av pris). Boten bør rekalibrere med live ATR14 fra cTrader:

```python
def _recalibrate_agri_levels(self, sig, live_atr):
    est_atr = sig.get("atr_est")  # Fra agri_signals.json (rå format)
    if not est_atr or not live_atr:
        return sig  # Bruk som de er

    ratio = live_atr / est_atr
    if 0.7 < ratio < 1.3:
        return sig  # Nærme nok — ikke juster

    # Rekalibrér
    entry = sig["alert_level"]
    direction = 1 if sig["direction"] == "buy" else -1
    sig["stop"] = round(entry - direction * 1.5 * live_atr, 5)
    sig["t1"]   = round(entry + direction * 2.0 * live_atr, 5)
    sig["t2_informational"] = round(entry + direction * 3.0 * live_atr, 5)
    margin = entry * 0.0015
    sig["entry_zone"] = [round(entry - margin, 5), round(entry + margin, 5)]
    return sig
```

### 3. Posisjonsstørrelse

Agri-signaler bruker **alltid halvparten** av normal størrelse som sikring mot lavere likviditet:

```python
def _get_agri_risk_pct(self, sig, gs):
    base_pct = self._get_risk_pct(sig, gs, rules)
    return base_pct * 0.5  # Halv størrelse for agri
```

### 4. Bekreftelseslogikk

Bruk **samme** confirmation scoring (body size + wick rejection + EMA9 gradient), men med utvidet tidsfrist:
- `confirmation_candle_limit`: 12 candles (1 time, vs 6 for tekniske)
- `expiry_candles`: 48 candles (4 timer, vs 8 for tekniske)

### 5. Exit-regler

Samme som tekniske signaler:
- T1 hit → close 50%, move SL to break-even
- EMA9 crossover → close remaining
- 8-candle / 16-candle timeout-regler
- Geo-spike nødlukking

### 6. Maks samtidige posisjoner

Foreslått: **maks 2 agri-posisjoner** uavhengig av tekniske posisjoner. Unngå å ha for mange korrelerte agri-trades (f.eks. corn + soybean + wheat er alle US grain).

```python
AGRI_MAX_POSITIONS = 2
CORRELATED_GROUPS = {
    "us_grain":  {"Corn", "Wheat", "Soybean"},
    "tropical":  {"Coffee", "Cocoa", "Sugar"},
    "fiber":     {"Cotton"},
}
# Maks 1 posisjon per korrelert gruppe
```

---

## Score-forklaring

Signaler scores 0–18 basert på 7 komponenter (`push_agri_signals.score_crop`):

| Komponent | Verdi | Beskrivelse |
|-----------|-------|-------------|
| Outlook score | 0–5 | Kombinert vær+COT+yield fundamental (abs-verdi) |
| Yield stress | 0–3 | < 40 = kritisk (3), < 55 = svak (2), < 70 = middels (1) |
| Weather urgency | 0–2 | Score ≥ 3 = akutt (2), ≥ 2 = forhøyet (1) |
| ENSO risk | 0–2 | enso_adj > 0.5 = 2, > 0 = 1 |
| Conab shock | 0–2 | Brasiliansk avlingsestimat m/m-revisjon (≥ 2.5 % = 2, ≥ 1.0 % = 1) |
| UNICA mix | 0–2 | Sukker-mix + crush yoy (kun Sugar) |
| Cross-confirm | 0–2 | Multi-kilde-validering på tvers av outlook/COT/Conab/UNICA |

I tillegg: `agri_analog.py` kan legge til 0–2 poeng (K-NN mot 15 år historisk vær), men denne brukes hovedsakelig som metadata.

**Grade:**
- **A** (score ≥ 7): MAKRO timeframe → character A+ → full size (men halvert pga agri-multiplikator i bot)
- **B** (score ≥ 5): SWING timeframe → character B → half size (= kvart total)
- **C** (score < 5): **droppes** — sendes ikke til boten (`push_agri_signals.py:868`: "C-grade sendes ikke til boten")

---

## Eksempel: aktive signaler (2026-04-14)

| Grade | Instrument | Action | Score | Entry | SL | T1 | R:R | Yield | Vær |
|-------|-----------|--------|-------|-------|-----|-----|-----|-------|-----|
| A | Soybean | BUY | 7.8 | 1168.12 | 1143.49 | 1200.97 | 1.33 | 34 (kritisk) | Vått |
| B | Sugar | BUY | 5.8 | 13.83 | 13.37 | 14.44 | 1.33 | 43 (svak) | Tørke |
| C | Coffee | BUY | 4.5 | 308.74 | 297.07 | 324.29 | 1.33 | 98 | Tørt |
| C | Corn | BUY | 3.3 | 447.28 | 437.17 | 460.76 | 1.33 | 60 | Vått |
| C | Wheat | BUY | 2.1 | 593.18 | 577.08 | 614.65 | 1.33 | 96 | Tørke |

---

## Viktige filer

| Fil | Sti | Beskrivelse |
|-----|-----|-------------|
| Agri-fetcher | `/home/pc/cot-explorer/fetch_agri.py` | Henter vær, yield, COT, ENSO |
| Signal-generator | `/home/pc/cot-explorer/push_agri_signals.py` | Genererer trading-setups |
| Agri-signaler (JSON) | `/home/pc/cot-explorer/data/agri_signals.json` | Output, GitHub Pages |
| Signal-server | `/home/pc/scalp_edge/signal_server.py` | Flask API |
| Bot-fil (agri) | `/home/pc/scalp_edge/latest_agri_signals.json` | Serverside cache |
| Update-pipeline | `/home/pc/cot-explorer/update.sh` | Kjører alt sekvensielt |

---

## ENSO-kontekst

ENSO-fasen leses **live fra NOAA CPC ONI** av `fetch_agri.py` og lagres i `data/agri/latest.json`. Påvirker yield-scoring per region via `enso_adj`-faktor.

> *Tidligere snapshot (april 2026, kun illustrasjon — sjekk `data/agri/latest.json` for live verdier):*
> - **ENSO fase:** Nøytral (ONI = -0.16)
> - **Prognose:** 72 % sjanse for El Niño innen mai-juli (IRI Columbia)
> - **ECMWF SEAS5:** SST anomali +2.73 °C innen oktober (sterk El Niño-signal)
>
> El Niño-effekter per region påvirker yield-scoring med halv vekt når den er forecast (ikke aktiv).
