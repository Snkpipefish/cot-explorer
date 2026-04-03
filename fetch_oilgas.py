#!/usr/bin/env python3
"""
fetch_oilgas.py — Olje & Gass Intelligence
Henter gratis energidata:
  - WTI, Brent, Naturgass, RBOB, Heating Oil (stooq)
  - Spekulantposisjonering fra COT-data (data/combined/latest.json)
  - Nyheter fra Google News RSS
  - Beregner spread, MA-avvik, segment-risiko og samlet signal
Output: data/oilgas/latest.json
"""
import json, time, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = Path(__file__).parent
OUT  = BASE / "data" / "oilgas" / "latest.json"
OUT.parent.mkdir(parents=True, exist_ok=True)
COMBINED_FILE  = BASE / "data" / "combined" / "latest.json"
MACRO_FILE     = BASE / "data" / "macro" / "latest.json"
BOT_PRICES_FILE = Path.home() / "scalp_edge" / "live_prices.json"

# Mapping fra instrument-id → nøkkel boten sender i /push-prices
BOT_PRICE_MAP = {
    "brent":  "Brent",
    "wti":    "WTI",
    "natgas": "NatGas",
    # rbob og heatoil ikke tilgjengelig i Skilling
}
MACRO_PRICE_MAP = {
    "brent": "Brent",
    "wti":   "WTI",
}

# ── Priser via stooq ─────────────────────────────────────────────
PRICE_INDICES = [
    {"id": "brent",   "label": "Brent Crude",    "symbol": "co.f",  "unit": "USD/fat",  "cot_key": "brent"},
    {"id": "wti",     "label": "WTI Crude",       "symbol": "cl.f",  "unit": "USD/fat",  "cot_key": "wti"},
    {"id": "natgas",  "label": "Natural Gas",     "symbol": "ng.f",  "unit": "USD/MMBtu","cot_key": "natgas"},
    {"id": "rbob",    "label": "Gasoline (RBOB)", "symbol": "rb.f",  "unit": "USD/gal",  "cot_key": "rbob"},
    {"id": "heatoil", "label": "Heating Oil",     "symbol": "ho.f",  "unit": "USD/gal",  "cot_key": None},
]

# COT: hvilke CFTC-markedsnavn tilhører hver pris
COT_MAP = {
    "wti":    ["Crude Oil, Light Sweet", "Wti Crude Oil 1St Line", "Wti Financial Crude Oil"],
    "brent":  ["Brent Last Day"],
    "natgas": ["Natural Gas Index: Ep San Juan"],
    "rbob":   ["Gasoline Rbob"],
}

# ── Energisegmenter med markedseffekt ────────────────────────────
SEGMENTS = [
    {
        "id": "opec", "name": "OPEC+ Produksjon",
        "ikon": "🛢️", "impact": "Brent, WTI, energiaksjer (XLE, STO, EQNR)",
        "keywords": ["opec","opec+","saudi","aramco","production cut","output cut",
                     "quota","barrel per day","mbpd","opec meeting","opec decision"],
    },
    {
        "id": "us_supply", "name": "USA Skifer & Lager",
        "ikon": "🇺🇸", "impact": "WTI, XLE, HAL, SLB, rig count",
        "keywords": ["eia","crude inventory","us crude","shale","permian","bakken",
                     "rig count","baker hughes","us production","spr","strategic reserve"],
    },
    {
        "id": "russia", "name": "Russland & Sanksjoner",
        "ikon": "⚠️", "impact": "Brent premium, Ural-rabatt, europeisk energi",
        "keywords": ["russia oil","russia gas","urals","russian crude","russia sanction",
                     "nord stream","russian energy","lukoil","rosneft","gazprom"],
    },
    {
        "id": "mideast", "name": "Midt-Østen Konflikt",
        "ikon": "💣", "impact": "Brent geopolitisk risiko, tanker-forsikring",
        "keywords": ["iran","iraq","israel","hamas","hezbollah","middle east oil",
                     "gulf war","strait hormuz","persian gulf tension","attack oil"],
    },
    {
        "id": "lng", "name": "LNG & Naturgass",
        "ikon": "🔵", "impact": "Henry Hub, TTF Europa, Asian LNG premium (JKM)",
        "keywords": ["lng","liquefied natural gas","henry hub","ttf","jkm",
                     "natural gas price","gas storage","lng terminal","freeport lng",
                     "sabine pass","gas export"],
    },
    {
        "id": "refinery", "name": "Raffinering & Produkter",
        "ikon": "🏭", "impact": "Crack spread, RBOB, jet fuel, diesel margin",
        "keywords": ["refinery","crack spread","gasoline","diesel","jet fuel",
                     "refinery outage","refinery fire","refinery maintenance",
                     "fuel demand","product inventory"],
    },
    {
        "id": "demand", "name": "Global Etterspørsel",
        "ikon": "📊", "impact": "Alle energipriser, IEA/OPEC prognose",
        "keywords": ["oil demand","iea forecast","opec forecast","china demand",
                     "india demand","energy demand","economic slowdown oil",
                     "recession oil","demand outlook"],
    },
    {
        "id": "renewable", "name": "Energitransisjon",
        "ikon": "🌱", "impact": "Langsiktig oljeetterspørsel, ESG-kapitalflyt",
        "keywords": ["energy transition","renewable","ev demand oil","electric vehicle",
                     "peak oil demand","solar wind energy","fossil fuel"],
    },
]

# ── Nyhetssøk ────────────────────────────────────────────────────
NEWS_QUERIES = [
    {"id": "opec",     "label": "OPEC+",
     "query": "OPEC production cut Saudi Arabia crude oil supply output"},
    {"id": "prices",   "label": "Priser",
     "query": "crude oil price WTI Brent forecast rally drop"},
    {"id": "natgas",   "label": "Naturgass",
     "query": "natural gas LNG price storage Henry Hub TTF"},
    {"id": "geopolit", "label": "Geopolitikk",
     "query": "oil supply disruption Middle East Iran Russia sanctions energy"},
    {"id": "inventory","label": "Lager/Produksjon",
     "query": "EIA crude inventory US oil production shale rig count"},
]

GNEWS_BASE = "https://news.google.com/rss/search"
STOOQ_BASE = "https://stooq.com/q/d/l/"

DISRUPTION_WORDS = [
    "cut","reduce","curtail","disruption","halt","suspend","sanction","attack",
    "conflict","war","strike","outage","fire","explosion","shutdown","close",
    "block","restrict","ban","threat","tension","risk","shortage","rally",
]

# ── Hjelpefunksjoner ─────────────────────────────────────────────
def fetch_stooq(symbol):
    url = STOOQ_BASE + "?" + urllib.parse.urlencode({"s": symbol, "i": "d"})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8", errors="replace")
        lines = raw.strip().split("\n")
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
        if rows[-1]["date"] == today and len(rows) > 1:
            rows = rows[:-1]
        rows = rows[-30:]
        if len(rows) < 3:
            return None
        closes = [r["close"] for r in rows]
        curr, prev = closes[-1], closes[-2]
        ma20  = sum(closes[-20:]) / min(len(closes), 20)
        ma5   = sum(closes[-5:])  / min(len(closes), 5)
        chg1d = (curr - prev) / prev * 100
        dev_ma = (curr - ma20) / ma20 * 100
        trend  = "STIGENDE" if ma5 > ma20 * 1.001 else "FALLENDE" if ma5 < ma20 * 0.999 else "SIDELENGS"
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
        }
    except Exception as e:
        print(f"  Stooq FEIL ({symbol}): {e}")
        return None


def fetch_from_bot(instrument_id):
    """Hent pris fra ~/scalp_edge/live_prices.json (sendt av trading-boten fra Skilling)."""
    try:
        if not BOT_PRICES_FILE.exists():
            return None
        with open(BOT_PRICES_FILE) as f:
            raw = json.load(f)
        key = BOT_PRICE_MAP.get(instrument_id)
        if not key:
            return None
        # Støtter flatt format {KEY: {...}} og nestet {"prices": {KEY: {...}}}
        bot = raw if "prices" not in raw else raw.get("prices", {})
        p = bot.get(key)
        if not p or p.get("value") is None:
            return None
        val = p["value"]
        chg1d = p.get("chg1d", 0.0) or 0.0
        prev = round(val / (1 + chg1d / 100), 4) if chg1d != -100 else val
        return {
            "value":  round(val, 4),
            "prev":   prev,
            "chg1d":  round(chg1d, 3),
            "chg5d":  round(p.get("chg5d", 0.0) or 0.0, 3),
            "ma20":   None,
            "dev_ma": None,
            "trend":  None,
            "signal": "neutral",
            "date":   p.get("updated", ""),
            "history": [],
            "source": "bot",
        }
    except Exception as e:
        print(f"  Bot-priser FEIL ({instrument_id}): {e}")
        return None


def fetch_from_macro(instrument_id):
    """Hent pris fra macro/latest.json som fallback når stooq ikke er tilgjengelig."""
    try:
        with open(MACRO_FILE) as f:
            macro = json.load(f)
        key = MACRO_PRICE_MAP.get(instrument_id)
        if not key:
            return None
        p = macro.get("prices", {}).get(key)
        if not p or p.get("price") is None:
            return None
        val = p["price"]
        chg1d = p.get("chg1d", 0.0) or 0.0
        prev = round(val / (1 + chg1d / 100), 2) if chg1d != -100 else val
        return {
            "value":   round(val, 2),
            "prev":    prev,
            "chg1d":   round(chg1d, 2),
            "ma20":    None,
            "dev_ma":  None,
            "trend":   None,
            "signal":  "neutral",
            "date":    macro.get("date", ""),
            "history": [],
            "source":  "macro",
        }
    except Exception as e:
        print(f"  Macro-fallback FEIL ({instrument_id}): {e}")
        return None


def get_cot(cot_key, cot_data):
    markets = COT_MAP.get(cot_key, [])
    matches = [e for e in cot_data
               if any(m.lower() in e.get("market", "").lower() for m in markets)]
    if not matches:
        return None
    main = max(matches, key=lambda e: e.get("open_interest", 0) or 0)
    sp   = main.get("spekulanter") or {}
    net  = sp.get("net", 0) or 0
    chg  = main.get("change_spec_net", 0) or 0
    oi   = main.get("open_interest", 1) or 1
    hist = main.get("spec_net_history", []) or []
    net_pct = net / oi * 100 if oi else 0
    bias = "bull" if net > 0 else "bear"
    if len(hist) >= 3:
        rec = hist[-3:]
        momentum = "ØKER" if all(x > 0 for x in rec) else "FALLER" if all(x < 0 for x in rec) else "BLANDET"
    else:
        momentum = "ØKER" if chg > 0 else "FALLER"
    if net_pct > 15:    cot_score = 2
    elif net_pct > 5:   cot_score = 1
    elif net_pct > -5:  cot_score = 0
    elif net_pct > -15: cot_score = -1
    else:               cot_score = -2
    if chg > 0 and cot_score >= 0:   cot_score = min(cot_score + 1, 2)
    elif chg < 0 and cot_score <= 0: cot_score = max(cot_score - 1, -2)
    return {
        "market":    main.get("market", cot_key),
        "net":       net,
        "net_pct":   round(net_pct, 1),
        "change":    chg,
        "bias":      bias,
        "momentum":  momentum,
        "cot_score": cot_score,
        "date":      main.get("date"),
    }


def fetch_news(q):
    params = urllib.parse.urlencode({
        "q": q["query"], "hl": "en-US", "gl": "US", "ceid": "US:en",
    })
    try:
        req = urllib.request.Request(
            f"{GNEWS_BASE}?{params}", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8", errors="replace")
        root = ET.fromstring(raw)
        ch = root.find("channel")
        if ch is None:
            return []
        result = []
        for item in ch.findall("item")[:8]:
            title = item.findtext("title", "").strip()
            link  = item.findtext("link", "").strip()
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
                "title":  title, "url": link, "source": source,
                "time":   pub_str, "cat": q["id"], "label": q["label"],
            })
        return result
    except Exception as e:
        print(f"  Nyheter FEIL ({q['id']}): {e}")
        return []


def score_segments(all_news):
    scores   = {s["id"]: 0 for s in SEGMENTS}
    articles = {s["id"]: [] for s in SEGMENTS}
    for art in all_news:
        text = art["title"].lower()
        for seg in SEGMENTS:
            if not any(kw in text for kw in seg["keywords"]):
                continue
            disrupt = sum(1 for w in DISRUPTION_WORDS if w in text)
            scores[seg["id"]] += 1 + disrupt
            if len(articles[seg["id"]]) < 3:
                articles[seg["id"]].append(art)
    result = []
    for s in SEGMENTS:
        sc = scores[s["id"]]
        risk = "HIGH" if sc >= 5 else "MEDIUM" if sc >= 2 else "LOW"
        result.append({**s, "risk": risk, "risk_score": sc, "articles": articles[s["id"]]})
    result.sort(key=lambda x: -x["risk_score"])
    return result


def combine_signal(price_data, cot):
    """Kombinerer pris-trend og COT til et samlet signal."""
    sig_map = {"bull": 2, "bull-mild": 1, "neutral": 0, "bear-mild": -1, "bear": -2}
    price_score = sig_map.get(price_data["signal"] if price_data else "neutral", 0)
    cot_score   = cot["cot_score"] if cot else 0
    total = price_score + cot_score
    if total >= 3:   return "STERKT BULLISH"
    elif total >= 1: return "BULLISH"
    elif total <= -3:return "STERKT BEARISH"
    elif total <= -1:return "BEARISH"
    else:            return "NØYTRAL"


# ── Hoved-logikk ─────────────────────────────────────────────────
print("Henter olje & gass data...")

# COT-data
try:
    with open(COMBINED_FILE) as f:
        cot_data = json.load(f)
except Exception as e:
    print(f"  COT-data FEIL: {e}")
    cot_data = []

# 1. Priser + COT per instrument
print("  Henter priser (stooq → macro fallback)...")
instruments = []
for i, inst in enumerate(PRICE_INDICES):
    if i > 0:
        time.sleep(1)
    price = fetch_stooq(inst["symbol"])
    if price is None:
        price = fetch_from_bot(inst["id"])
        if price:
            print(f"    {inst['label']:20} → bruker bot-priser (Skilling)")
    if price is None:
        price = fetch_from_macro(inst["id"])
        if price:
            print(f"    {inst['label']:20} → bruker macro-data som fallback")
    cot   = get_cot(inst["cot_key"], cot_data) if inst["cot_key"] else None
    signal = combine_signal(price, cot)
    status = f"{price['value']} ({price['chg1d']:+.2f}%)" if price else "ikke tilgjengelig"
    print(f"    {inst['label']:20} → {status}")
    instruments.append({
        "id":     inst["id"],
        "label":  inst["label"],
        "unit":   inst["unit"],
        "price":  price,
        "cot":    cot,
        "signal": signal,
    })

# 2. Brent-WTI spread
brent_v = next((i["price"]["value"] for i in instruments if i["id"] == "brent" and i["price"]), None)
wti_v   = next((i["price"]["value"] for i in instruments if i["id"] == "wti"   and i["price"]), None)
brent_wti_spread = round(brent_v - wti_v, 2) if brent_v and wti_v else None

# 3. Nyheter
print("  Henter energi-nyheter...")
all_news = []
for i, q in enumerate(NEWS_QUERIES):
    if i > 0:
        time.sleep(2)
    arts = fetch_news(q)
    all_news.extend(arts)
    print(f"    {q['label']:15} → {len(arts)} artikler")
all_news.sort(key=lambda x: x["time"], reverse=True)

# 4. Segment-risiko
segments = score_segments(all_news)
high_seg = [s for s in segments if s["risk"] == "HIGH"]
med_seg  = [s for s in segments if s["risk"] == "MEDIUM"]
if len(high_seg) >= 2:   overall_risk = "HIGH"
elif high_seg or len(med_seg) >= 3: overall_risk = "MEDIUM"
else:                    overall_risk = "LOW"

# 5. Samlet markedssignal (basert på Brent + WTI)
key_instruments = [i for i in instruments if i["id"] in ("brent", "wti")]
sig_scores = {"STERKT BULLISH": 2, "BULLISH": 1, "NØYTRAL": 0, "BEARISH": -1, "STERKT BEARISH": -2}
if key_instruments:
    avg_sig = sum(sig_scores.get(i["signal"], 0) for i in key_instruments) / len(key_instruments)
    overall_signal = ("STERKT BULLISH" if avg_sig >= 1.5 else "BULLISH" if avg_sig >= 0.5
                      else "STERKT BEARISH" if avg_sig <= -1.5 else "BEARISH" if avg_sig <= -0.5
                      else "NØYTRAL")
else:
    overall_signal = "NØYTRAL"

output = {
    "generated":      datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "source":         "CFTC · Skilling bot · Yahoo Finance · Google News RSS",
    "overall_risk":   overall_risk,
    "overall_signal": overall_signal,
    "brent_wti_spread": brent_wti_spread,
    "instruments":    instruments,
    "segments":       segments,
    "news":           all_news[:50],
}

with open(OUT, "w") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nOK → {OUT}")
print(f"  Signal: {overall_signal}  |  Risiko: {overall_risk}  |  Spread B/W: {brent_wti_spread}")
if high_seg:
    print(f"  HIGH-segmenter: {', '.join(s['name'] for s in high_seg)}")
