# Agri-signaler → Trading Bot — Integrasjonsguide

## Oversikt

`push_agri_signals.py` genererer fundamentalbaserte trading-setups for agri-råvarer basert på avlingsdata (vær, yield, COT, ENSO). Disse skrives til `data/agri_signals.json` og merges deretter inn i den **felles** `/push-alert`-payloaden av `push_signals.py` — agri-signalene flagges med `source: "agri_fundamental"` slik at boten kan filtrere/behandle dem med agri-spesifikke regler.

Boten henter alle signaler fra `/signals` og skiller på `source`-feltet — det finnes **ikke** en egen `/agri-signals`-endpoint.

---

## Dataflyt

```
fetch_agri.py          → data/agri/latest.json      (vær, yield, COT, ENSO)
push_agri_signals.py   → data/agri_signals.json      (trading-setups, grade A/B)
push_signals.py        → POST /push-alert            (felles endpoint;
                                                      agri merges inn med
                                                      source: "agri_fundamental")
signal_server.py       → latest_signals.json         (felles cache, alle kilder)
                       → GET /signals                 (bot henter, filtrerer på source)
```

Kjøres i `update.sh`: `fetch_agri.py` → `push_signals.py` → `push_agri_signals.py` (merken inn i neste push_signals-kjøring).

Agri-signalene har **ingen scoring-side aging-filter** (fjernet i schema 2.2 — boten håndterer signal-utløp selv via `horizon_config.exit_timeout_*`-feltene).

---

## Endpoint: POST /push-alert (felles for tekniske og agri)

Agri-signaler ligger som egne objekter i `signals[]`-arrayet. Boten gjenkjenner dem på `source: "agri_fundamental"`.

### Payload-struktur (utdrag — kun agri-relevante felt)

```json
{
  "schema_version": "2.1",
  "generated": "2026-04-17 16:00 UTC",
  "global_state": {
    "geo_active": false,
    "vix_regime": "normal",
    "correlation_regime": "normal",
    "correlation_config": {...}
  },
  "signals": [
    {
      "key": "Cotton",
      "name": "Bomull",
      "horizon": "MAKRO",
      "direction": "bull",
      "grade": "A",
      "score": 9.0, "max_score": 18,
      "setup": {
        "entry": 78.95, "sl": 78.61, "t1": 79.52, "t2": 80.20,
        "rr_t1": 1.68, "rr_t2": 3.68, "sl_type": "atr_prosent"
      },
      "cot": {"bias": "LONG", "pct": 12.4},
      "atr_d1": 0.34, "atr_est": 0.34,
      "correlation_group": "cotton",
      "source": "agri_fundamental",
      "horizon_config": {...},
      "data_quality": "fresh",
      "quality_notes": [],
      "yield_score": 34,
      "weather_outlook": "tørt",
      "drivers": [
        "Yield kritisk (34) — supply-press",
        "Værstress USA Cotton Belt — tørke",
        "COT: spekulanter snur long",
        "Conab: bomull -2.1% m/m (bull)"
      ],
      "driver_groups": {
        "trend":       {"score": 1.0,  "weight": 0.8, "drivers": []},
        "positioning": {"score": 1.0,  "weight": 1.0, "drivers": ["COT LONG 12.4%"]},
        "macro":       {"score": 0.0,  "weight": 1.0, "drivers": []},
        "fundamental": {"score": 0.85, "weight": 1.3, "drivers": ["Yield kritisk", "..."]},
        "risk":        {"score": 0.0,  "weight": 1.0, "drivers": []},
        "structure":   {"score": 0.0,  "weight": 0.5, "drivers": []}
      },
      "active_driver_groups": 3,
      "group_drivers": ["Yield kritisk (34) — supply-press", "..."],
      "created_at": "2026-04-17T16:00:00+00:00"
    }
  ]
}
```

### Felter som er agri-spesifikke

| Felt | Type | Beskrivelse |
|---|---|---|
| `source` | str | Alltid `"agri_fundamental"` for agri-signaler |
| `max_score` | int | **18** for agri (vs 4.2/5.0/5.2 for tekniske, per horisont) |
| `data_quality` | str | `"fresh"` / `"degraded"` / `"stale"` — propagert fra Conab/UNICA-staleness |
| `quality_notes` | list[str] | F.eks. `["Conab missing"]` når en kritisk kilde mangler |
| `yield_score` | int | 0–100 fra Open-Meteo (lav = supply-knapphet, høy = overflod) |
| `weather_outlook` | str | `"tørt"` / `"vått"` / `"tørke"` / `"flom"` / `"normalt"` |
| `drivers` | list[str] | Menneskelig lesbare driver-strenger fra agri-scoring |
| `correlation_group` | str | `"grains"` / `"softs"` / `"cotton"` (fra `AGRI_CORRELATION_SUBGROUPS`) |

---

## Forskjeller fra tekniske signaler

Begge typer kommer i samme `/push-alert`-payload — boten skiller på `source`:

| Egenskap | Tekniske | Agri (`source: "agri_fundamental"`) |
|----------|----------|-------------------------------------|
| `source` | (fraværende) | `"agri_fundamental"` |
| `score`-skala | 0–6 (driver_matrix, 5 scoring-familier) | 0–18 (additivt, 7 komponenter) |
| `max_score` | 4.2/5.0/5.2 (per horisont) | **18** (`AGRI_MAX_SCORE`) |
| Grade-terskler | % av max (75/55/35) | Absolutt: A ≥ 7, B ≥ 5 |
| `confirmation_candle_limit` | per horisont (SCALP 6, SWING 8, MAKRO 6) | bot-side: 12 (1 time) |
| `expiry_candles` | per horisont | bot-side: 48 (4 timer) |
| Aging-filter (live pris vs entry) | **Fjernet** (schema 2.2) — bot håndterer via `exit_timeout_*` | **Fjernet** (schema 2.2) — bot håndterer via `exit_timeout_*` |
| Entry-basis | Teknisk S/R-nivå (struktur + SMC) | ATR-prosent estimat (pullback −0.3×ATR) |
| SL-basis | Struktur (under demand-sone) + ATR | 1.5× estimert ATR |
| `data_quality` | Fra `_assess_data_quality` (FRED/COT-staleness) | Fra Conab/UNICA-staleness (inkl. `corrupt`-deteksjon) |
| Bot-størrelse | VIX × horisont-base | **Halvert** uansett (lavere likviditet) |
| Maks samtidige | Korrelasjons-bucketed (`MAX_CONCURRENT`) | Bot-side (scoring håndhever ikke lenger subgruppe-cap) |

> **Merk:** Boten tar bare tradet — den sammenligner ikke score på tvers av kilder. Forskjellig `max_score` er kun synlig i UI (`score_pct = score / max_score`).

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

### 1. Filtrer agri-signaler ut fra felles `/signals`-respons

Det finnes ingen separat agri-endpoint — alle signaler kommer i samme respons. Boten kan partisjonere på `source`-feltet:

```python
def _partition_signals(self, payload):
    techs, agris = [], []
    for sig in payload.get("signals", []):
        if sig.get("source") == "agri_fundamental":
            agris.append(sig)
        else:
            techs.append(sig)
    return techs, agris
```

### 2. Juster ATR-nivåer med live data

**Viktig:** Entry/SL/T1 i agri-signaler er basert på **estimert ATR** (prosent av pris) — feltet `atr_est` (også speilet i `atr_d1` for kompatibilitet). Boten bør rekalibrere med live ATR14 fra cTrader når avviket er > 30 %:

```python
def _recalibrate_agri_levels(self, sig, live_atr):
    est_atr = sig.get("atr_est") or sig.get("atr_d1")
    setup   = sig.get("setup", {})
    if not est_atr or not live_atr or not setup.get("entry"):
        return sig

    ratio = live_atr / est_atr
    if 0.7 < ratio < 1.3:
        return sig  # Nærme nok — ikke juster

    entry = setup["entry"]
    direction = 1 if sig["direction"] in ("buy", "bull") else -1
    setup["sl"] = round(entry - direction * 1.5 * live_atr, 5)
    setup["t1"] = round(entry + direction * 2.0 * live_atr, 5)
    setup["t2"] = round(entry + direction * 3.0 * live_atr, 5)
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

**Scoring-laget håndhever ingen agri-subgruppe-cap** (schema 2.2 — fjernet). Korrelasjons-grupper er fortsatt definert i `AGRI_CORRELATION_SUBGROUPS` og settes som `correlation_group`-felt på hvert signal, men begrensning er bot-ansvar:

```python
AGRI_CORRELATION_SUBGROUPS = {
    "Corn": "grains", "Wheat": "grains", "Soybean": "grains",
    "Coffee": "softs", "Sugar": "softs", "Cocoa": "softs",
    "Cotton": "cotton",
}
```

Boten kan velge selv hvor mange samtidige posisjoner den ønsker per subgruppe — flere agri-trades innen samme gruppe er tillatt.

---

## Score-forklaring

Signaler scores 0–18 basert på 7 komponenter (`push_agri_signals.score_crop`). Konstanten ligger i `scoring_config.AGRI_MAX_SCORE`:

| Komponent | Verdi | Beskrivelse |
|-----------|-------|-------------|
| Outlook score | 0–5 | Kombinert vær+COT+yield fundamental (abs-verdi) |
| Yield stress | 0–3 | **BUY**: < 40 kritisk (3), < 55 svak (2), < 70 middels (1). **SELL**: > 85 rekord (3), > 70 sterk (2), > 60 god (1). Symmetrisk siden Apr-2026. |
| Weather urgency | 0–2 | Score ≥ 3 = akutt (2), ≥ 2 = forhøyet (1) |
| ENSO risk | 0–2 | enso_adj > 0.5 = 2, > 0 = 1 |
| Conab shock | 0–2 | Brasiliansk avlingsestimat m/m-revisjon (≥ 2.5 % = 2, ≥ 1.0 % = 1) |
| UNICA mix | 0–2 | Sukker-mix + crush yoy (kun Sugar) |
| Cross-confirm | 0–2 | Multi-kilde-validering (inkl. analog-match fra `agri_analog.py` K-NN mot 15 år historisk vær) |

**Grade:**
- **A** (score ≥ 7): MAKRO timeframe → character A+ → full size (men halvert pga agri-multiplikator i bot)
- **B** (score ≥ 5): SWING timeframe → character B → half size (= kvart total)
- **C** (score < 5): **droppes** — sendes ikke til boten (`push_agri_signals.py:931`: "Grade C = ikke tradeable, hopp over")

### Data-quality

Hvert agri-signal får `data_quality` propagert til payloaden:

| Verdi | Trigger | Cap |
|---|---|---|
| `fresh` | Conab og UNICA er ferske og lastet OK | ingen |
| `degraded` | Én avhengighet er stale (men finnes på disk) | A (ikke A+) |
| `stale` | Én avhengighet mangler helt på disk | B (kappet) |

`quality_notes`-listen viser konkrete grunner (f.eks. `["Conab missing"]`, `["UNICA stale"]`). Logikken finnes i `push_agri_signals._agri_data_quality()` og speiler `driver_matrix._assess_data_quality` for konsistens på tvers av tekniske/agri.

---

## Eksempel: aktive signaler (snapshot — sjekk `data/agri_signals.json` for live verdier)

| Grade | Instrument | Action | Score | Entry | SL | T1 | R:R | Yield | Vær |
|-------|-----------|--------|-------|-------|-----|-----|-----|-------|-----|
| A | Cotton | BUY | 9.0 | 78.95 | 78.61 | 79.52 | 1.68 | 0 (estimert mangler) | Tørt |
| B | Wheat | BUY | 7.0 | 594.64 | 592.32 | 618.50 | 10.28 | 60 (middels) | Tørke |
| B | Soybean | BUY | 6.5 | 1177.11 | 1174.46 | 1211.00 | 12.79 | 32 (kritisk) | Normalt |
| B | Sugar | BUY | 6.2 | 13.39 | 13.31 | 13.78 | 4.87 | 0 (estimert mangler) | Tørke |
| B | Corn | BUY | 5.5 | 454.70 | 453.27 | 465.50 | 7.55 | 11 (kritisk) | Normalt |
| B | Coffee | **SELL** | 5.0 | 296.13 | 297.73 | 290.00 | 3.83 | 100 (rekord) | Tørt |

> Coffee SELL er et eksempel på den nye **symmetriske yield-stress-scoringen** (Apr-2026): yield = 100 → SELL får +3 poeng (tidligere kun +1), slik at supply-overflod kan nå A/B-grade like lett som supply-knapphet for BUY.

---

## Viktige filer

| Fil | Sti | Beskrivelse |
|-----|-----|-------------|
| Agri-fetcher | `/home/pc/cot-explorer/fetch_agri.py` | Henter vær, yield, COT, ENSO |
| Signal-generator | `/home/pc/cot-explorer/push_agri_signals.py` | Genererer trading-setups |
| Agri-signaler (JSON) | `/home/pc/cot-explorer/data/agri_signals.json` | Output, GitHub Pages |
| Signal-server | `/home/pc/scalp_edge/signal_server.py` | Flask API (felles `/push-alert`) |
| Bot-fil (felles) | `/home/pc/scalp_edge/latest_signals.json` | Serverside cache for alle signaler (filtreres på `source`) |
| Konstanter | `/home/pc/cot-explorer/scoring_config.py` | `AGRI_MAX_SCORE`, `AGRI_CORRELATION_SUBGROUPS` |
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
