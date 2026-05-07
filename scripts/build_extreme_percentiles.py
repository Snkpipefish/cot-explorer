#!/usr/bin/env python3
"""
Build a percentile snapshot for every COT timeseries file.

The curated `data/cot_analytics/latest.json` only covers ~14 hand-picked
benchmarks (EURUSD, Gold, WTI, etc.). The Positions tab has 123 markets,
so the rest show "—" and never get an interpretation tag. This script
computes a coarser fallback — 52w / 156w / all-time percentile of the
current spec_net plus a derived change_oi_4w_avg — for every market the
timeseries pipeline has already produced, keyed by `{symbol}_{report}`.

The dashboard's `_lookupAnalytics()` falls back to this file when
cot_analytics has no entry for a market, so the OI-regime / divergence-z
fields stay populated only for the 14 curated names while the simpler
percentile fields cover all 123.

Output: data/extremes/latest.json
"""

import bisect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TS_DIR = ROOT / "data" / "timeseries"
OUT_DIR = ROOT / "data" / "extremes"
OUT_FILE = OUT_DIR / "latest.json"


def percentile_rank(values: list[float], target: float) -> float:
    """Return the percentile rank (0–100) of `target` within `values`.

    Uses the average-rank convention (mean of strict-less and
    less-or-equal counts), which is what scipy's `percentileofscore`
    with kind='mean' does. Stable when there are ties at the value.
    """
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    lo = bisect.bisect_left(s, target)
    hi = bisect.bisect_right(s, target)
    rank = (lo + hi) / 2.0
    return round(100.0 * rank / max(1, n - 1) if n > 1 else 50.0, 1)


def freshness(latest_date: str) -> str:
    """Mirror the same staleness gate used by cot_analytics."""
    try:
        d = datetime.fromisoformat(latest_date).replace(tzinfo=timezone.utc)
    except Exception:
        return "unknown"
    age_d = (datetime.now(tz=timezone.utc) - d).total_seconds() / 86400.0
    if age_d < 11:
        return "fresh"
    if age_d < 18:
        return "aging"
    return "stale"


def process_file(path: Path) -> tuple[str, dict] | None:
    try:
        with path.open() as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    # The directory also contains an index.json that is a bare list; skip
    # anything that isn't the per-market doc shape (`{symbol, ..., data}`).
    if not isinstance(doc, dict):
        return None
    rows = doc.get("data") or []
    if not rows:
        return None

    series = [r for r in rows if r.get("spec_net") is not None and r.get("date")]
    if len(series) < 8:        # too short to say anything meaningful
        return None

    series.sort(key=lambda r: r["date"])
    latest = series[-1]
    target = latest["spec_net"]

    spec_hist = [r["spec_net"] for r in series]
    pctile_at = percentile_rank(spec_hist, target)
    pctile_52 = percentile_rank([r["spec_net"] for r in series[-52:]], target)
    pctile_156 = percentile_rank([r["spec_net"] for r in series[-156:]], target)

    # Derive change_oi values from the OI series — needed so the OI-regime
    # readout in the dashboard isn't gated on the 14 curated markets.
    oi_hist = [r.get("oi") for r in series if r.get("oi") is not None]
    change_oi_current = None
    change_oi_4w_avg = None
    if len(oi_hist) >= 5:
        deltas = [oi_hist[i] - oi_hist[i - 1] for i in range(1, len(oi_hist))]
        change_oi_current = deltas[-1]
        last4 = deltas[-4:]
        change_oi_4w_avg = round(sum(last4) / len(last4), 1)

    # Stem maps to the timeseries naming convention used everywhere else
    # in this repo: {symbol}_{report} (e.g. "099741_tff", "088691_disaggregated").
    key = path.stem
    out = {
        "cot_date": latest["date"],
        "report_type": doc.get("report"),
        "symbol": doc.get("symbol"),
        "market": doc.get("market"),
        "mm_net": target,
        "mm_net_pctile_52w": pctile_52,
        "mm_net_pctile_156w": pctile_156,
        "mm_net_pctile_alltime": pctile_at,
        "oi_now": latest.get("oi"),
        "change_oi_current": change_oi_current,
        "change_oi_4w_avg": change_oi_4w_avg,
        "history_weeks": len(series),
        "data_quality": freshness(latest["date"]),
    }
    return key, out


def main() -> int:
    if not TS_DIR.exists():
        print(f"timeseries dir missing: {TS_DIR}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assets: dict[str, dict] = {}
    skipped = 0
    latest_cot_date = ""
    for path in sorted(TS_DIR.glob("*.json")):
        result = process_file(path)
        if result is None:
            skipped += 1
            continue
        key, payload = result
        assets[key] = payload
        if payload["cot_date"] > latest_cot_date:
            latest_cot_date = payload["cot_date"]

    out = {
        "generated": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cot_date": latest_cot_date,
        "asset_count": len(assets),
        "skipped": skipped,
        "assets": assets,
    }
    OUT_FILE.write_text(json.dumps(out, separators=(",", ":")))
    print(
        f"extremes: wrote {len(assets)} assets "
        f"(skipped {skipped}) → {OUT_FILE.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
