#!/usr/bin/env python3
"""
track_setups.py — Outcome-logging og evaluering av publiserte setups.

Leser data/signals.json (både tekniske og agri-signaler), registrerer hvert
nytt setup i data/setup_outcomes.json og evaluerer åpne setups mot 1H-OHLC
fra Yahoo Finance:

  1. Aktivering: første bar etter first_seen der low <= entry <= high
  2. Etter aktivering: traff prisen T1 eller SL først?
     - Begge i samme 1H-bar → "ambiguous" (telles konservativt som tap)
  3. TTL per horisont (matcher HORIZON_CONFIGS exit_timeout_full):
     SCALP 24t, SWING 120t, MAKRO 360t
     - Ikke aktivert innen TTL → "expired" (teller ikke i hit-rate)
     - Aktivert men uavgjort innen TTL → "timeout" (MFE/MAE logges)

Statistikk aggregeres per horisont, grade, t1_source og kilde (tech/agri) —
dette er kalibreringsgrunnlaget for nivåvekter, R:R-tiers og push-terskler.

Kjøres av update.sh etter push_signals.py. Idempotent: samme setup
(key+retning+entry+sl+t1) registreres kun én gang.

Kjøring:
    python3 track_setups.py            # registrer + evaluer + skriv stats
    python3 track_setups.py --stats    # kun print statistikk, ingen fetch
"""
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone

BASE          = os.path.expanduser("~/cot-explorer/data")
SIGNALS_FILE  = os.path.join(BASE, "signals.json")
MACRO_FILE    = os.path.join(BASE, "macro", "latest.json")
AGRI_FILE     = os.path.join(BASE, "agri_signals.json")
OUTCOMES_FILE = os.path.join(BASE, "setup_outcomes.json")

# TTL i timer per horisont — matcher scoring_config.HORIZON_CONFIGS
# exit_timeout_full (SCALP 16×15m-bekreftelsesvindu ≈ intradag → 24t).
TTL_HOURS = {"SCALP": 24, "SWING": 120, "MAKRO": 360}
DEFAULT_TTL = 120

# Yahoo-symboler. Tekniske keys matcher fetch_all.INSTRUMENTS, agri-keys
# matcher push_agri_signals (futures front-month continuous).
YAHOO_SYMBOLS = {
    "DXY": "DX-Y.NYB", "EURUSD": "EURUSD=X", "USDJPY": "JPY=X",
    "GBPUSD": "GBPUSD=X", "AUDUSD": "AUDUSD=X", "USDCHF": "CHF=X",
    "USDNOK": "NOK=X",
    "Gold": "GC=F", "Silver": "SI=F", "Brent": "BZ=F", "WTI": "CL=F",
    "SPX": "^GSPC", "NAS100": "^NDX", "VIX": "^VIX",
    "Corn": "ZC=F", "Wheat": "ZW=F", "Soybean": "ZS=F",
    "Sugar": "SB=F", "Coffee": "KC=F", "Cocoa": "CC=F", "Cotton": "CT=F",
}


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def setup_id(sig):
    return "|".join([
        str(sig.get("key", "?")), str(sig.get("action", "?")),
        f"{sig.get('entry', 0):.5f}", f"{sig.get('sl', 0):.5f}",
        f"{sig.get('t1', 0):.5f}",
    ])


# ── Evaluering (ren funksjon — testes i tests/test_track_setups.py) ──────
def evaluate_setup(direction, entry, sl, t1, bars, first_seen_ts):
    """
    Evaluerer ett setup mot OHLC-barer.

    direction: "BUY" eller "SELL"
    bars: liste av (epoch_ts, high, low) sortert stigende
    first_seen_ts: epoch — kun barer ETTER denne telles

    Returnerer dict:
      status: "pending" | "active" | "t1" | "sl" | "ambiguous"
      activated_ts, closed_ts: epoch eller None
      mfe, mae: maks favorabel/ufavorabel bevegelse fra entry (prisenheter,
                kun etter aktivering; None hvis ikke aktivert)
    """
    is_long = direction == "BUY"
    activated_ts = None
    mfe = mae = None

    for ts, high, low in bars:
        if ts is None or high is None or low is None or ts <= first_seen_ts:
            continue

        if activated_ts is None:
            if low <= entry <= high:
                activated_ts = ts
            else:
                continue
        # Aktivert (evt. samme bar): sjekk SL/T1
        hit_sl = (low <= sl) if is_long else (high >= sl)
        hit_t1 = (high >= t1) if is_long else (low <= t1)
        fav = (high - entry) if is_long else (entry - low)
        adv = (entry - low) if is_long else (high - entry)
        mfe = fav if mfe is None else max(mfe, fav)
        mae = adv if mae is None else max(mae, adv)

        if hit_sl and hit_t1:
            return {"status": "ambiguous", "activated_ts": activated_ts,
                    "closed_ts": ts, "mfe": mfe, "mae": mae}
        if hit_sl:
            return {"status": "sl", "activated_ts": activated_ts,
                    "closed_ts": ts, "mfe": mfe, "mae": mae}
        if hit_t1:
            return {"status": "t1", "activated_ts": activated_ts,
                    "closed_ts": ts, "mfe": mfe, "mae": mae}

    return {"status": "active" if activated_ts else "pending",
            "activated_ts": activated_ts, "closed_ts": None,
            "mfe": mfe, "mae": mae}


# ── Yahoo 1H OHLC ─────────────────────────────────────────────────────────
def fetch_hourly_bars(symbol, range_="1mo"):
    """Returnerer [(epoch, high, low), ...] eller [] ved feil."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?interval=1h&range={range_}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        res = d["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        return [(t, h, l) for t, h, l in zip(ts, q["high"], q["low"])
                if t and h and l]
    except Exception as e:
        print(f"  fetch FEIL {symbol}: {e}")
        return []


# ── Registrering ──────────────────────────────────────────────────────────
def load_outcomes():
    try:
        with open(OUTCOMES_FILE) as f:
            return json.load(f)
    except Exception:
        return {"schema_version": "1.0", "open": [], "closed": []}


def register_new(outcomes, signals, published_at=None):
    """Legg publiserte signaler inn som åpne setups (dedupe på setup_id).
    published_at: ISO-tid signalet ble publisert (signals.json 'generated') —
    evaluering teller barer fra publisering, ikke fra registrering."""
    known = {e["id"] for e in outcomes["open"]} | \
            {e["id"] for e in outcomes["closed"]}
    first_seen = published_at or iso(now_utc())
    added = 0
    for sig in signals:
        if not all(sig.get(k) for k in ("key", "action", "entry", "sl", "t1")):
            continue
        sid = setup_id(sig)
        if sid in known:
            continue
        outcomes["open"].append({
            "id":          sid,
            "key":         sig["key"],
            "direction":   sig["action"],
            "entry":       sig["entry"],
            "sl":          sig["sl"],
            "t1":          sig["t1"],
            "t2":          sig.get("t2"),
            "rr_t1":       sig.get("rr_t1"),
            "horizon":     sig.get("horizon", sig.get("timeframe", "?")),
            "grade":       sig.get("grade", "?"),
            "score":       sig.get("score"),
            "t1_source":   sig.get("t1_source"),
            "sl_type":     sig.get("sl_type"),
            "source":      sig.get("source", "technical"),
            "atr_d1":      sig.get("atr_d1") or sig.get("atr_est"),
            "first_seen":  first_seen,
            "status":      "pending",
        })
        known.add(sid)
        added += 1
    return added


def enrich_from_macro(outcomes):
    """Hent t1_source/entry_weight fra macro/latest.json (tekniske) og
    agri_signals.json (agri) — push_signals flater ikke ut alle setup-felter
    ved merge inn i signals.json."""
    try:
        with open(MACRO_FILE) as f:
            levels = json.load(f).get("trading_levels", {})
    except Exception:
        levels = {}
    try:
        with open(AGRI_FILE) as f:
            agri = {s.get("key"): s for s in json.load(f).get("signals", [])}
    except Exception:
        agri = {}
    for e in outcomes["open"]:
        if e.get("t1_source"):
            continue
        lvl = levels.get(e["key"], {})
        stp = lvl.get("setup_long") if e["direction"] == "BUY" \
            else lvl.get("setup_short")
        if stp and abs((stp.get("entry") or 0) - e["entry"]) < 1e-9:
            e["t1_source"]    = stp.get("t1_source")
            e["entry_weight"] = stp.get("entry_weight")
            e["t1_quality"]   = stp.get("t1_quality")
            continue
        ag = agri.get(e["key"])
        if ag and abs((ag.get("entry") or 0) - e["entry"]) < 1e-9 \
                and ag.get("action") == e["direction"]:
            e["t1_source"] = ag.get("t1_source")
            e["sl_type"]   = e.get("sl_type") or ag.get("sl_type")


# ── Evaluering av åpne setups ────────────────────────────────────────────
def evaluate_open(outcomes):
    by_key = {}
    for e in outcomes["open"]:
        by_key.setdefault(e["key"], []).append(e)

    still_open = []
    closed_now = 0
    for key, entries in by_key.items():
        symbol = YAHOO_SYMBOLS.get(key)
        bars = fetch_hourly_bars(symbol) if symbol else []
        for e in entries:
            first_seen = parse_iso(e["first_seen"])
            age_h = (now_utc() - first_seen).total_seconds() / 3600 \
                if first_seen else 0
            ttl = TTL_HOURS.get(e.get("horizon"), DEFAULT_TTL)

            if bars:
                r = evaluate_setup(e["direction"], e["entry"], e["sl"],
                                   e["t1"], bars,
                                   first_seen.timestamp() if first_seen else 0)
                e["status"] = r["status"]
                if r["activated_ts"]:
                    e["activated_at"] = iso(datetime.fromtimestamp(
                        r["activated_ts"], tz=timezone.utc))
                if r["mfe"] is not None:
                    e["mfe"] = round(r["mfe"], 5)
                    e["mae"] = round(r["mae"], 5)
                if r["status"] in ("t1", "sl", "ambiguous"):
                    e["closed_at"] = iso(datetime.fromtimestamp(
                        r["closed_ts"], tz=timezone.utc))
                    outcomes["closed"].append(e)
                    closed_now += 1
                    continue

            # TTL-håndtering
            if age_h > ttl:
                e["closed_at"] = iso(now_utc())
                e["status"] = "timeout" if e.get("activated_at") else "expired"
                outcomes["closed"].append(e)
                closed_now += 1
            else:
                still_open.append(e)

    outcomes["open"] = still_open
    return closed_now


# ── Statistikk ────────────────────────────────────────────────────────────
def build_stats(closed):
    """Hit-rate per dimensjon. 'ambiguous' telles som tap (konservativt),
    'expired' (aldri aktivert) holdes utenfor hit-rate."""
    def agg(dim):
        groups = {}
        for e in closed:
            k = str(e.get(dim) or "?")
            g = groups.setdefault(k, {"t1": 0, "sl": 0, "ambiguous": 0,
                                      "timeout": 0, "expired": 0})
            g[e["status"]] = g.get(e["status"], 0) + 1
        for k, g in groups.items():
            decided = g["t1"] + g["sl"] + g["ambiguous"]
            g["hit_rate_pct"] = round(g["t1"] / decided * 100, 1) \
                if decided else None
            g["n_decided"] = decided
        return groups

    return {
        "n_closed":     len(closed),
        "by_horizon":   agg("horizon"),
        "by_grade":     agg("grade"),
        "by_t1_source": agg("t1_source"),
        "by_source":    agg("source"),
        "by_key":       agg("key"),
    }


def print_stats(stats):
    print(f"\n── Setup-outcomes ({stats['n_closed']} lukkede) ─────────────")
    for dim in ("by_horizon", "by_grade", "by_t1_source", "by_source"):
        groups = stats.get(dim, {})
        if not groups:
            continue
        print(f"  {dim}:")
        for k, g in sorted(groups.items()):
            hr = f"{g['hit_rate_pct']}%" if g["hit_rate_pct"] is not None else "—"
            print(f"    {k:14s} T1:{g['t1']:3d} SL:{g['sl']:3d} "
                  f"amb:{g['ambiguous']:2d} timeout:{g['timeout']:2d} "
                  f"expired:{g['expired']:2d}  hit-rate:{hr}")


def main():
    stats_only = "--stats" in sys.argv
    outcomes = load_outcomes()

    if not stats_only:
        signals, published_at = [], None
        try:
            with open(SIGNALS_FILE) as f:
                sj = json.load(f)
            signals = sj.get("signals", [])
            gen = (sj.get("_meta") or {}).get("generated_at") or ""
            published_at = gen if parse_iso(gen) else None
        except Exception as e:
            print(f"Kan ikke lese {SIGNALS_FILE}: {e}")

        added = register_new(outcomes, signals, published_at)
        enrich_from_macro(outcomes)
        closed = evaluate_open(outcomes)
        outcomes["stats"] = build_stats(outcomes["closed"])
        outcomes["updated"] = iso(now_utc())
        with open(OUTCOMES_FILE, "w") as f:
            json.dump(outcomes, f, ensure_ascii=False, indent=1)
        print(f"setup_outcomes: +{added} nye, {closed} lukket, "
              f"{len(outcomes['open'])} åpne, {len(outcomes['closed'])} totalt lukket")

    print_stats(outcomes.get("stats") or build_stats(outcomes["closed"]))


if __name__ == "__main__":
    main()
