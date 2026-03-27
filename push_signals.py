#!/usr/bin/env python3
"""
push_signals.py — Les data/macro/latest.json og push topp-setups

Kjøres ALLTID (ikke gated av env-variabler).
Skriver alltid: data/signals.json (GitHub Pages bot) og data/signal_log.json (historikk).

Miljøvariabler (valgfritt):
  TELEGRAM_TOKEN   + TELEGRAM_CHAT_ID  → Telegram-bot
  DISCORD_WEBHOOK                      → Discord webhook
  PUSH_MIN_SCORE   = 7                 → minimum score for å pushe (default 7)
  PUSH_MAX_SIGNALS = 5                 → maks antall signaler per kjøring
  FLASK_URL        = http://localhost:5000  → signal_server.py for /push-alert
  SCALP_API_KEY                        → API-nøkkel til Flask-server
"""

import os
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

# ── Konfigurasjon ─────────────────────────────────────────
BASE          = Path(__file__).parent
DATA_FILE     = BASE / "data" / "macro" / "latest.json"
SIGNAL_LOG    = BASE / "data" / "signal_log.json"
SIGNALS_OUT   = BASE / "data" / "signals.json"
MIN_SCORE     = int(os.environ.get("PUSH_MIN_SCORE",   "7"))
MAX_SIGNALS   = int(os.environ.get("PUSH_MAX_SIGNALS", "5"))
TG_TOKEN      = os.environ.get("TELEGRAM_TOKEN",  "")
TG_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID","")
DC_WEBHOOK    = os.environ.get("DISCORD_WEBHOOK", "")
FLASK_URL     = os.environ.get("FLASK_URL",       "http://localhost:5000")
SCALP_API_KEY = os.environ.get("SCALP_API_KEY",   "")

# Fallback: les SCALP_API_KEY fra ~/.bashrc hvis ikke i shell-miljøet
if not SCALP_API_KEY:
    bashrc = Path.home() / ".bashrc"
    if bashrc.exists():
        for line in bashrc.read_text().splitlines():
            if line.startswith("export SCALP_API_KEY="):
                SCALP_API_KEY = line.split("=", 1)[1].strip().strip('"\'')
                break

# ── Hent data ─────────────────────────────────────────────
if not DATA_FILE.exists():
    print(f"FEIL: {DATA_FILE} finnes ikke — kjør fetch_all.py først")
    sys.exit(1)

with open(DATA_FILE) as f:
    macro = json.load(f)

levels    = macro.get("trading_levels", {})
vix_price = (macro.get("prices") or {}).get("VIX", {}).get("price", 20)
generated = macro.get("date", "ukjent")
cot_date  = macro.get("cot_date", "")


# ── Aktiv setup basert på retning ─────────────────────────
def active_setup(d):
    return d.get("setup_long") if d.get("dir_color") == "bull" else d.get("setup_short")


# ── Filtrer og sorter ──────────────────────────────────────
def score_key(item):
    _, d = item
    tf_rank = {"MAKRO": 3, "SWING": 2, "SCALP": 1, "WATCHLIST": 0}
    return (tf_rank.get(d.get("timeframe_bias", "WATCHLIST"), 0), d.get("score", 0))

candidates = [
    (key, d) for key, d in levels.items()
    if d.get("score", 0) >= MIN_SCORE
    and d.get("dir_color") in ("bull", "bear")
    and active_setup(d) is not None
]
candidates.sort(key=score_key, reverse=True)
top = candidates[:MAX_SIGNALS]


# ── Skriv data/signals.json (alltid, for GitHub Pages bots) ─
now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
signals_json = {
    "generated": now_ts,
    "cot_date":  cot_date,
    "signals":   [],
}
for key, d in top:
    setup = active_setup(d)
    if not setup:
        continue
    p   = 5 if (d.get("current") or 0) < 100 else 2
    cot = d.get("cot", {})
    signals_json["signals"].append({
        "key":      key,
        "name":     d.get("name", key),
        "action":   "BUY" if d.get("dir_color") == "bull" else "SELL",
        "timeframe":d.get("timeframe_bias", "SWING"),
        "grade":    d.get("grade", "?"),
        "score":    d.get("score", 0),
        "current":  d.get("current"),
        "entry":    setup.get("entry"),
        "sl":       setup.get("sl"),
        "t1":       setup.get("t1"),
        "t2":       setup.get("t2"),
        "rr_t1":    setup.get("rr_t1"),
        "rr_t2":    setup.get("rr_t2"),
        "sl_type":  setup.get("sl_type"),
        "cot_bias": cot.get("bias"),
        "cot_pct":  cot.get("pct"),
    })

SIGNALS_OUT.parent.mkdir(parents=True, exist_ok=True)
with open(SIGNALS_OUT, "w") as f:
    json.dump(signals_json, f, ensure_ascii=False, indent=2)
print(f"signals.json → {len(signals_json['signals'])} signaler (score>={MIN_SCORE}/12)")

if not top:
    print(f"Ingen signaler med score >= {MIN_SCORE} og aktiv setup")
    sys.exit(0)


# ── Signal-logg ───────────────────────────────────────────
MAX_LOG_ENTRIES = 500


def load_signal_log():
    if SIGNAL_LOG.exists():
        try:
            with open(SIGNAL_LOG) as f:
                return json.load(f)
        except Exception:
            pass
    return {"entries": [], "hit_stats": {}}


def save_signal_log(log):
    SIGNAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SIGNAL_LOG, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def evaluate_previous_signals(log):
    """
    Evaluer eldre signaler mot nåpris.
    HIT: BUY + pris > entry, eller SELL + pris < entry.
    PENDING: signal yngre enn 20 timer.
    """
    for entry in log.get("entries", []):
        if entry.get("result") in ("HIT", "MISS"):
            continue  # allerede evaluert
        sig = entry.get("signal", {})
        # Finn nåpris via key_orig (original case) eller key
        lv = levels.get(sig.get("key_orig")) or levels.get(sig.get("key", "").upper())
        if not lv:
            for k, v in levels.items():
                if k.lower() == sig.get("key", "").lower():
                    lv = v
                    break
        if not lv:
            continue
        curr = lv.get("current")
        entry_price = sig.get("entry")
        action      = sig.get("action")
        if not curr or not entry_price or not action:
            continue
        try:
            sig_time = datetime.fromisoformat(
                entry.get("timestamp", "").replace(" UTC", "+00:00"))
            age_h = (datetime.now(timezone.utc) - sig_time).total_seconds() / 3600
            if age_h < 20:
                entry["result"] = "PENDING"
                continue
        except Exception:
            pass
        if action == "BUY"  and curr > entry_price:
            entry["result"] = "HIT"
        elif action == "SELL" and curr < entry_price:
            entry["result"] = "HIT"
        else:
            entry["result"] = "MISS"


def calc_hit_stats(log):
    stats = {"total": {"hits": 0, "misses": 0, "n": 0, "rate": None}, "by_grade": {}}
    for entry in log.get("entries", []):
        result = entry.get("result")
        if result not in ("HIT", "MISS"):
            continue
        grade = entry.get("signal", {}).get("grade", "?")
        is_hit = result == "HIT"
        stats["total"]["hits"]   += int(is_hit)
        stats["total"]["misses"] += int(not is_hit)
        bg = stats["by_grade"].setdefault(grade, {"hits": 0, "misses": 0})
        bg["hits"]   += int(is_hit)
        bg["misses"] += int(not is_hit)
    t  = stats["total"]
    t["n"] = t["hits"] + t["misses"]
    if t["n"] > 0:
        t["rate"] = round(t["hits"] / t["n"] * 100, 1)
    for g, gs in stats["by_grade"].items():
        ng = gs["hits"] + gs["misses"]
        gs["n"]    = ng
        gs["rate"] = round(gs["hits"] / ng * 100, 1) if ng > 0 else None
    return stats


signal_log = load_signal_log()
evaluate_previous_signals(signal_log)

new_entries = []
for key, d in top:
    setup = active_setup(d)
    if not setup:
        continue
    cot = d.get("cot", {})
    new_entries.append({
        "timestamp": now_ts,
        "result":    None,
        "signal": {
            "key_orig": key,
            "key":      key.upper(),
            "name":     d.get("name", key),
            "action":   "BUY" if d.get("dir_color") == "bull" else "SELL",
            "timeframe":d.get("timeframe_bias", "SWING"),
            "grade":    d.get("grade", "?"),
            "score":    d.get("score", 0),
            "entry":    setup.get("entry"),
            "sl":       setup.get("sl"),
            "t1":       setup.get("t1"),
            "rr_t1":    setup.get("rr_t1"),
            "cot_bias": cot.get("bias"),
        },
    })

signal_log["entries"] = (new_entries + signal_log.get("entries", []))[:MAX_LOG_ENTRIES]
signal_log["hit_stats"]    = calc_hit_stats(signal_log)
signal_log["last_updated"] = now_ts
save_signal_log(signal_log)
stats_t = signal_log["hit_stats"]["total"]
print(f"signal_log.json → {len(signal_log['entries'])} oppføringer  "
      f"treffsikkerhet: {stats_t.get('rate','?')}%  (n={stats_t.get('n',0)})")


# ── Formater melding ───────────────────────────────────────
def fmt_signal(key, d):
    direction = "LONG  ▲" if d.get("dir_color") == "bull" else "SHORT ▼"
    tf        = d.get("timeframe_bias", "SWING")
    grade     = d.get("grade", "?")
    score     = d.get("score", 0)
    curr      = d.get("current", 0)
    p         = 5 if curr < 100 else 2
    cot       = d.get("cot", {})
    cot_str   = f"{cot.get('bias','?')} {cot.get('momentum','')} ({cot.get('pct',0):.1f}%)"
    pos_size  = d.get("pos_size", "?")
    setup     = active_setup(d)

    lines = [
        f"── {d.get('name', key)} [{tf}] ──",
        f"{direction}  {grade}({score}/12)  VIX:{vix_price:.1f} → {pos_size}",
    ]
    if setup:
        risk_desc = f"{setup.get('risk_atr_d','?')}×ATRd ({setup.get('sl_type','?')} SL)"
        lines += [
            f"Entry: {round(setup['entry'], p)}  [{setup.get('t1_source','?')}]",
            f"SL:    {round(setup['sl'], p)}  ({risk_desc})",
            f"T1:    {round(setup['t1'], p)}  R:R {setup.get('rr_t1','?')}",
        ]
        if setup.get("t2"):
            lines.append(f"T2:    {round(setup['t2'], p)}  R:R {setup.get('rr_t2','?')}")
    else:
        nearest = d.get("supports" if d.get("dir_color") == "bull" else "resistances", [])
        if nearest:
            n = nearest[0]
            lines.append(f"Nearest: {n['level']} [{n['name']}]  ({n['dist_atr']:.1f}×ATR unna)")
        lines.append("Ingen aktiv setup — watchlist")
    lines += [
        f"COT:   {cot_str}",
        f"SMA200: {d.get('sma200_pos','?')}  | Chg20d: {d.get('chg20d',0):+.1f}%",
    ]
    for ev in d.get("binary_risk", [])[:2]:
        lines.append(f"⚠️  EVENT: {ev.get('title','')} kl {ev.get('cet','?')}")
    return "\n".join(lines)


def build_message():
    ts    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"📊 COT Explorer  |  {ts}", f"Data: {generated}", ""]
    for key, d in top:
        lines.append(fmt_signal(key, d))
        lines.append("")
    return "\n".join(lines).strip()


message = build_message()
print(message)
print()


# ── Push til Telegram ─────────────────────────────────────
def push_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    url     = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id":    TG_CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Telegram OK ({resp.status})")
    except urllib.error.URLError as e:
        print(f"Telegram FEIL: {e}")


# ── Push til Discord ──────────────────────────────────────
def push_discord(text):
    if not DC_WEBHOOK:
        return
    payload = json.dumps({"content": f"```\n{text}\n```"}).encode()
    req = urllib.request.Request(DC_WEBHOOK, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Discord OK ({resp.status})")
    except urllib.error.URLError as e:
        print(f"Discord FEIL: {e}")


# ── Push til Flask /push-alert ────────────────────────────
def push_flask(signals):
    if not SCALP_API_KEY:
        return
    url     = f"{FLASK_URL}/push-alert"
    payload = json.dumps({"signals": signals, "generated": generated}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "X-API-Key": SCALP_API_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Flask /push-alert OK ({resp.status})")
    except urllib.error.URLError as e:
        print(f"Flask FEIL: {e}")


# ── Kjør pushes ───────────────────────────────────────────
push_telegram(message)
push_discord(message)
push_flask([{
    "key":            key,
    "name":           d.get("name", key),
    "timeframe_bias": d.get("timeframe_bias", "SWING"),
    "direction":      d.get("dir_color", "?"),
    "grade":          d.get("grade", "?"),
    "score":          d.get("score", 0),
    "setup":          active_setup(d),
    "cot":            d.get("cot", {}),
} for key, d in top])
