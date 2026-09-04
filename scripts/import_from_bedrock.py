#!/usr/bin/env python3
"""
import_from_bedrock.py — read-only import from ~/bedrock/bedrock.db
into ~/cot-explorer/data/bedrock/*.json snapshots that the dashboard
consumes. Bedrock is treated as an upstream producer; we never write
back to its database or its source tree.

Run via cot-explorer's update.sh cron (every 4h is plenty — bedrock
fetchers run their own systemd timers).

Schema philosophy:
  - One JSON file per logical source under data/bedrock/
  - All files include {generated, source, rows: int, data: ...}
    so the dashboard can always show freshness even when data is empty
  - Empty bedrock tables → file with rows: 0, data: null  (not absent)
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BEDROCK_DB = Path(os.environ.get("BEDROCK_DB", os.path.expanduser("~/bedrock/data/bedrock.db")))
OUT_DIR    = Path(os.environ.get("BEDROCK_EXPORT", os.path.expanduser("~/cot-explorer/data/bedrock")))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_atomic(path: Path, payload: dict) -> None:
    """Write JSON atomically — temp file + rename — so a half-written
    file is never visible to readers (the cot-explorer git push)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.replace(path)


def fetch_all(con: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    cur = con.cursor()
    cur.row_factory = sqlite3.Row
    return [dict(r) for r in cur.execute(sql, params).fetchall()]


def fetch_count(con: sqlite3.Connection, table: str) -> int:
    try:
        return con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    except sqlite3.Error:
        return 0


# ─────────────────────────────────────────────────────────────────────
# Per-source exporters. Each takes the connection, returns the payload.
# Empty tables yield {rows: 0, data: null} so the UI can show "awaiting".
# ─────────────────────────────────────────────────────────────────────

# EIA series ID → human label (extend as bedrock adds more series)
EIA_SERIES_LABELS = {
    "NW2_EPG0_SWO_R48_BCF": ("Natural Gas Storage (L48)", "BCF"),
    "WCESTUS1":             ("Crude Stocks (US)",         "Mb"),
    "WGTSTUS1":             ("Gasoline Stocks (US)",      "Mb"),
    "WDISTUS1":             ("Distillate Stocks (US)",    "Mb"),
    "WCRSTUS1":             ("Crude excl. SPR (US)",      "Mb"),
}


def export_eia_storage(con: sqlite3.Connection) -> dict:
    """EIA petroleum + natural-gas storage. 5018 rows in current bedrock.
    Aggregates latest value per series_id and a short trend tail."""
    rows = fetch_all(
        con,
        """
        SELECT series_id, date, value, units
        FROM eia_inventory
        ORDER BY series_id, date DESC
        """,
    )
    by_series: dict[str, list[dict]] = {}
    for r in rows:
        by_series.setdefault(r["series_id"], []).append(r)
    latest = {}
    for sid, rs in by_series.items():
        head = rs[0]
        tail = [{"date": x["date"], "value": x["value"]} for x in rs[:52]]  # 52w
        prev = rs[1] if len(rs) > 1 else None
        chg_1w = (head["value"] - prev["value"]) if prev and prev["value"] is not None else None
        # YoY: same week one year back (~52 entries down)
        yoy_idx = min(52, len(rs) - 1)
        prev_yr = rs[yoy_idx] if yoy_idx > 0 else None
        chg_yoy = (head["value"] - prev_yr["value"]) if prev_yr and prev_yr["value"] is not None else None
        # Five-year average for the same week-of-year, if we have >5 years of data
        five_yr_avg = None
        if len(rs) >= 260:
            same_week_vals = [
                rs[k]["value"] for k in (52, 104, 156, 208, 260)
                if k < len(rs) and rs[k]["value"] is not None
            ]
            if same_week_vals:
                five_yr_avg = sum(same_week_vals) / len(same_week_vals)
        label, unit_alt = EIA_SERIES_LABELS.get(sid, (sid.replace("_", " "), None))
        latest[sid] = {
            "label":    label,
            "date":     head["date"],
            "value":    head["value"],
            "units":    unit_alt or head["units"],
            "chg_1w":   chg_1w,
            "chg_yoy":  chg_yoy,
            "five_yr_avg": five_yr_avg,
            "vs_5y_avg": (head["value"] - five_yr_avg) if five_yr_avg else None,
            "history":  list(reversed(tail)),
        }
    return {
        "generated": now_iso(),
        "source":    "EIA · weekly petroleum + natural-gas storage",
        "rows":      len(rows),
        "series_count": len(by_series),
        "data":      latest if latest else None,
    }


def export_manual_csv(filename: str, source_label: str) -> dict:
    """Read a manual CSV from ~/bedrock/data/manual and return its rows."""
    import csv
    src = Path(os.path.expanduser(f"~/bedrock/data/manual/{filename}"))
    if not src.exists():
        return {
            "generated": now_iso(),
            "source":    source_label,
            "rows":      0,
            "data":      None,
            "note":      f"{filename} not present in ~/bedrock/data/manual/",
        }
    try:
        with open(src, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    except Exception as exc:
        return {
            "generated": now_iso(),
            "source":    source_label,
            "rows":      0,
            "data":      None,
            "note":      f"Read error: {exc}",
        }
    return {
        "generated": now_iso(),
        "source":    source_label,
        "rows":      len(rows),
        "data":      rows if rows else None,
    }


def export_news_intel():     return export_manual_csv("news_intel.csv",      "Bedrock manual · curated news intel events")
def export_disease_alerts(): return export_manual_csv("disease_alerts.csv",  "Bedrock manual · crop disease alerts")
def export_export_events():  return export_manual_csv("export_events.csv",   "Bedrock manual · ad-hoc export bans/incidents")
def export_ism_pmi():        return export_manual_csv("ism_pmi.csv",         "ISM · manufacturing PMI (manual)")
def export_iri_enso():       return export_manual_csv("iri_enso_forecast.csv","IRI Columbia · ENSO probability forecast")
def export_crypto_sent():    return export_manual_csv("crypto_sentiment.csv","Crypto sentiment (manual aggregate)")
# Manual fallbacks for DB tables that aren't yet populated by bedrock fetchers
def export_cot_ice_manual():       return export_manual_csv("cot_ice.csv",          "ICE COT (manual CSV supplement — primary source is bedrock cot_ice table → ice_cot.json)")
def export_shipping_manual():      return export_manual_csv("shipping_indices.csv", "Baltic indices (manual fallback — bedrock bdi table empty)")


_BEDROCK_TO_COT_INSTRUMENT = {
    # FX / indices / commodities mapped to the keys cot-explorer uses
    "CrudeOil":   "WTI",
    "SP500":      "SPX",
    "Nasdaq":     "NAS100",
    "NaturalGas": "NatGas",
}


def export_prices(con: sqlite3.Connection) -> dict:
    """Latest close per instrument + chg1d/5d/20d from D1 history.

    Replaces the dead Skilling-bot pipeline that used to write
    ~/scalp_edge/live_prices.json. fetch_prices.py reads this snapshot.
    """
    rows = fetch_all(
        con,
        """
        SELECT instrument, ts, close
        FROM prices
        WHERE tf IN ('D1', 'M1', 'H1')
        ORDER BY instrument, ts DESC
        """,
    )
    by_inst: dict[str, list[dict]] = {}
    for r in rows:
        by_inst.setdefault(r["instrument"], []).append(r)

    prices: dict[str, dict] = {}
    for inst, rs in by_inst.items():
        if not rs or rs[0]["close"] is None:
            continue
        cur = rs[0]["close"]
        # D1 history for change calcs (skip intraday tfs to avoid same-day noise)
        d1 = [x for x in rs if len(str(x["ts"])) >= 10][:30]
        def pct_back(n: int) -> float:
            if len(d1) <= n or d1[n]["close"] in (None, 0):
                return 0.0
            return round((cur / d1[n]["close"] - 1) * 100, 3)
        out_key = _BEDROCK_TO_COT_INSTRUMENT.get(inst, inst)
        prices[out_key] = {
            "value":  round(cur, 6),
            "chg1d":  pct_back(1),
            "chg5d":  pct_back(5),
            "chg20d": pct_back(20),
            "ts":     rs[0]["ts"],
        }
    return {
        "generated": now_iso(),
        "source":    "Bedrock · prices (latest close per instrument)",
        "rows":      len(prices),
        "data":      prices if prices else None,
    }


def export_seismic(con: sqlite3.Connection) -> dict:
    """USGS seismic events. Filter to ≥M4.0 and last 30 days for relevance."""
    rows = fetch_all(
        con,
        """
        SELECT event_id, event_ts, magnitude, latitude, longitude,
               depth_km, place, region, url
        FROM seismic_events
        WHERE magnitude >= 4.0
        ORDER BY event_ts DESC
        LIMIT 50
        """,
    )
    return {
        "generated": now_iso(),
        "source":    "USGS · earthquakes ≥M4.0 (last 50)",
        "rows":      len(rows),
        "data":      rows if rows else None,
    }


def export_cot_euronext(con: sqlite3.Connection) -> dict:
    rows = fetch_all(
        con,
        """
        SELECT report_date, contract, mm_long, mm_short, open_interest
        FROM cot_euronext
        ORDER BY contract, report_date DESC
        """,
    )
    by_contract: dict[str, list[dict]] = {}
    for r in rows:
        by_contract.setdefault(r["contract"], []).append(r)
    out = {}
    for c, rs in by_contract.items():
        head = rs[0]
        history = [r["mm_long"] - r["mm_short"] for r in rs[:52]]  # 52w spec_net
        out[c] = {
            "report_date":   head["report_date"],
            "mm_long":       head["mm_long"],
            "mm_short":      head["mm_short"],
            "mm_net":        (head["mm_long"] or 0) - (head["mm_short"] or 0),
            "open_interest": head["open_interest"],
            "spec_net_history": list(reversed(history)),
        }
    return {
        "generated": now_iso(),
        "source":    "Euronext · MiFID II COT",
        "rows":      len(rows),
        "data":      out if out else None,
    }


def export_cot_ice(con: sqlite3.Connection) -> dict:
    """ICE Futures Europe COT (Brent, Gasoil, London softs) — bedrock cot_ice table.
    Same shape as export_cot_euronext so the UI can treat them alike."""
    rows = fetch_all(
        con,
        """
        SELECT report_date, contract, mm_long, mm_short, open_interest
        FROM cot_ice
        ORDER BY contract, report_date DESC
        """,
    )
    by_contract: dict[str, list[dict]] = {}
    for r in rows:
        by_contract.setdefault(r["contract"], []).append(r)
    out = {}
    for c, rs in by_contract.items():
        head = rs[0]
        history = [(r["mm_long"] or 0) - (r["mm_short"] or 0) for r in rs[:52]]
        out[c] = {
            "report_date":   head["report_date"],
            "mm_long":       head["mm_long"],
            "mm_short":      head["mm_short"],
            "mm_net":        (head["mm_long"] or 0) - (head["mm_short"] or 0),
            "open_interest": head["open_interest"],
            "spec_net_history": list(reversed(history)),
        }
    return {
        "generated": now_iso(),
        "source":    "ICE Futures Europe · COT (bedrock cot_ice)",
        "rows":      len(rows),
        "data":      out if out else None,
    }


def export_comex(con: sqlite3.Connection) -> dict:
    rows = fetch_all(
        con,
        """
        SELECT metal, date, registered, eligible, total, units
        FROM comex_inventory
        ORDER BY metal, date DESC
        """,
    )
    by_metal: dict[str, list[dict]] = {}
    for r in rows:
        by_metal.setdefault(r["metal"], []).append(r)
    out = {}
    for m, rs in by_metal.items():
        head = rs[0]
        prev = rs[1] if len(rs) > 1 else None
        out[m] = {
            "date":              head["date"],
            "registered":        head["registered"],
            "eligible":          head["eligible"],
            "total":             head["total"],
            "units":             head["units"],
            "registered_chg_1d": (head["registered"] - prev["registered"]) if prev else None,
        }
    return {
        "generated": now_iso(),
        "source":    "COMEX vault inventory",
        "rows":      len(rows),
        "data":      out if out else None,
    }


def export_conab(con: sqlite3.Connection) -> dict:
    rows = fetch_all(
        con,
        """
        SELECT report_date, commodity, levantamento, safra, production,
               production_units, area_kha, yield_value, yield_units,
               yoy_change_pct, mom_change_pct
        FROM conab_estimates
        ORDER BY commodity, report_date DESC
        """,
    )
    by_crop: dict[str, dict] = {}
    for r in rows:
        if r["commodity"] in by_crop:
            continue
        by_crop[r["commodity"]] = r
    return {
        "generated": now_iso(),
        "source":    "Conab · Brazil grain & coffee surveys",
        "rows":      len(rows),
        "data":      by_crop if by_crop else None,
    }


def export_unica(con: sqlite3.Connection) -> dict:
    rows = fetch_all(
        con,
        """
        SELECT *
        FROM unica_reports
        ORDER BY report_date DESC
        LIMIT 12
        """,
    )
    return {
        "generated": now_iso(),
        "source":    "UNICA · Brazil sugar-cane crush",
        "rows":      len(rows),
        "data":      rows[0] if rows else None,
        "history":   rows if rows else None,
    }


def export_cot_legacy(con: sqlite3.Connection) -> dict:
    """Bedrock cot_legacy table — empty in current build, but schema-ready."""
    n = fetch_count(con, "cot_legacy")
    rows = (
        fetch_all(
            con,
            "SELECT * FROM cot_legacy ORDER BY report_date DESC LIMIT 500",
        )
        if n
        else []
    )
    return {
        "generated": now_iso(),
        "source":    "CFTC · COT legacy (futures-only)",
        "rows":      n,
        "data":      rows if rows else None,
    }


def export_cot_disagg(con: sqlite3.Connection) -> dict:
    n = fetch_count(con, "cot_disaggregated")
    rows = (
        fetch_all(
            con,
            "SELECT * FROM cot_disaggregated ORDER BY report_date DESC LIMIT 500",
        )
        if n
        else []
    )
    return {
        "generated": now_iso(),
        "source":    "CFTC · COT disaggregated (Managed Money)",
        "rows":      n,
        "data":      rows if rows else None,
    }


def export_fundamentals(con: sqlite3.Connection) -> dict:
    n = fetch_count(con, "fundamentals")
    rows = (
        fetch_all(
            con,
            "SELECT * FROM fundamentals ORDER BY date DESC LIMIT 500",
        )
        if n
        else []
    )
    return {
        "generated": now_iso(),
        "source":    "FRED · macro indicators",
        "rows":      n,
        "data":      rows if rows else None,
    }


def export_weather(con: sqlite3.Connection) -> dict:
    n = fetch_count(con, "weather")
    rows = (
        fetch_all(
            con,
            """SELECT region, date, tmax, tmin, precip, gdd
               FROM weather ORDER BY date DESC LIMIT 1000""",
        )
        if n
        else []
    )
    return {
        "generated": now_iso(),
        "source":    "NOAA · daily weather (per region)",
        "rows":      n,
        "data":      rows if rows else None,
    }


def export_crop_progress(con: sqlite3.Connection) -> dict:
    """USDA NASS weekly crop progress. Bedrock-skjema: week_ending, commodity,
    state, metric, value_pct (NASS-original kolonnenavn)."""
    n = fetch_count(con, "crop_progress")
    rows = (
        fetch_all(
            con,
            "SELECT * FROM crop_progress ORDER BY week_ending DESC LIMIT 200",
        )
        if n
        else []
    )
    return {
        "generated": now_iso(),
        "source":    "USDA NASS · weekly crop progress",
        "rows":      n,
        "data":      rows if rows else None,
    }


def export_wasde(con: sqlite3.Connection) -> dict:
    n = fetch_count(con, "wasde")
    rows = fetch_all(con, "SELECT * FROM wasde ORDER BY report_date DESC LIMIT 50") if n else []
    return {
        "generated": now_iso(),
        "source":    "USDA · WASDE monthly reports",
        "rows":      n,
        "data":      rows if rows else None,
    }


def export_bdi(con: sqlite3.Connection) -> dict:
    n = fetch_count(con, "bdi")
    rows = fetch_all(con, "SELECT * FROM bdi ORDER BY date DESC LIMIT 100") if n else []
    return {
        "generated": now_iso(),
        "source":    "Baltic indices · daily",
        "rows":      n,
        "data":      rows if rows else None,
    }


def export_shipping(con: sqlite3.Connection) -> dict:
    """Bedrock shipping_indices — Baltic Capesize/Dry/Panamax/Supramax
    indices, daily values from BDRY (Yahoo). Latest + 1d change +
    ~6 weeks of history per index_code."""
    rows = fetch_all(
        con,
        """
        SELECT index_code, date, value, source
        FROM shipping_indices
        ORDER BY index_code, date DESC
        """,
    )
    by_code: dict[str, list[dict]] = {}
    for r in rows:
        by_code.setdefault(r["index_code"], []).append(r)
    out: dict[str, dict] = {}
    for code, rs in by_code.items():
        head = rs[0]
        prev = rs[1] if len(rs) > 1 else None
        out[code] = {
            "date":    head["date"],
            "value":   head["value"],
            "source":  head["source"],
            "chg_1d":  (head["value"] - prev["value"]) if prev else None,
            "history": [{"date": h["date"], "value": h["value"]} for h in rs[:30]],
        }
    return {
        "generated": now_iso(),
        "source":    "Baltic indices (BCI/BDI/BPI/BSI) · daily, via BDRY",
        "rows":      len(rows),
        "data":      out if out else None,
    }


def export_analogs(con: sqlite3.Connection) -> dict:
    """K-NN analog matching — feed for the future analog panel."""
    n = fetch_count(con, "analog_outcomes")
    rows = fetch_all(con, "SELECT * FROM analog_outcomes ORDER BY rowid DESC LIMIT 200") if n else []
    return {
        "generated": now_iso(),
        "source":    "Bedrock · K-NN analog outcomes",
        "rows":      n,
        "data":      rows if rows else None,
    }


def _passthrough(name: str, src_rel: str) -> dict:
    src = Path(os.path.expanduser(f"~/bedrock/data/{src_rel}"))
    if not src.exists():
        return {
            "generated": now_iso(),
            "source":    f"Bedrock · {src_rel}",
            "rows":      0,
            "data":      None,
            "note":      f"Bedrock {src_rel} not yet present — system under development.",
        }
    try:
        payload = json.loads(src.read_text())
    except Exception as exc:
        return {
            "generated": now_iso(),
            "source":    f"Bedrock · {src_rel}",
            "rows":      0,
            "data":      None,
            "note":      f"Read error: {exc}",
        }
    if isinstance(payload, dict):
        sigs = payload.get("signals", [])
    elif isinstance(payload, list):
        sigs = payload
    else:
        sigs = []
    return {
        "generated": now_iso(),
        "source":    f"Bedrock · {src_rel} (mirrored)",
        "rows":      len(sigs) if isinstance(sigs, list) else 0,
        "raw":       payload,
    }


def export_signals_passthrough() -> dict:
    """Bedrock writes its own data/signals.json — financial scoring."""
    return _passthrough("signals.json", "signals.json")


def export_agri_signals_passthrough() -> dict:
    """Bedrock writes its own data/agri_signals.json — agri scoring."""
    return _passthrough("agri_signals.json", "agri_signals.json")


# ─────────────────────────────────────────────────────────────────────
EXPORTERS = {
    # SQLite-backed
    "prices.json":          export_prices,
    "eia_storage.json":     export_eia_storage,
    "seismic.json":         export_seismic,
    "cot_euronext.json":    export_cot_euronext,
    "ice_cot.json":         export_cot_ice,
    "comex.json":           export_comex,
    "conab.json":           export_conab,
    "unica.json":           export_unica,
    "cot_legacy.json":      export_cot_legacy,
    "cot_disagg.json":      export_cot_disagg,
    "fundamentals.json":    export_fundamentals,
    "weather.json":         export_weather,
    "crop_progress.json":   export_crop_progress,
    "wasde.json":           export_wasde,
    "bdi.json":             export_bdi,
    "shipping.json":        export_shipping,
    "analogs.json":         export_analogs,
}

# Manual-CSV exporters take no DB connection
MANUAL_EXPORTERS = {
    "news_intel.json":      export_news_intel,
    "disease_alerts.json":  export_disease_alerts,
    "export_events.json":   export_export_events,
    "ism_pmi.json":         export_ism_pmi,
    "iri_enso.json":        export_iri_enso,
    "crypto_sentiment.json": export_crypto_sent,
    "ice_cot_manual.json":  export_cot_ice_manual,
    "shipping_manual.json": export_shipping_manual,
}


def main() -> int:
    if not BEDROCK_DB.exists():
        print(f"WARN: bedrock DB not found at {BEDROCK_DB}; nothing to import.", file=sys.stderr)
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{BEDROCK_DB}?mode=ro", uri=True)
    summary = []
    for fname, fn in EXPORTERS.items():
        try:
            payload = fn(con)
            write_atomic(OUT_DIR / fname, payload)
            summary.append(f"  {fname:24s}  rows={payload.get('rows', 0)}")
        except Exception as exc:
            summary.append(f"  {fname:24s}  ERR {exc}")
    # Manual-CSV exporters (no DB connection needed)
    for fname, fn in MANUAL_EXPORTERS.items():
        try:
            payload = fn()
            write_atomic(OUT_DIR / fname, payload)
            summary.append(f"  {fname:24s}  rows={payload.get('rows', 0)}")
        except Exception as exc:
            summary.append(f"  {fname:24s}  ERR {exc}")
    # Bedrock signals passthrough (financial + agri — both are JSON arrays in bedrock)
    for fname, fn in [
        ("signals.json",      export_signals_passthrough),
        ("agri_signals.json", export_agri_signals_passthrough),
    ]:
        try:
            write_atomic(OUT_DIR / fname, fn())
            summary.append(f"  {fname:24s}  passthrough")
        except Exception as exc:
            summary.append(f"  {fname}  ERR {exc}")
    # Index file: tells the UI which exports exist + their freshness
    all_files = list(EXPORTERS.keys()) + list(MANUAL_EXPORTERS.keys()) + ["signals.json", "agri_signals.json"]
    write_atomic(
        OUT_DIR / "index.json",
        {
            "generated": now_iso(),
            "exports":   all_files,
            "bedrock_db": str(BEDROCK_DB),
        },
    )
    print(f"[bedrock-import] wrote {len(all_files)} files to {OUT_DIR}")
    for line in summary:
        print(line)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
