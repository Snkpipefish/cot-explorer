#!/usr/bin/env python3
"""
push_signals.py — Les data/macro.json og push topp-setups til Telegram / Discord

Miljøvariabler:
  TELEGRAM_TOKEN   + TELEGRAM_CHAT_ID  → Telegram-bot
  DISCORD_WEBHOOK                      → Discord webhook
  PUSH_MIN_SCORE   = 5                 → minimum score for å pushe (default 5)
  PUSH_MAX_SIGNALS = 5                 → maks antall signaler per kjøring
  FLASK_URL        = http://localhost:5000  → signal_server.py for /push-alert
  SCALP_API_KEY                        → API-nøkkel til Flask-server

Støtter begge plattformer samtidig (pusher til alle som er konfigurert).
"""

import os
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

# ── Konfigurasjon ─────────────────────────────────────────
BASE           = Path(__file__).parent
DATA_FILE      = BASE / "data" / "macro" / "latest.json"
MIN_SCORE      = int(os.environ.get("PUSH_MIN_SCORE",   "7"))
MAX_SIGNALS    = int(os.environ.get("PUSH_MAX_SIGNALS", "5"))
TG_TOKEN       = os.environ.get("TELEGRAM_TOKEN",  "")
TG_CHAT_ID     = os.environ.get("TELEGRAM_CHAT_ID","")
DC_WEBHOOK     = os.environ.get("DISCORD_WEBHOOK", "")
FLASK_URL      = os.environ.get("FLASK_URL",       "http://localhost:5000")
SCALP_API_KEY  = os.environ.get("SCALP_API_KEY",   "")

# ── Hent data ─────────────────────────────────────────────
if not DATA_FILE.exists():
    print(f"FEIL: {DATA_FILE} finnes ikke — kjør fetch_all.py først")
    sys.exit(1)

with open(DATA_FILE) as f:
    macro = json.load(f)

levels    = macro.get("trading_levels", {})
vix_price = (macro.get("prices") or {}).get("VIX", {}).get("price", 20)
generated = macro.get("date", "ukjent")

# ── Filtrer og sorter signaler ────────────────────────────
def score_key(item):
    _, d = item
    # Prioriter: MAKRO > SWING > SCALP, deretter score
    tf_rank = {"MAKRO": 3, "SWING": 2, "SCALP": 1, "WATCHLIST": 0}
    return (tf_rank.get(d.get("timeframe_bias", "WATCHLIST"), 0), d.get("score", 0))

candidates = [
    (key, d) for key, d in levels.items()
    if d.get("score", 0) >= MIN_SCORE
    and d.get("dir_color") in ("bull", "bear")   # bare klare retninger
]
candidates.sort(key=score_key, reverse=True)
top = candidates[:MAX_SIGNALS]

if not top:
    print(f"Ingen signaler med score >= {MIN_SCORE}")
    sys.exit(0)

# ── Formater signal-kort ──────────────────────────────────
def fmt_signal(key, d):
    direction  = "LONG  ▲" if d.get("dir_color") == "bull" else "SHORT ▼"
    tf         = d.get("timeframe_bias", "SWING")
    grade      = d.get("grade", "?")
    score      = d.get("score", 0)
    curr       = d.get("current", 0)
    p          = 5 if curr < 100 else 2
    cot        = d.get("cot", {})
    cot_str    = f"{cot.get('bias','?')} {cot.get('momentum','')} ({cot.get('pct',0):.1f}%)"
    sma_pos    = d.get("sma200_pos", "?")
    pos_size   = d.get("pos_size", "?")

    active_setup = d.get("setup_long") if d.get("dir_color") == "bull" else d.get("setup_short")

    lines = [
        f"── {d.get('name', key)} [{tf}] ──",
        f"{direction}  {grade}({score}/12)  VIX:{vix_price:.1f} → {pos_size}",
    ]

    if active_setup:
        risk_desc = f"{active_setup.get('risk_atr_d','?')}×ATRd ({active_setup.get('sl_type','?')} SL)"
        lines += [
            f"Entry: {round(active_setup['entry'], p)}  [{active_setup.get('t1_source','?')}]",
            f"SL:    {round(active_setup['sl'], p)}  ({risk_desc})",
            f"T1:    {round(active_setup['t1'], p)}  R:R {active_setup.get('rr_t1','?')}",
        ]
        if active_setup.get("t2"):
            lines.append(f"T2:    {round(active_setup['t2'], p)}  R:R {active_setup.get('rr_t2','?')}")
    else:
        nearest = d.get("supports" if d.get("dir_color") == "bull" else "resistances", [])
        if nearest:
            n = nearest[0]
            lines.append(f"Nearest: {n['level']} [{n['name']}]  ({n['dist_atr']:.1f}×ATR unna)")
        lines.append("Ingen aktiv setup — watchlist")

    lines += [
        f"COT:   {cot_str}",
        f"SMA200: {sma_pos}  | Chg20d: {d.get('chg20d',0):+.1f}%",
    ]

    events = d.get("binary_risk", [])
    for ev in events[:2]:
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

# ── Skriv ren signals.json for trading-bot ────────────────
SIGNALS_FILE = BASE / "data" / "signals.json"

def build_signal_record(key, d):
    is_long  = d.get("dir_color") == "bull"
    action   = "BUY" if is_long else "SELL"
    setup    = d.get("setup_long") if is_long else d.get("setup_short")
    curr     = d.get("current", 0)
    p        = 5 if curr < 100 else 2
    cot      = d.get("cot", {})
    rec = {
        "key":       key,
        "name":      d.get("name", key),
        "action":    action,
        "timeframe": d.get("timeframe_bias", "SWING"),
        "grade":     d.get("grade", "?"),
        "score":     d.get("score", 0),
        "current":   curr,
        "cot_bias":  cot.get("bias", "?"),
        "cot_pct":   round(cot.get("pct", 0), 1),
    }
    if setup:
        rec["entry"]   = round(setup.get("entry", 0), p)
        rec["sl"]      = round(setup.get("sl", 0), p)
        rec["t1"]      = round(setup.get("t1", 0), p)
        rec["t2"]      = round(setup.get("t2", 0), p) if setup.get("t2") else None
        rec["rr_t1"]   = setup.get("rr_t1")
        rec["rr_t2"]   = setup.get("rr_t2")
        rec["sl_type"] = setup.get("sl_type", "structural")
    return rec

signals_out = {
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "cot_date":  generated,
    "signals":   [build_signal_record(key, d) for key, d in top],
}
with open(SIGNALS_FILE, "w") as f:
    json.dump(signals_out, f, ensure_ascii=False, indent=2)
print(f"→ {SIGNALS_FILE} ({len(top)} signaler)")

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
push_flask(signals_out["signals"])
