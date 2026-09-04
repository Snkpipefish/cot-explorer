#!/usr/bin/env python3
"""
fetch_ice_cot.py — ICE Futures Europe COT-data (Brent, Gasoil m.fl.) fra bedrock

Tidligere lastet dette scriptet ICE sin COTHist-CSV/Excel direkte (krevde
openpyxl og var i praksis dødt fra april 2026). Bedrock henter nå ICE COT
ukentlig på egen timer (bedrock-fetch-cot_ice.timer) inn i tabellen
`cot_ice`, og cot-explorer er en read-only konsument av bedrock.db.

Output (uendret format, slik fetch_all.py forventer):
  data/ice_cot/latest.json  — {generated, source, markets: [...]}
  data/ice_cot/history.json — rullende 26-ukers historikk per marked

Brukes av fetch_all.py: Brent bruker ICE som primær COT-kilde (ICE er
hjemmebørs for Brent), med CFTC som fallback.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE       = Path(__file__).parent
OUT_DIR    = BASE / "data" / "ice_cot"
OUT        = OUT_DIR / "latest.json"
HIST       = OUT_DIR / "history.json"
BEDROCK_DB = Path(os.environ.get("BEDROCK_DB", os.path.expanduser("~/bedrock/data/bedrock.db")))

HISTORY_WEEKS = 26

# Kontraktsnavn i bedrock.cot_ice → display-navn. Nøkkelen brukes som
# "market" i output og matcher ICE_COT_MAP i fetch_all.py.
DISPLAY = {
    "ice brent crude": "ICE Brent Crude",
    "ice gasoil":      "ICE Gasoil",
    "ice ttf gas":     "ICE TTF Gas",
    "ice cocoa":       "ICE Cocoa (London)",
    "ice coffee":      "ICE Robusta Coffee",
    "ice sugar":       "ICE White Sugar",
    "ice wheat":       "ICE Feed Wheat",
}


def load_rows() -> dict[str, list[dict]]:
    """Les de siste HISTORY_WEEKS ukene per kontrakt, eldst først."""
    con = sqlite3.connect(f"file:{BEDROCK_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT report_date, contract, mm_long, mm_short, open_interest
            FROM cot_ice
            ORDER BY contract, report_date DESC
            """
        ).fetchall()
    finally:
        con.close()

    by_contract: dict[str, list[dict]] = {}
    for r in rows:
        lst = by_contract.setdefault(r["contract"], [])
        if len(lst) >= HISTORY_WEEKS:
            continue
        lst.append({
            "date":  r["report_date"],
            "long":  int(r["mm_long"] or 0),
            "short": int(r["mm_short"] or 0),
            "net":   int(r["mm_long"] or 0) - int(r["mm_short"] or 0),
            "oi":    int(r["open_interest"] or 0),
        })
    for lst in by_contract.values():
        lst.reverse()   # eldst → nyest, som history.json alltid har vært
    return by_contract


def build_output(by_contract: dict[str, list[dict]]) -> tuple[list[dict], dict]:
    markets = []
    history = {}
    for key, entries in sorted(by_contract.items()):
        head = entries[-1]
        prev_net = entries[-2]["net"] if len(entries) >= 2 else head["net"]
        markets.append({
            "market":       key,
            "display_name": DISPLAY.get(key, key.replace("ice ", "ICE ").title()),
            "spekulanter": {
                "long":  head["long"],
                "short": head["short"],
                "net":   head["net"],
                "label": "Managed Money",
            },
            "open_interest":    head["oi"] or max(abs(head["net"]) * 8, 1),
            "change_spec_net":  head["net"] - prev_net,
            "spec_net_history": [e["net"] for e in entries],
            "date":             head["date"],
            "report":           "ice",
        })
        history[key] = [
            {"date": e["date"], "net": e["net"], "long": e["long"], "short": e["short"]}
            for e in entries
        ]
    return markets, history


def main() -> bool:
    print("Henter ICE COT fra bedrock...")
    if not BEDROCK_DB.exists():
        print(f"  FEIL: bedrock.db finnes ikke: {BEDROCK_DB}")
        return False
    try:
        by_contract = load_rows()
    except sqlite3.Error as e:
        print(f"  FEIL: kunne ikke lese cot_ice: {e}")
        return False
    if not by_contract:
        print("  FEIL: cot_ice-tabellen er tom — ingen data skrevet")
        return False

    markets, history = build_output(by_contract)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    HIST.write_text(json.dumps(history, ensure_ascii=False, indent=2))
    OUT.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source":    "ICE Futures Europe via bedrock.cot_ice",
        "markets":   markets,
    }, ensure_ascii=False, indent=2))

    print(f"  OK → {len(markets)} markeder lagret")
    for m in markets:
        net = m["spekulanter"]["net"]
        pct = net / m["open_interest"] * 100 if m["open_interest"] else 0
        print(f"    {m['display_name']:24} net={net:+,}  ({pct:+.1f}% OI)  {m['date']}")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
