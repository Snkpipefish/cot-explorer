#!/usr/bin/env python3
"""
utils.py — Delte hjelpefunksjoner for COT Explorer pipeline.
Eliminerer kodeduplisering på tvers av fetch_*.py scripts.
"""
import json
import time
import logging
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# ── Logging ──────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

def get_logger(name, log_file=None):
    """Opprett en logger med fil- og konsoll-handler."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    # Konsoll
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    # Fil
    if log_file:
        fh = logging.FileHandler(LOG_DIR / log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


# M6: Circuit-breaker per hostname. Når en kilde feiler flere ganger på
# rad, bytter vi til "open"-state og dropper påfølgende kall i N sekunder.
# Forhindrer at én død RSS-feed bremser hele fetch-pipelinen med 45s
# retry-windows per forespørsel. State holdes in-memory per prosess —
# passer for kort-levede fetch_*.py-kjøringer (én per ~4h eller ~15m).
_CB_FAIL_THRESHOLD = 3        # antall strake feil før åpning
_CB_OPEN_SECONDS   = 300      # hvor lenge kretsen holdes åpen (5 min)
_cb_state: dict = {}          # host → {"fails": int, "opened_at": float|None}


def _cb_host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc or url


def _cb_allow(url: str) -> bool:
    host = _cb_host(url)
    st = _cb_state.get(host)
    if not st or st["opened_at"] is None:
        return True
    if time.time() - st["opened_at"] > _CB_OPEN_SECONDS:
        # Half-open: gi neste request sjansen til å lukke kretsen
        st["opened_at"] = None
        st["fails"] = 0
        return True
    return False


def _cb_record(url: str, ok: bool):
    host = _cb_host(url)
    st = _cb_state.setdefault(host, {"fails": 0, "opened_at": None})
    if ok:
        st["fails"] = 0
        st["opened_at"] = None
        return
    st["fails"] += 1
    if st["fails"] >= _CB_FAIL_THRESHOLD and st["opened_at"] is None:
        st["opened_at"] = time.time()


# ── HTTP med retry ───────────────────────────────────────────
def fetch_url(url, timeout=15, retries=2, headers=None):
    """Hent URL med retry og eksponentiell backoff. Returnerer bytes eller None.
    M6: Circuit-breaker per host — hopper over kall mot kilder som har feilet
    _CB_FAIL_THRESHOLD ganger på rad, i _CB_OPEN_SECONDS sekunder."""
    if not _cb_allow(url):
        return None   # Kretsen er åpen — fail-fast uten retry-pølse
    hdrs = {"User-Agent": "Mozilla/5.0"}
    if headers:
        hdrs.update(headers)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            _cb_record(url, ok=True)
            return data
        except Exception as e:
            if attempt < retries:
                time.sleep(1.5 ** attempt)
                continue
            _cb_record(url, ok=False)
            return None


def fetch_json(url, timeout=15, retries=2):
    """Hent JSON fra URL med retry. Returnerer dict/list eller None."""
    raw = fetch_url(url, timeout=timeout, retries=retries)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


# ── Stooq prisdata ───────────────────────────────────────────
STOOQ_BASE = "https://stooq.com/q/d/l/"

def fetch_stooq(symbol, days=30):
    """Hent historiske priser fra Stooq. Returnerer dict med value, chg1d, ma20, etc. eller None."""
    url = STOOQ_BASE + "?" + urllib.parse.urlencode({"s": symbol, "i": "d"})
    raw = fetch_url(url)
    if raw is None:
        return None
    try:
        lines = raw.decode("utf-8", errors="replace").strip().split("\n")
        rows = []
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for line in lines[1:]:
            parts = line.strip().split(",")
            if len(parts) < 5:
                continue
            try:
                rows.append({"date": parts[0].strip(), "close": float(parts[4])})
            except Exception:
                continue
        if not rows:
            return None
        # Fjern ubekreftede intradag-data
        if rows[-1]["date"] == today and len(rows) > 1:
            rows = rows[:-1]
        rows = rows[-days:]
        if len(rows) < 3:
            return None
        closes = [r["close"] for r in rows]
        curr, prev = closes[-1], closes[-2]
        n20 = min(len(closes), 20)
        n5 = min(len(closes), 5)
        ma20 = sum(closes[-n20:]) / n20
        ma5 = sum(closes[-n5:]) / n5
        chg1d = (curr - prev) / prev * 100
        dev_ma = (curr - ma20) / ma20 * 100
        trend = "STIGENDE" if ma5 > ma20 * 1.001 else "FALLENDE" if ma5 < ma20 * 0.999 else "SIDELENGS"
        if dev_ma > 15:    signal = "bull"
        elif dev_ma < -15: signal = "bear"
        elif dev_ma > 5:   signal = "bull-mild"
        elif dev_ma < -5:  signal = "bear-mild"
        else:              signal = "neutral"
        return {
            "value":   round(curr, 2),
            "prev":    round(prev, 2),
            "chg1d":   round(chg1d, 2),
            "ma20":    round(ma20, 2),
            "dev_ma":  round(dev_ma, 1),
            "trend":   trend,
            "signal":  signal,
            "date":    rows[-1]["date"],
            "history": [round(c, 2) for c in closes[-15:]],
            "source":  "stooq",
        }
    except Exception:
        return None


# ── Google News RSS ──────────────────────────────────────────
GNEWS_BASE = "https://news.google.com/rss/search"

def fetch_google_news(query_id, query_label, query_text, max_articles=8):
    """Hent nyheter fra Google News RSS. Returnerer liste med artikler."""
    params = urllib.parse.urlencode({
        "q": query_text, "hl": "en-US", "gl": "US", "ceid": "US:en",
    })
    raw = fetch_url(f"{GNEWS_BASE}?{params}")
    if raw is None:
        return []
    try:
        root = ET.fromstring(raw.decode("utf-8", errors="replace"))
        ch = root.find("channel")
        if ch is None:
            return []
        result = []
        for item in ch.findall("item")[:max_articles]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            src_el = item.find("source")
            source = src_el.text.strip() if src_el is not None and src_el.text else ""
            pub_raw = item.findtext("pubDate", "")
            try:
                pub_str = parsedate_to_datetime(pub_raw).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pub_str = pub_raw[:16] if pub_raw else ""
            if not title:
                continue
            result.append({
                "title": title, "url": link, "source": source,
                "time": pub_str, "cat": query_id, "label": query_label,
            })
        return result
    except Exception:
        return []


# ── Bot-priser ───────────────────────────────────────────────
BOT_PRICES_FILE = Path.home() / "scalp_edge" / "live_prices.json"

def load_bot_prices():
    """Last bot-priser fra live_prices.json. Returnerer dict eller {}."""
    try:
        if not BOT_PRICES_FILE.exists():
            return {}
        with open(BOT_PRICES_FILE) as f:
            raw = json.load(f)
        return raw if "prices" not in raw else raw.get("prices", {})
    except Exception:
        return {}


def fetch_from_bot(bot_key_map, instrument_id):
    """Hent pris for instrument fra bot-data."""
    try:
        bot = load_bot_prices()
        key = bot_key_map.get(instrument_id)
        if not key:
            return None
        p = bot.get(key)
        if not p or p.get("value") is None:
            return None
        val = p["value"]
        chg1d = p.get("chg1d", 0.0) or 0.0
        prev = round(val / (1 + chg1d / 100), 4) if chg1d != -100 else val
        return {
            "value": round(val, 4),
            "prev": prev,
            "chg1d": round(chg1d, 3),
            "chg5d": round(p.get("chg5d", 0.0) or 0.0, 3),
            "ma20": None,
            "dev_ma": None,
            "trend": None,
            "signal": "neutral",
            "date": p.get("updated", ""),
            "history": [],
            "source": "bot",
        }
    except Exception:
        return None


# ── Data freshness ───────────────────────────────────────────
def check_data_freshness(filepath, max_age_hours):
    """Sjekk om en datafil er innenfor akseptabel alder. Returnerer (ok, age_hours)."""
    try:
        p = Path(filepath)
        if not p.exists():
            return False, None
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        age_h = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
        return age_h <= max_age_hours, round(age_h, 1)
    except Exception:
        return True, None


# ── JSON med meta ────────────────────────────────────────────
def save_json_with_meta(data, filepath, script_name=None):
    """Lagre JSON med _meta freshness-info."""
    data["_meta"] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "script": script_name or "unknown",
    }
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Pris-validering ──────────────────────────────────────────
def validate_price(value, min_val=0, max_val=1e7):
    """Sjekk om en prisverdi er rimelig."""
    if value is None:
        return False
    try:
        v = float(value)
        return min_val <= v <= max_val and v == v  # NaN check
    except (ValueError, TypeError):
        return False
