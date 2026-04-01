#!/usr/bin/env python3
"""
signal_server.py — Lokal Flask-server for COT Explorer

Endepunkter:
  POST /push-alert   → mottar signaler fra push_signals.py
  POST /push-prices  → mottar live priser fra trading-boten (Skilling)
  GET  /prices       → returnerer siste bot-priser som JSON

Miljøvariabler:
  SCALP_API_KEY  → nøkkel som må sendes i X-API-Key header
  PORT           → lytteport (default 5000)
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, request, jsonify

app = Flask(__name__)

BASE          = Path(__file__).parent.parent          # ~/cot-explorer/
BOT_PRICES    = BASE / "data" / "prices" / "live_prices.json"
ALERTS_LOG    = BASE / "data" / "prices" / "alerts.json"
SCALP_API_KEY = os.environ.get("SCALP_API_KEY", "")

BOT_PRICES.parent.mkdir(parents=True, exist_ok=True)


def check_key():
    if not SCALP_API_KEY:
        return None   # nøkkel ikke konfigurert → godta alt (lokal dev)
    return request.headers.get("X-API-Key") == SCALP_API_KEY


# ── POST /push-prices ────────────────────────────────────────────────────────
# Boten kaller dette endepunktet med live priser fra Skilling.
# Format (JSON body):
# {
#   "prices": {
#     "Brent":  {"value": 85.20, "chg1d": -0.4},
#     "WTI":    {"value": 81.10, "chg1d": -0.3},
#     "NatGas": {"value":  2.85, "chg1d":  1.1},
#     "Gold":   {"value": 2350.0, "chg1d": 0.5},
#     "EURUSD": {"value": 1.0850, "chg1d": 0.2}
#   }
# }
# Alle felt i "prices" er valgfrie — send bare det boten har tilgang til.
@app.route("/push-prices", methods=["POST"])
def push_prices():
    if not check_key():
        return jsonify({"error": "unauthorized"}), 401

    body = request.get_json(silent=True)
    if not body or "prices" not in body:
        return jsonify({"error": "mangler 'prices'-felt i body"}), 400

    incoming = body["prices"]
    if not isinstance(incoming, dict) or not incoming:
        return jsonify({"error": "'prices' må være et objekt med minst ett felt"}), 400

    # Last eksisterende data (behold priser vi ikke oppdaterer)
    existing = {}
    if BOT_PRICES.exists():
        try:
            existing = json.loads(BOT_PRICES.read_text()).get("prices", {})
        except Exception:
            pass

    # Normaliser og merge
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    merged  = {**existing}
    updated = []
    for key, val in incoming.items():
        if not isinstance(val, dict):
            continue
        price = val.get("value") or val.get("price")
        if price is None:
            continue
        merged[key] = {
            "value":  round(float(price), 6),
            "chg1d":  round(float(val.get("chg1d", 0) or 0), 3),
            "chg5d":  round(float(val.get("chg5d", 0) or 0), 3),
            "chg20d": round(float(val.get("chg20d", 0) or 0), 3),
            "source": "bot",
            "updated": now_str,
        }
        updated.append(key)

    out = {"generated": now_str, "prices": merged}
    BOT_PRICES.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print(f"[push-prices] {now_str} → oppdaterte: {', '.join(updated)}")
    return jsonify({"ok": True, "updated": updated, "total": len(merged)}), 200


# ── GET /prices ──────────────────────────────────────────────────────────────
@app.route("/prices", methods=["GET"])
def get_prices():
    if BOT_PRICES.exists():
        return jsonify(json.loads(BOT_PRICES.read_text()))
    return jsonify({"prices": {}, "generated": None}), 200


# ── POST /push-alert ─────────────────────────────────────────────────────────
@app.route("/push-alert", methods=["POST"])
def push_alert():
    if not check_key():
        return jsonify({"error": "unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    signals = body.get("signals", [])

    # Logg til fil
    log = []
    if ALERTS_LOG.exists():
        try:
            log = json.loads(ALERTS_LOG.read_text())
        except Exception:
            pass
    log.append({
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "generated": body.get("generated"),
        "signals":   signals,
    })
    log = log[-200:]   # behold siste 200
    ALERTS_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2))

    print(f"[push-alert] mottok {len(signals)} signaler")
    return jsonify({"ok": True, "received": len(signals)}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"signal_server kjører på port {port}")
    print(f"API-nøkkel: {'satt' if SCALP_API_KEY else 'IKKE SATT (åpen tilgang)'}")
    app.run(host="0.0.0.0", port=port)
