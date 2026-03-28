#!/usr/bin/env python3
"""
fetch_crypto.py — Henter krypto-markedsdata
Ingen API-nøkkel kreves. Bruker Yahoo Finance, CoinGecko, alternative.me og Google News RSS.
Lagrer til data/crypto/latest.json
"""
import json, urllib.request, urllib.parse, urllib.error
import xml.etree.ElementTree as ET
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = Path(__file__).parent
OUT  = BASE / "data" / "crypto" / "latest.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

CRYPTO_SYMBOLS = [
    {"key": "BTC",  "symbol": "BTC-USD",  "name": "Bitcoin"},
    {"key": "ETH",  "symbol": "ETH-USD",  "name": "Ethereum"},
    {"key": "SOL",  "symbol": "SOL-USD",  "name": "Solana"},
    {"key": "XRP",  "symbol": "XRP-USD",  "name": "XRP"},
    {"key": "BNB",  "symbol": "BNB-USD",  "name": "BNB"},
    {"key": "ADA",  "symbol": "ADA-USD",  "name": "Cardano"},
    {"key": "DOGE", "symbol": "DOGE-USD", "name": "Dogecoin"},
    {"key": "AVAX", "symbol": "AVAX-USD", "name": "Avalanche"},
]

def fetch_yahoo(symbol, range_="60d", interval="1d"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?interval={interval}&range={range_}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        res = d["chart"]["result"][0]
        q   = res["indicators"]["quote"][0]
        return [(h,l,c) for h,l,c in zip(q.get("high",[]),q.get("low",[]),q.get("close",[])) if h and l and c]
    except Exception as e:
        print(f"  FEIL {symbol}: {e}")
        return []

# ── Priser ────────────────────────────────────────────────
prices = {}
daily_closes = {}
for inst in CRYPTO_SYMBOLS:
    print(f"  {inst['name']}...")
    rows = fetch_yahoo(inst["symbol"])
    if not rows or len(rows) < 2:
        continue
    curr = rows[-1][2]
    c1   = rows[-2][2]
    c7   = rows[-8][2]  if len(rows) >= 8  else curr
    c30  = rows[-31][2] if len(rows) >= 31 else curr
    dec  = 8 if curr < 0.01 else 5 if curr < 1 else 4 if curr < 10 else 2 if curr < 1000 else 0
    prices[inst["key"]] = {
        "name":   inst["name"],
        "price":  round(curr, dec),
        "chg1d":  round((curr/c1-1)*100,  2),
        "chg7d":  round((curr/c7-1)*100,  2),
        "chg30d": round((curr/c30-1)*100, 2),
    }
    daily_closes[inst["key"]] = [r[2] for r in rows]

# Hent SPX og Gull for korrelasjon
for key, sym in [("SPX", "^GSPC"), ("Gold", "GC=F")]:
    rows = fetch_yahoo(sym)
    if rows:
        daily_closes[key] = [r[2] for r in rows]

# ── Pearson-korrelasjon (30 dager) ────────────────────────
def pearson(a, b, n=30):
    pairs = list(zip(a, b))[-n:]
    if len(pairs) < 5:
        return None
    ra = [pairs[i][0]/pairs[i-1][0]-1 for i in range(1, len(pairs))]
    rb = [pairs[i][1]/pairs[i-1][1]-1 for i in range(1, len(pairs))]
    ma, mb = sum(ra)/len(ra), sum(rb)/len(rb)
    num  = sum((ra[i]-ma)*(rb[i]-mb) for i in range(len(ra)))
    da   = sum((x-ma)**2 for x in ra)**0.5
    db   = sum((x-mb)**2 for x in rb)**0.5
    if da*db == 0:
        return 0.0
    return round(num/(da*db), 2)

btc = daily_closes.get("BTC", [])
correlations = {
    "btc_spx":  pearson(btc, daily_closes.get("SPX",  [])),
    "btc_gold": pearson(btc, daily_closes.get("Gold", [])),
    "eth_btc":  pearson(daily_closes.get("ETH", []), btc),
    "sol_btc":  pearson(daily_closes.get("SOL", []), btc),
    "xrp_btc":  pearson(daily_closes.get("XRP", []), btc),
}

# ── CoinGecko — global markedsdata ───────────────────────
market = {}
try:
    req = urllib.request.Request(
        "https://api.coingecko.com/api/v3/global",
        headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        cg = json.loads(r.read()).get("data", {})
    market = {
        "btc_dominance":     round(cg.get("market_cap_percentage", {}).get("btc", 0), 1),
        "eth_dominance":     round(cg.get("market_cap_percentage", {}).get("eth", 0), 1),
        "total_mcap":        cg.get("total_market_cap", {}).get("usd"),
        "total_mcap_chg24h": round(cg.get("market_cap_change_percentage_24h_usd", 0), 2),
        "active_coins":      cg.get("active_cryptocurrencies"),
    }
    print(f"  CoinGecko: BTC dom={market['btc_dominance']}%")
except Exception as e:
    print(f"  CoinGecko FEIL: {e}")

# ── Krypto Fear & Greed (alternative.me) ─────────────────
fear_greed = {}
try:
    req = urllib.request.Request(
        "https://api.alternative.me/fng/?limit=7&format=json",
        headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        fg = json.loads(r.read())
    entries = fg.get("data", [])
    if entries:
        fear_greed = {
            "score":   int(entries[0]["value"]),
            "label":   entries[0]["value_classification"],
            "history": [int(e["value"]) for e in reversed(entries)],
        }
    print(f"  Krypto F&G: {fear_greed.get('score')} ({fear_greed.get('label')})")
except Exception as e:
    print(f"  Fear&Greed FEIL: {e}")

# ── Bitcoin COT fra combined/latest.json ──────────────────
cot_btc = {}
combined_file = BASE / "data" / "combined" / "latest.json"
if combined_file.exists():
    try:
        with open(combined_file) as f:
            combined = json.load(f)
        for entry in combined:
            m = entry.get("market", "").lower()
            if "bitcoin" in m and entry.get("report") == "tff" and "micro" not in m and "nano" not in m:
                sp  = entry.get("spekulanter", {})
                oi  = entry.get("open_interest", 1) or 1
                net = sp.get("net", 0) or 0
                cot_btc = {
                    "market":  entry["market"],
                    "net":     net,
                    "chg":     entry.get("change_spec_net", 0),
                    "oi":      oi,
                    "pct":     round(net / oi * 100, 1),
                    "date":    entry.get("date", ""),
                    "history": entry.get("spec_net_history", []),
                }
                break
        print(f"  COT BTC: net={cot_btc.get('net','?')}  pct={cot_btc.get('pct','?')}%")
    except Exception as e:
        print(f"  COT FEIL: {e}")

# ── Krypto-nyheter fra Google News RSS ────────────────────
news = []
QUERIES = [
    ("bitcoin", "Bitcoin"),
    ("ethereum DeFi crypto", "DeFi / Ethereum"),
    ("crypto regulation SEC CFTC", "Regulering"),
    ("altcoin market crypto rally", "Altcoins"),
]
for i, (query, label) in enumerate(QUERIES):
    if i > 0:
        time.sleep(2)
    try:
        params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        url = f"https://news.google.com/rss/search?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            root = ET.fromstring(r.read().decode("utf-8", errors="replace"))
        channel = root.find("channel")
        if channel is None:
            continue
        for item in channel.findall("item")[:6]:
            title = item.findtext("title", "").strip()
            link  = item.findtext("link",  "").strip()
            src   = item.find("source")
            source = src.text.strip() if src is not None and src.text else ""
            try:
                pub_str = parsedate_to_datetime(item.findtext("pubDate","")).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pub_str = ""
            if title:
                news.append({"title": title, "url": link, "source": source, "time": pub_str, "cat": label})
        print(f"  Nyheter {label}: OK")
    except Exception as e:
        print(f"  Nyheter FEIL ({label}): {e}")

seen, unique_news = set(), []
for n in sorted(news, key=lambda x: x["time"], reverse=True):
    if n["title"] not in seen:
        seen.add(n["title"])
        unique_news.append(n)

result = {
    "updated":      datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "prices":       prices,
    "market":       market,
    "fear_greed":   fear_greed,
    "correlations": correlations,
    "cot_btc":      cot_btc,
    "news":         unique_news[:30],
}

with open(OUT, "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\nOK → {OUT}  ({len(prices)} priser, {len(unique_news)} nyheter)")
