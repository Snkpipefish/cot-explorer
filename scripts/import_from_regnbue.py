#!/usr/bin/env python3
"""
import_from_regnbue.py — read-only import from the Regnbue setup-generator
(~/prosjekter/setups) into ~/cot-explorer/data/regnbue/*.json snapshots that
the dashboard consumes. Regnbue is an upstream producer; we never write back
to its source tree.

Regnbue publishes web/data/setups.json (base-rate-validated setups with
entry/SL/TP on the Skilling feed) + web/data/scenario_models.json. We mirror
both behind a {generated, source, rows, raw} wrapper so the dashboard can show
freshness even when the source is missing.

Run via cot-explorer's update.sh.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REGNBUE_DATA = Path(os.environ.get(
    "REGNBUE_DATA", os.path.expanduser("~/prosjekter/setups/web/data")))
OUT_DIR = Path(os.environ.get(
    "REGNBUE_EXPORT", os.path.expanduser("~/cot-explorer/data/regnbue")))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.replace(path)


def mirror(filename: str, source_label: str) -> dict:
    src = REGNBUE_DATA / filename
    if not src.exists():
        return {
            "generated": now_iso(),
            "source": source_label,
            "rows": 0,
            "raw": None,
            "note": f"Regnbue {filename} not present at {src}",
        }
    try:
        payload = json.loads(src.read_text())
    except Exception as exc:
        return {
            "generated": now_iso(),
            "source": source_label,
            "rows": 0,
            "raw": None,
            "note": f"Read error: {exc}",
        }
    sigs = payload.get("signals", []) if isinstance(payload, dict) else []
    return {
        "generated": now_iso(),
        "source": source_label,
        "as_of": payload.get("as_of") if isinstance(payload, dict) else None,
        "rows": len(sigs) if isinstance(sigs, list) else 0,
        "raw": payload,
    }


EXPORTS = {
    "setups.json": "Regnbue · base-rate-validated setups (Skilling-feed)",
    "scenario_models.json": "Regnbue · scenario calibration (per-instrument)",
}


def main() -> int:
    if not REGNBUE_DATA.exists():
        print(f"WARN: regnbue data dir not found at {REGNBUE_DATA}; nothing to import.",
              file=sys.stderr)
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = []
    for fname, label in EXPORTS.items():
        try:
            payload = mirror(fname, label)
            write_atomic(OUT_DIR / fname, payload)
            summary.append(f"  {fname:24s}  rows={payload.get('rows', 0)}")
        except Exception as exc:
            summary.append(f"  {fname:24s}  ERR {exc}")
    write_atomic(
        OUT_DIR / "index.json",
        {
            "generated": now_iso(),
            "exports": list(EXPORTS.keys()),
            "regnbue_data": str(REGNBUE_DATA),
        },
    )
    print(f"[regnbue-import] wrote {len(EXPORTS) + 1} files to {OUT_DIR}")
    for line in summary:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
