#!/usr/bin/env python3
"""
fetch_shipping.py — Shipping Intelligence
Henter gratis shipping-data:
  - Baltic Dry Index og sub-indekser (stooq)
  - Shipping-nyheter fra Google News RSS
  - Beregner MA-avvik og rute-risiko
Output: data/shipping/latest.json
"""
import json, time, urllib.request, urllib.parse, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = Path(__file__).parent
OUT  = BASE / "data" / "shipping" / "latest.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

# ── Stooq-symboler for shipping-indekser ─────────────────────────
INDICES = [
    {"id": "bdi",  "label": "Baltic Dry Index",   "symbol": "^bdi",   "desc": "Tørrbulk totalt"},
    {"id": "bci",  "label": "Baltic Capesize",     "symbol": "^bci",   "desc": "Kull & jernmalm"},
    {"id": "bpi",  "label": "Baltic Panamax",      "symbol": "^bpi",   "desc": "Korn & kull"},
    {"id": "bsi",  "label": "Baltic Supramax",     "symbol": "^bsi",   "desc": "Korn, stål, fosfat"},
]

# ── Globale shippingruter med markedseffekt ───────────────────────
ROUTES = [
    {
        "id": "trans_pacific", "name": "Trans-Pacific",
        "ikon": "📦", "cargo": "Container",
        "from": "Kina/Asia", "to": "USA Vestkyst",
        "impact": "USD, US-import, Fed-inflasjon, AAPL/Walmart",
        "keywords": ["trans-pacific","asia-us","la port","long beach","cosco",
                     "yang ming","evergreen","oakland port","us west coast"],
    },
    {
        "id": "asia_europe", "name": "Asia–Europa (Suez)",
        "ikon": "🚢", "cargo": "Container/Tanker",
        "from": "Asia", "to": "Europa",
        "impact": "EUR/USD, europeisk inflasjon, energipriser",
        "keywords": ["suez","red sea","houthi","bab-el-mandeb","maersk",
                     "msc","hapag","asia-europe","far east europe","cma cgm"],
    },
    {
        "id": "hormuz", "name": "Hormuz-stredet",
        "ikon": "🛢️", "cargo": "Råolje (VLCC)",
        "from": "Midt-Østen", "to": "Asia/Europa",
        "impact": "Brent, WTI, gass, energiaksjer",
        "keywords": ["hormuz","strait of hormuz","vlcc","persian gulf",
                     "iran","crude tanker","supertanker","middle east oil"],
    },
    {
        "id": "black_sea", "name": "Svartehavet (korn)",
        "ikon": "🌾", "cargo": "Hvete/Mais",
        "from": "Ukraina/Russland", "to": "Global",
        "impact": "Hvete, mais, global matvarepris, WEAT ETF",
        "keywords": ["black sea","ukraine grain","russia grain","bosphorus",
                     "grain corridor","novorossiysk","odessa","kerch strait"],
    },
    {
        "id": "panama", "name": "Panama-kanalen",
        "ikon": "🌊", "cargo": "Container/Bulk/LNG",
        "from": "Atlanterhavet", "to": "Stillehavet",
        "impact": "Kina–US handel, LNG til Asia, korn-frakt",
        "keywords": ["panama canal","panamax","water level","canal drought",
                     "gatun lake","canal authority","panama transit"],
    },
    {
        "id": "south_america", "name": "Sør-Amerika (korn/soya)",
        "ikon": "🌱", "cargo": "Soya/Mais/Hvete",
        "from": "Brasil/Argentina", "to": "Asia/Europa",
        "impact": "Soyabønner, mais, brasiliansk real",
        "keywords": ["brazil port","santos","paranagua","argentina grain",
                     "rosario","soybean export","corn export brazil",
                     "south america grain","mato grosso"],
    },
    {
        "id": "australia_bulk", "name": "Australia (råvarer)",
        "ikon": "⛏️", "cargo": "Kull/Jernmalm/Hvete",
        "from": "Australia", "to": "Kina/Japan/Korea",
        "impact": "Kull, jernmalm, stål, AUD/USD",
        "keywords": ["australia coal","newcastle coal","port hedland",
                     "iron ore","capesize australia","pilbara","dampier",
                     "australia wheat export"],
    },
    {
        "id": "malacca", "name": "Malakka-stredet",
        "ikon": "⚓", "cargo": "Olje/Container/LNG",
        "from": "Midt-Østen/Europa", "to": "Japan/Korea/Kina",
        "impact": "Olje, LNG, all Asia-import via stredet",
        "keywords": ["malacca","strait of malacca","singapore shipping",
                     "piracy malacca","tanker malacca","indonesia strait"],
    },
]

# ── Nyheter fra Google RSS ────────────────────────────────────────
NEWS_QUERIES = [
    {"id": "container",  "label": "Container",
     "query": "container shipping freight rate disruption congestion Maersk MSC"},
    {"id": "tanker",     "label": "Tanker",
     "query": "tanker VLCC crude oil shipping sanctions disruption"},
    {"id": "bulk",       "label": "Tørrbulk",
     "query": "dry bulk capesize panamax BDI Baltic Dry freight coal iron ore"},
    {"id": "chokepoint", "label": "Chokepoints",
     "query": "Suez Canal Panama Canal Hormuz Red Sea Houthi shipping disruption"},
    {"id": "port",       "label": "Havner",
     "query": "port congestion strike labor dispute shipping delay supply chain"},
]

GNEWS_BASE  = "https://news.google.com/rss/search"
STOOQ_BASE  = "https://stooq.com/q/d/l/"
BDI_HIST    = BASE / "data" / "shipping" / "bdi_history.json"

# Ord som tyder på forstyrrelser/risiko
DISRUPTION_WORDS = [
    "disruption","delay","congestion","strike","block","clos","restrict",
    "sanction","attack","conflict","war","drought","low water","divert",
    "reroute","avoid","warning","alert","risk","suspend","halt","tension",
    "threat","incident","explosion","fire","collision","aground","grounded",
]

# ── BDI fra tradingeconomics (selvbyggende historikk) ─────────────
def fetch_bdi_te():
    """Hent BDI nåverdi fra tradingeconomics og bygg lokal historikk."""
    import re
    url = "https://tradingeconomics.com/commodity/baltic"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="ignore")
        m = re.search(r'"last":([\d.]+).*?"name":"Baltic Dry"', html)
        if not m:
            m = re.search(r'"name":"Baltic Dry".*?"last":([\d.]+)', html)
        if not m:
            return None
        curr = round(float(m.group(1)))
    except Exception as e:
        print(f"  BDI tradingeconomics FEIL: {e}")
        return None

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Last og oppdater lokal historikk
    hist = []
    if BDI_HIST.exists():
        try:
            hist = json.loads(BDI_HIST.read_text())
        except Exception:
            pass
    # Legg til dagens verdi (én per dag)
    if not hist or hist[-1]["date"] != today:
        hist.append({"date": today, "close": curr})
    else:
        hist[-1]["close"] = curr  # oppdater hvis allerede hentet i dag
    hist = hist[-60:]  # behold maks 60 dager
    BDI_HIST.write_text(json.dumps(hist, ensure_ascii=False))

    closes = [h["close"] for h in hist]
    if len(closes) < 2:
        # Ikke nok historikk — bruk absolutte terskler
        signal = "bull" if curr > 2000 else "bear" if curr < 1000 else "neutral"
        return {
            "value": curr, "prev": curr, "chg1d": 0.0,
            "ma20": curr, "dev_ma": 0.0,
            "trend": "UKJENT", "signal": signal,
            "date": today, "history": [curr],
        }

    prev   = closes[-2]
    ma20   = sum(closes[-20:]) / min(len(closes), 20)
    chg1d  = round((curr - prev) / prev * 100, 1)
    dev_ma = round((curr - ma20) / ma20 * 100, 1)
    trend_v = curr - closes[max(0, len(closes) - 6)]
    trend   = "STIGENDE" if trend_v > 0 else "FALLENDE"
    if len(closes) >= 5:
        signal = "bull" if dev_ma > 15 else "bear" if dev_ma < -15 else "neutral"
    else:
        signal = "bull" if curr > 2000 else "bear" if curr < 1000 else "neutral"

    return {
        "value":   curr,
        "prev":    round(prev),
        "chg1d":   chg1d,
        "ma20":    round(ma20),
        "dev_ma":  dev_ma,
        "trend":   trend,
        "signal":  signal,
        "date":    today,
        "history": [round(c) for c in closes[-15:]],
    }


# ── Hjelpe-funksjoner ─────────────────────────────────────────────
def fetch_stooq(symbol):
    """Henter daglig CSV for et stooq-symbol, returnerer indeks-objekt eller None."""
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
                close = float(parts[4])
                date  = parts[0].strip()
                rows.append({"date": date, "close": close})
            except Exception:
                continue
        if not rows:
            return None
        # Strip intraday bar
        if rows[-1]["date"] == today and len(rows) > 1:
            rows = rows[:-1]
        if len(rows) < 3:
            return None
        # Siste 30 dager er nok
        rows = rows[-30:]
        closes = [r["close"] for r in rows]
        curr   = closes[-1]
        prev   = closes[-2]
        ma20   = sum(closes[-20:]) / min(len(closes), 20)
        chg1d  = (curr - prev) / prev * 100
        dev_ma = (curr - ma20) / ma20 * 100
        # 5d trend
        trend_v = curr - closes[max(0, len(closes) - 6)]
        trend   = "STIGENDE" if trend_v > 0 else "FALLENDE"
        if dev_ma > 15:    signal = "bull"
        elif dev_ma < -15: signal = "bear"
        else:              signal = "neutral"
        return {
            "value":   round(curr),
            "prev":    round(prev),
            "chg1d":   round(chg1d, 1),
            "ma20":    round(ma20),
            "dev_ma":  round(dev_ma, 1),
            "trend":   trend,
            "signal":  signal,
            "date":    rows[-1]["date"],
            "history": [round(c) for c in closes[-15:]],
        }
    except Exception as e:
        print(f"  Stooq FEIL ({symbol}): {e}")
        return None


def fetch_news(q):
    """Henter opptil 8 artikler fra Google RSS for et søk."""
    params = urllib.parse.urlencode({
        "q": q["query"], "hl": "en-US", "gl": "US", "ceid": "US:en",
    })
    url = f"{GNEWS_BASE}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8", errors="replace")
        root = ET.fromstring(raw)
        ch   = root.find("channel")
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
                "title":  title,
                "url":    link,
                "source": source,
                "time":   pub_str,
                "cat":    q["id"],
                "label":  q["label"],
            })
        return result
    except Exception as e:
        print(f"  Nyheter FEIL ({q['id']}): {e}")
        return []


def score_routes(all_news):
    """Beregner rute-risiko basert på nyhetssignaler."""
    scores   = {r["id"]: 0 for r in ROUTES}
    articles = {r["id"]: [] for r in ROUTES}
    for art in all_news:
        text = art["title"].lower()
        for route in ROUTES:
            if not any(kw in text for kw in route["keywords"]):
                continue
            disrupt = sum(1 for w in DISRUPTION_WORDS if w in text)
            scores[route["id"]] += 1 + disrupt
            if len(articles[route["id"]]) < 3:
                articles[route["id"]].append(art)
    result = []
    for r in ROUTES:
        s = scores[r["id"]]
        if s >= 5:   risk = "HIGH"
        elif s >= 2: risk = "MEDIUM"
        else:        risk = "LOW"
        result.append({**r, "risk": risk, "risk_score": s, "articles": articles[r["id"]]})
    result.sort(key=lambda x: -x["risk_score"])
    return result


# ── Hoved-logikk ─────────────────────────────────────────────────
print("Henter shipping-data...")

# 1. Indekser — BDI fra tradingeconomics, BCI/BPI/BSI ikke tilgjengelig
print("  Henter Baltic-indekser...")
bdi_data_fresh = fetch_bdi_te()
status = f"{bdi_data_fresh['value']} ({bdi_data_fresh['chg1d']:+.1f}%)" if bdi_data_fresh else "ikke tilgjengelig"
print(f"    {'Baltic Dry Index':25} → {status}")
indices_result = [
    {"id": "bdi", "label": "Baltic Dry Index", "desc": "Tørrbulk totalt", "data": bdi_data_fresh},
    {"id": "bci", "label": "Baltic Capesize",  "desc": "Kull & jernmalm", "data": None},
    {"id": "bpi", "label": "Baltic Panamax",   "desc": "Korn & kull",     "data": None},
    {"id": "bsi", "label": "Baltic Supramax",  "desc": "Korn, stål, fosfat", "data": None},
]

# 2. Nyheter
print("  Henter shipping-nyheter...")
all_news = []
for i, q in enumerate(NEWS_QUERIES):
    if i > 0:
        time.sleep(2)
    arts = fetch_news(q)
    all_news.extend(arts)
    print(f"    {q['label']:15} → {len(arts)} artikler")

all_news.sort(key=lambda x: x["time"], reverse=True)

# 3. Rute-risiko
routes = score_routes(all_news)

# 4. Samlet risikovurdering
high_routes   = [r for r in routes if r["risk"] == "HIGH"]
medium_routes = [r for r in routes if r["risk"] == "MEDIUM"]
if len(high_routes) >= 2:
    overall = "HIGH"
elif high_routes or len(medium_routes) >= 3:
    overall = "MEDIUM"
else:
    overall = "LOW"

# 5. BDI-signal (brukes i samlet vurdering)
bdi_data = next((i["data"] for i in indices_result if i["id"] == "bdi"), None)
bdi_signal = bdi_data["signal"] if bdi_data else "neutral"
bdi_date   = bdi_data["date"]   if bdi_data else None

output = {
    "generated":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "bdi_date":     bdi_date,
    "source":       "tradingeconomics.com · Google News RSS",
    "overall_risk": overall,
    "bdi_signal":   bdi_signal,
    "indices":      indices_result,
    "routes":       routes,
    "news":         all_news[:50],
    "_meta": {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "script": "fetch_shipping.py",
    },
}

with open(OUT, "w") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

high_r = [r["name"] for r in routes if r["risk"] == "HIGH"]
print(f"\nOK → {OUT}")
print(f"  Samlet risiko: {overall}  |  BDI: {bdi_signal}")
if high_r:
    print(f"  HIGH-ruter: {', '.join(high_r)}")
