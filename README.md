# Markedspuls – COT Explorer 📊

Visualisering av CFTC's Commitments of Traders (COT) rapporter.
Live side: **https://snkpipefish.github.io/cot-explorer**

---

## For AI: Slik henter du data

### Siste ukes data (659 markeder, alle rapporter kombinert)
```
https://snkpipefish.github.io/cot-explorer/data/combined/latest.json
```

### Per rapport
```
https://snkpipefish.github.io/cot-explorer/data/tff/latest.json           (76 markeder – valuta, aksjer, renter, krypto)
https://snkpipefish.github.io/cot-explorer/data/legacy/latest.json        (290 markeder – alle markeder)
https://snkpipefish.github.io/cot-explorer/data/disaggregated/latest.json (281 markeder – råvarer)
https://snkpipefish.github.io/cot-explorer/data/supplemental/latest.json  (12 markeder – landbruk)
```

### Historiske tidsserier per marked
```
https://snkpipefish.github.io/cot-explorer/data/timeseries/index.json     (indeks over alle 1292 tidsserier)
https://snkpipefish.github.io/cot-explorer/data/timeseries/13874+_tff.json (eksempel: S&P 500)
```

---

## Datastruktur (combined/latest.json)
```json
{
  "date": "2026-03-17",
  "market": "S&P 500 Consolidated",
  "navn_no": "S&P 500",
  "forklaring": "De 500 største selskapene i USA.",
  "symbol": "13874+",
  "kategori": "aksjer",
  "report": "tff",
  "open_interest": 2359720,
  "change_oi": 336624,
  "change_spec_net": 10519,
  "spekulanter": { "long": 145042, "short": 492619, "net": -347577, "label": "Hedge Funds" },
  "institusjoner": { "long": 1089306, "short": 199864, "net": 889442, "label": "Pensjonsfond" },
  "meglere": { "long": 140531, "short": 802355, "net": -661824, "label": "Banker/Meglere" },
  "smahandlere": { "long": 290138, "short": 202589, "net": 87549, "label": "Småhandlere" }
}
```

| Felt | Forklaring |
|------|-----------|
| `navn_no` | Norsk markedsnavn |
| `kategori` | aksjer / valuta / renter / råvarer / krypto / landbruk |
| `report` | tff / legacy / disaggregated / supplemental |
| `spekulanter.net` | Hedge fund netto (positivt = bullish) |
| `institusjoner.net` | Pensjonsfond/forsikring netto |
| `meglere.net` | Banker/meglere netto |
| `change_spec_net` | Ukentlig endring i spekulanters netto |

---

## Tidsserie-struktur (data/timeseries/*.json)
```json
{
  "symbol": "13874+",
  "market": "S&P 500 Consolidated",
  "navn_no": "S&P 500",
  "kategori": "aksjer",
  "report": "tff",
  "data": [
    { "date": "2009-06-16", "spec_net": 12500, "spec_long": 89000, "spec_short": 76500, "oi": 890000 },
    { "date": "2009-06-23", "spec_net": 15200, "spec_long": 92000, "spec_short": 76800, "oi": 912000 }
  ]
}
```

---

## Kategorier

| Kategori | Innhold |
|----------|---------|
| `aksjer` | S&P 500, Nasdaq, Russell, Nikkei, MSCI, VIX |
| `valuta` | EUR/USD, JPY, GBP, CHF, DXY m.fl. |
| `renter` | US 2/5/10/30-årig, SOFR |
| `råvarer` | Olje, gull, sølv, kobber, naturgass |
| `krypto` | Bitcoin, Ethereum, Solana, XRP |
| `landbruk` | Mais, soya, hvete, kaffe, sukker, bomull |

---

## Oppdateringsfrekvens

Data oppdateres automatisk hver fredag etter kl. 21:30 norsk tid.
Kilde: [CFTC.gov](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
