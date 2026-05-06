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

BEDROCK_DB = Path(os.environ.get("BEDROCK_DB", os.path.expanduser("~/bedrock/bedrock.db")))
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
        tail = [{"date": x["date"], "value": x["value"]} for x in rs[:26]]  # 26w
        prev = rs[1] if len(rs) > 1 else None
        chg = (head["value"] - prev["value"]) if prev and prev["value"] is not None else None
        latest[sid] = {
            "date":    head["date"],
            "value":   head["value"],
            "units":   head["units"],
            "chg_1w": chg,
            "history": list(reversed(tail)),
        }
    return {
        "generated": now_iso(),
        "source":    "EIA · weekly petroleum + natural-gas storage",
        "rows":      len(rows),
        "series_count": len(by_series),
        "data":      latest if latest else None,
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
    n = fetch_count(con, "crop_progress")
    rows = (
        fetch_all(
            con,
            "SELECT * FROM crop_progress ORDER BY report_date DESC LIMIT 200",
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


def export_signals_passthrough() -> dict:
    """Bedrock writes its own data/signals.json — copy it through if present."""
    src = Path(os.path.expanduser("~/bedrock/data/signals.json"))
    if not src.exists():
        return {
            "generated": now_iso(),
            "source":    "Bedrock · signals.json",
            "rows":      0,
            "data":      None,
            "note":      "Bedrock signals.json not yet present — system under development.",
        }
    try:
        payload = json.loads(src.read_text())
    except Exception as exc:
        return {
            "generated": now_iso(),
            "source":    "Bedrock · signals.json",
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
        "source":    "Bedrock · signals.json (mirrored)",
        "rows":      len(sigs) if isinstance(sigs, list) else 0,
        "raw":       payload,
    }


# ─────────────────────────────────────────────────────────────────────
EXPORTERS = {
    "eia_storage.json":     export_eia_storage,
    "seismic.json":         export_seismic,
    "cot_euronext.json":    export_cot_euronext,
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
    "analogs.json":         export_analogs,
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
    # Bedrock signals.json passthrough (no DB read)
    try:
        write_atomic(OUT_DIR / "signals.json", export_signals_passthrough())
        summary.append(f"  {'signals.json':24s}  passthrough")
    except Exception as exc:
        summary.append(f"  signals.json  ERR {exc}")
    # Index file: tells the UI which exports exist + their freshness
    write_atomic(
        OUT_DIR / "index.json",
        {
            "generated": now_iso(),
            "exports":   list(EXPORTERS.keys()) + ["signals.json"],
            "bedrock_db": str(BEDROCK_DB),
        },
    )
    print(f"[bedrock-import] wrote {len(EXPORTERS) + 1} files to {OUT_DIR}")
    for line in summary:
        print(line)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
