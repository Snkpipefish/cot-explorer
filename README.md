# COT Explorer 📊

Visualisering av CFTC's Commitments of Traders (COT) rapporter.
Live side: **https://snkpipefish.github.io/cot-explorer**

## Hva er COT-data?

CFTC publiserer hver fredag kl. 21:30 norsk tid en rapport som viser hvem som holder posisjoner i futures-markedene i USA. Dataen er fra tirsdagen samme uke.

**Tre hovedgrupper:**
- **Leveraged Funds** – Hedge funds og spekulative tradere. Følger trenden.
- **Asset Managers** – Pensjonsfond, forsikringsselskaper. Langsiktige investorer.
- **Dealers** – Banker og meglere. Tar gjerne motsatt side av kundene.

Netto = Long minus Short. Positivt tall = flere kjøpere enn selgere (bullish).

---

## AI-tilgang til data

Siste ukens data (JSON):
```
https://snkpipefish.github.io/cot-explorer/data/latest.json
```

Historiske filer: `/data/YYYY-MM-DD.json`

---

## Datastruktur
```json
{
  "date": "2026-03-17",
  "market": "S&P 500 Consolidated",
  "symbol": "13874+",
  "open_interest": 2359720,
  "leveraged_funds": { "long": 145042, "short": 492619, "net": -347577 },
  "asset_managers":  { "long": 1089306, "short": 199864, "net": 889442 },
  "dealers":         { "long": 140531, "short": 802355, "net": -661824 },
  "non_reportable":  { "long": 290138, "short": 202589, "net": 87549 },
  "change_oi": 336624,
  "change_lev_net": 10519
}
```

| Felt | Forklaring |
|------|-----------|
| `leveraged_funds.net` | Hedge fund netto (positiv = bullish) |
| `asset_managers.net` | Institusjonelle investorer netto |
| `dealers.net` | Bank/megler netto |
| `change_oi` | Endring i open interest fra forrige uke |
| `change_lev_net` | Endring i hedge fund netto fra forrige uke |

---

Kilde: [CFTC.gov](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
