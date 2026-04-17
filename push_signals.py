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
from datetime import datetime, timezone, timedelta

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
SCALP_ONLY    = "--scalp-only" in sys.argv  # Hourly: kun SCALP-signaler

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

# ── Freshness-sjekk: advarer om stale data ────────────────
def _check_freshness(filepath, max_age_hours, label):
    """Sjekk om en datafil er for gammel."""
    try:
        p = Path(filepath)
        if not p.exists():
            print(f"  ⚠️  {label}: fil mangler ({filepath})")
            return False
        age_h = (datetime.now(timezone.utc) - datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)).total_seconds() / 3600
        if age_h > max_age_hours:
            print(f"  ⚠️  {label}: {age_h:.0f}t gammel (maks {max_age_hours}t)")
            return False
        return True
    except Exception:
        return True

_check_freshness(DATA_FILE, 6, "macro/latest.json")
_check_freshness(BASE / "data" / "shipping" / "latest.json", 24, "shipping data")
_check_freshness(BASE / "data" / "oilgas" / "latest.json", 24, "oilgas data")
_check_freshness(BASE / "data" / "fundamentals" / "latest.json", 48, "fundamentals data")


# ── Aktiv setup basert på retning ─────────────────────────
def active_setup(d):
    return d.get("setup_long") if d.get("dir_color") == "bull" else d.get("setup_short")


from scoring_config import (
    PUSH_THRESHOLDS, HORIZON_PRIORITY, HORIZON_CONFIGS,
    CORRELATION_GROUPS, CORRELATION_REGIME_CONFIGS, VIX_CORRELATION_THRESHOLDS,
    AGRI_CORRELATION_SUBGROUPS,
)


def should_push(d):
    horizon = d.get("horizon", d.get("timeframe_bias", "WATCHLIST"))
    if horizon == "WATCHLIST":
        return False
    if d.get("dir_color") not in ("bull", "bear"):
        return False
    setup = active_setup(d)
    if not setup:
        return False
    threshold = PUSH_THRESHOLDS.get(horizon, 999)
    if d.get("score", 0) < threshold:
        return False
    # Signal aging: avvis hvis pris har beveget seg for langt fra entry
    current = d.get("current")
    entry = setup.get("entry")
    atr = d.get("atr_daily") or d.get("atr14")  # Prioriter D1 ATR for signal aging
    if current and entry and atr and atr > 0:
        dist = abs(current - entry) / atr
        max_dist = {"SCALP": 1.5, "SWING": 2.5, "MAKRO": 4.0}.get(horizon, 2.5)
        if dist > max_dist:
            return False
    return True


candidates = [
    (key, d) for key, d in levels.items()
    if should_push(d) and key not in ("DXY",)
    and (not SCALP_ONLY or d.get("horizon") == "SCALP")
]
candidates.sort(key=lambda item: (
    HORIZON_PRIORITY.get(item[1].get("horizon", "WATCHLIST"), 3),
    -item[1].get("score", 0),
))
top = candidates[:MAX_SIGNALS]


# ── Detect oil war-spread premium ───────────────────────────
brent      = (macro.get("prices") or {}).get("Brent") or {}
brent_20d  = brent.get("chg20d", 0) or 0
sentiment  = macro.get("sentiment") or {}
news       = sentiment.get("news") or {}
headlines  = " ".join(h.get("headline","") for h in news.get("key_drivers",[]))
WAR_WORDS  = ("iran","israel","attack","war","strike","sanction","invasion","escalat")
geo_news   = any(w in headlines.lower() for w in WAR_WORDS)
geo_active = geo_news or (brent_20d > 15)
oil_geo    = geo_active or (brent_20d > 10)
oil_reason = []
if brent_20d > 10:  oil_reason.append(f"Brent +{brent_20d:.0f}% 20d")
if geo_news:        oil_reason.append("krig/angrep i nyheter")
oil_warn_str = " · ".join(oil_reason) if oil_reason else ""

vix_obj    = macro.get("vix_regime") or {}
vix_regime = vix_obj.get("regime", "normal")

# ── Korrelasjons-regime basert på VIX-nivå ────────────────────
_vix_val = vix_price or 20
if _vix_val >= VIX_CORRELATION_THRESHOLDS.get("crisis", 35):
    corr_regime = "crisis"
elif _vix_val >= VIX_CORRELATION_THRESHOLDS.get("risk_off", 25):
    corr_regime = "risk_off"
else:
    corr_regime = "normal"
corr_config = CORRELATION_REGIME_CONFIGS[corr_regime]

# ── Olje supply-disruption: blokkér SHORT på olje ─────────────
# Leser fra trading_levels (satt av fetch_all.py fra shipping/oilgas data)
_oil_disruption = False
for _okey in ("Brent", "WTI"):
    _olevel = levels.get(_okey, {})
    if _olevel.get("oil_supply_disruption"):
        _oil_disruption = True
        _oil_reasons = _olevel.get("oil_supply_reason", [])
        print(f"  ⛽ Supply-disruption aktiv for {_okey}: {', '.join(_oil_reasons)}")
        print(f"     → SHORT-signaler på olje blokkeres")

# ── Skriv data/signals.json (alltid, for GitHub Pages bots) ─
now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
signals_json = {
    "generated": now_ts,
    "cot_date":  cot_date,
    "global_state": {
        "geo_active":        geo_active,
        "vix_regime":        vix_regime,
        "oil_geo_warning":   oil_geo,
        "oil_warning_reason": oil_warn_str,
    },
    "rules": {
        "risk_pct_full":           1.0,
        "risk_pct_half":           0.5,
        "risk_pct_quarter":        0.25,
        "geo_spike_atr_multiplier": 2.0,
        "oil_max_spread_mult":     3.0,
        "oil_min_sl_pips":         25,
    },
    "signals":   [],
    "_meta": {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "script": "push_signals.py",
        "macro_date": generated,
        "cot_date": cot_date,
    },
}
for key, d in top:
    setup = active_setup(d)
    if not setup:
        continue
    # Blokkér olje SHORT ved supply-disruption
    if _oil_disruption and key in ("Brent", "WTI") and d.get("dir_color") == "bear":
        print(f"  ⛽ {key} SHORT blokkert — supply-disruption aktiv")
        continue
    p   = 5 if (d.get("current") or 0) < 100 else 2
    cot = d.get("cot", {})
    horizon = d.get("horizon", d.get("timeframe_bias", "SWING"))
    signals_json["signals"].append({
        "key":      key,
        "name":     d.get("name", key),
        "action":   "BUY" if d.get("dir_color") == "bull" else "SELL",
        "timeframe": horizon,
        "horizon":   horizon,
        "grade":    d.get("grade", "?"),
        "score":    d.get("score", 0),
        "max_score": d.get("max_score", 14),
        "score_pct": d.get("score_pct", 0),
        "score_details": d.get("score_details", {}),
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
        "correlation_group": d.get("correlation_group"),
        "adr_utilization":   d.get("adr_utilization"),
        "atr_d1":            d.get("atr_daily"),
        "horizon_config":    HORIZON_CONFIGS.get(horizon, {}),
    })

# ── Merge agri-signaler inn i signals.json ────────────────
AGRI_SIGNALS_FILE = BASE / "data" / "agri_signals.json"
agri_merged = 0
if AGRI_SIGNALS_FILE.exists():
    try:
        with open(AGRI_SIGNALS_FILE) as _af:
            agri_data = json.load(_af)
        for asig in agri_data.get("signals", []):
            horizon = asig.get("timeframe", "SWING")
            signals_json["signals"].append({
                "key":       asig.get("key", ""),
                "name":      asig.get("name", asig.get("key", "")),
                "action":    asig.get("action", "BUY"),
                "timeframe": horizon,
                "horizon":   horizon,
                "grade":     asig.get("grade", "C"),
                "score":     asig.get("score", 0),
                "max_score": 10,
                "current":   asig.get("current"),
                "entry":     asig.get("entry"),
                "sl":        asig.get("sl"),
                "t1":        asig.get("t1"),
                "t2":        asig.get("t2"),
                "rr_t1":     asig.get("rr_t1"),
                "rr_t2":     asig.get("rr_t2"),
                "sl_type":   asig.get("sl_type", "atr_prosent"),
                "cot_bias":  asig.get("cot_bias"),
                "atr_d1":    asig.get("atr_est"),
                "source":    "agri_fundamental",
                "correlation_group": AGRI_CORRELATION_SUBGROUPS.get(asig.get("key",""), "agri"),
                "horizon_config": HORIZON_CONFIGS.get(horizon, {}),
                # Agri-spesifikk ekstradata
                "yield_score":     asig.get("yield_score"),
                "weather_outlook": asig.get("weather_outlook"),
                "drivers":         asig.get("drivers", []),
            })
            agri_merged += 1
        if agri_merged:
            print(f"  Agri: {agri_merged} signaler merget inn i signals.json")
    except Exception as e:
        print(f"  Agri merge feilet: {e}")

SIGNALS_OUT.parent.mkdir(parents=True, exist_ok=True)
tech_count = len(signals_json['signals']) - agri_merged
if len(signals_json['signals']) == 0:
    # Ingen nye signaler — behold eksisterende signals.json uendret
    # slik at lista ikke tømmes når en oppdatering returnerer 0 signaler.
    print(f"signals.json → 0 signaler, beholder eksisterende fil uendret")
else:
    with open(SIGNALS_OUT, "w") as f:
        json.dump(signals_json, f, ensure_ascii=False, indent=2)
    print(f"signals.json → {tech_count} tekniske + {agri_merged} agri = {len(signals_json['signals'])} totalt")
if oil_geo:
    print(f"  ⚠️  OLJE GEO-ADVARSEL: {oil_warn_str} → boten blokkerer smale SL på olje")
if geo_active:
    print(f"  🌍 GEO AKTIV: kvart-størrelse på alle trades")

if not top:
    # Ingen nye tekniske signaler — vi pusher IKKE tom liste til Flask
    # (det ville tømt eksisterende signaler på serveren). Lar serveren
    # beholde forrige push til neste oppdatering faktisk har signaler.
    print(f"Ingen signaler over horisont-terskler — beholder eksisterende liste (ingen push)")
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

# signal_log.json skrives KUN av trading_bot.py (faktiske bot-trades)
# push_signals.py logger ikke lenger auto-genererte signaler hit
print(f"signal_log.json → {len(signal_log.get('entries',[]))} bot-trades (managed av trading_bot.py)")


# ── Formater melding ───────────────────────────────────────
def fmt_signal(key, d):
    direction = "LONG  ▲" if d.get("dir_color") == "bull" else "SHORT ▼"
    tf        = d.get("horizon", d.get("timeframe_bias", "SWING"))
    grade     = d.get("grade", "?")
    score     = d.get("score", 0)
    max_sc    = d.get("max_score", 14)
    curr      = d.get("current", 0)
    p         = 5 if curr < 100 else 2
    cot       = d.get("cot", {})
    cot_str   = f"{cot.get('bias','?')} {cot.get('momentum','')} ({cot.get('pct',0):.1f}%)"
    pos_size  = d.get("pos_size", "?")
    setup     = active_setup(d)

    lines = [
        f"── {d.get('name', key)} [{tf}] ──",
        f"{direction}  {grade}({score:.1f}/{max_sc:.1f})  VIX:{vix_price:.1f} → {pos_size}",
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


# H2: Outbox-katalog. Hvis Flask er nede når push_signals.py kjører, lagres
# payload her; neste kjøring forsøker å sende alt som ligger i kø først.
# Filene slettes ved vellykket levering. Bevart også ved 4xx slik at operatør
# kan debugge validerings-avslag manuelt.
OUTBOX_DIR = BASE / "data" / "outbox"


def _send_payload(payload_bytes: bytes) -> tuple[bool, str]:
    """Returnerer (ok, melding). ok=True ved HTTP 2xx."""
    url = f"{FLASK_URL}/push-alert"
    req = urllib.request.Request(
        url, data=payload_bytes,
        headers={"Content-Type": "application/json", "X-API-Key": SCALP_API_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return (True, f"HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        # 4xx = skjema/valideringsfeil. Behold i outbox for inspeksjon,
        # men ikke retry i evigheten — flagg som "stuck".
        return (False, f"HTTP {e.code} {e.reason}")
    except urllib.error.URLError as e:
        return (False, f"nettverk: {e}")


def _flush_outbox():
    """Forsøk å levere hver outbox-fil. Slett ved suksess."""
    if not OUTBOX_DIR.exists():
        return
    stuck = sorted(OUTBOX_DIR.glob("*.json"))
    if not stuck:
        return
    print(f"Outbox: {len(stuck)} ventende payload(s)")
    for path in stuck:
        try:
            ok, msg = _send_payload(path.read_bytes())
        except Exception as e:
            print(f"  {path.name}: lesefeil — {e}")
            continue
        if ok:
            path.unlink()
            print(f"  {path.name} → levert ({msg})")
        else:
            # Payload eldre enn 24h med 4xx-feil: slett for å unngå evig retry
            age_h = (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 3600
            if msg.startswith("HTTP 4") and age_h > 24:
                path.unlink()
                print(f"  {path.name} → droppet (4xx eldre enn 24h)")
            else:
                print(f"  {path.name} → utsatt ({msg}, alder {age_h:.1f}h)")


# ── Push til Flask /push-alert ────────────────────────────
def push_flask(signals):
    if not SCALP_API_KEY:
        return
    payload = json.dumps({
        # Schema 2.0: driver-familie-matrise (erstatter 9-kriterie-scoring).
        # Felt `driver_groups`, `active_driver_groups`, `group_drivers` per signal.
        "schema_version": "2.1",
        "signals":   signals,
        "generated": generated,
        "global_state": {
            "vix_regime": vix_regime,
            "geo_active": geo_active,
            "correlation_regime": corr_regime,
            "correlation_config": corr_config,
        },
    }).encode()

    # H2: Forsøk outbox-flush først (ventende payloads fra tidligere kjøring)
    _flush_outbox()

    ok, msg = _send_payload(payload)
    if ok:
        print(f"Flask /push-alert OK ({msg})")
        return
    # Feilet — persist til outbox for retry neste kjøring
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    fname = OUTBOX_DIR / f"push-{ts}.json"
    try:
        fname.write_bytes(payload)
        print(f"Flask FEIL ({msg}) — lagret i outbox: {fname.name}")
    except Exception as e:
        print(f"Flask FEIL ({msg}) — outbox-skriv også feilet: {e}")


# ── Kjør pushes ───────────────────────────────────────────
push_telegram(message)
push_discord(message)
# Per-signal created_at — botens TTL-sjekk ser på denne, ikke kun fil-nivå valid_until
_now_iso = datetime.now(timezone.utc).isoformat()

# Tekniske signaler i Flask-format
# Schema 2.1: propagere driver_groups + active_driver_groups + group_drivers
flask_signals = [{
    "key":            key,
    "name":           d.get("name", key),
    "horizon":        d.get("horizon", d.get("timeframe_bias", "SWING")),
    "direction":      d.get("dir_color", "?"),
    "grade":          d.get("grade", "?"),
    "score":          d.get("score", 0),
    "max_score":      d.get("max_score", 6.0),   # 0-6 i schema 2.0
    "setup":          active_setup(d),
    "cot":            d.get("cot", {}),
    "correlation_group": d.get("correlation_group"),
    "horizon_config": HORIZON_CONFIGS.get(
        d.get("horizon", d.get("timeframe_bias", "SWING")), {}),
    # ── Driver-familie-matrise (fikset C1) ──────────────────────
    "driver_groups":        d.get("driver_groups", {}),
    "active_driver_groups": d.get("active_driver_groups"),
    "group_drivers":  d.get("group_drivers", []),
    "created_at":     _now_iso,
} for key, d in top]

# Agri-signaler i Flask-format (samme /push-alert endpoint)
if AGRI_SIGNALS_FILE.exists():
    try:
        with open(AGRI_SIGNALS_FILE) as _af2:
            _agri2 = json.load(_af2)
        for asig in _agri2.get("signals", []):
            horizon = asig.get("timeframe", "SWING")
            flask_signals.append({
                "key":       asig.get("key", ""),
                "name":      asig.get("name", asig.get("key", "")),
                "horizon":   horizon,
                "direction": asig.get("action", "BUY").lower().replace("buy","bull").replace("sell","bear"),
                "grade":     asig.get("grade", "C"),
                "score":     asig.get("score", 0),
                "max_score": 10,
                "setup": {
                    "entry":   asig.get("entry"),
                    "sl":      asig.get("sl"),
                    "t1":      asig.get("t1"),
                    "t2":      asig.get("t2"),
                    "rr_t1":   asig.get("rr_t1"),
                    "rr_t2":   asig.get("rr_t2"),
                    "sl_type": asig.get("sl_type", "atr_prosent"),
                },
                "cot":              {"bias": asig.get("cot_bias"), "pct": asig.get("cot_pct")},
                "atr_d1":           asig.get("atr_est"),
                "atr_est":          asig.get("atr_est"),
                "correlation_group": "agri",
                "source":           "agri_fundamental",
                "horizon_config":   HORIZON_CONFIGS.get(horizon, {}),
                "yield_score":      asig.get("yield_score"),
                "weather_outlook":  asig.get("weather_outlook"),
                "drivers":          asig.get("drivers", []),
                # Schema 2.1: propagere driver_groups fra agri_signals.json
                "driver_groups":         asig.get("driver_groups", {}),
                "active_driver_groups":  asig.get("active_driver_groups"),
                "group_drivers":   asig.get("group_drivers", []),
                "created_at":       _now_iso,
            })
    except Exception:
        pass

push_flask(flask_signals)
