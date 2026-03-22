#!/usr/bin/env python3
import json, os, re

BASE = os.path.expanduser("~/cot-explorer/data")
TS   = os.path.join(BASE, "timeseries")
OUT  = os.path.join(BASE, "combined", "latest.json")
os.makedirs(os.path.join(BASE, "combined"), exist_ok=True)

CATS = {
    "aksjer":    ["s&p","nasdaq","russell","nikkei","msci","vix","topix","dow","djia"],
    "valuta":    ["euro fx","japanese yen","british pound","swiss franc","canadian dollar",
                  "australian dollar","nz dollar","mexican peso","so african rand",
                  "usd index","brazilian real","nok","sek"],
    "renter":    ["treasury","t-note","t-bond","sofr","eurodollar","swap","eris",
                  "federal fund","libor","bund","bobl","schatz"],
    "ravarer":   ["crude oil","natural gas","gasoline","heating oil","gold","silver",
                  "copper","platinum","palladium","lumber","wti","brent","rbob","coal"],
    "krypto":    ["bitcoin","ether","solana","xrp","litecoin","doge"],
    "landbruk":  ["corn","wheat","soybean","coffee","sugar","cocoa","cotton","cattle",
                  "hogs","lean","live","feeder","oats","rice","milk","butter","canola",
                  "orange juice","lumber"],
}

NAVN = {
    "s&p 500 consolidated":     "S&P 500",
    "nasdaq mini":              "Nasdaq 100",
    "nasdaq-100":               "Nasdaq 100",
    "dow jones":                "Dow Jones",
    "russell e-mini":           "Russell 2000",
    "vix futures":              "VIX – Frykt",
    "nikkei stock average":     "Nikkei 225",
    "euro fx":                  "EUR/USD",
    "japanese yen":             "USD/JPY",
    "british pound":            "GBP/USD",
    "swiss franc":              "USD/CHF",
    "canadian dollar":          "USD/CAD",
    "australian dollar":        "AUD/USD",
    "nz dollar":                "NZD/USD",
    "so african rand":          "USD/ZAR",
    "usd index":                "DXY Dollar",
    "mexican peso":             "USD/MXN",
    "brazilian real":           "USD/BRL",
    "gold":                     "Gull",
    "silver":                   "Solv",
    "copper":                   "Kobber",
    "platinum":                 "Platina",
    "palladium":                "Palladium",
    "crude oil, light sweet":   "WTI Råolje",
    "natural gas":              "Naturgass",
    "gasoline rbob":            "Bensin",
    "heating oil":              "Fyringsolje",
    "corn":                     "Mais",
    "wheat-srw":                "Hvete",
    "wheat":                    "Hvete",
    "soybeans":                 "Soyabønner",
    "soybean":                  "Soyabønner",
    "coffee c":                 "Kaffe",
    "sugar no. 11":             "Sukker",
    "cocoa":                    "Kakao",
    "cotton no. 2":             "Bomull",
    "live cattle":              "Storfe",
    "lean hogs":                "Gris",
    "feeder cattle":            "Ungnaut",
    "bitcoin":                  "Bitcoin",
    "ether cash settled":       "Ethereum",
    "u.s. treasury bonds":      "US T-Bond 30Y",
    "10-year u.s. treasury notes": "US T-Note 10Y",
    "5-year u.s. treasury notes":  "US T-Note 5Y",
    "2-year u.s. treasury notes":  "US T-Note 2Y",
    "30-day federal funds":     "Fed Funds",
    "sofr":                     "SOFR",
}

def get_kat(market):
    ml = market.lower()
    for kat, keys in CATS.items():
        if any(k in ml for k in keys):
            return kat
    return "annet"

def get_navn(market):
    ml = market.lower().strip()
    for k, v in NAVN.items():
        if k in ml:
            return v
    # Tittelcase som fallback
    return market.title()[:40]

def is_junk(market):
    m = market.strip()
    # Hopp over rene tall, enkeltbokstaver, "long", "short" etc
    if re.fullmatch(r'[\d\s]+', m): return True
    if len(m) <= 3: return True
    if m.lower() in ('long','short','total','other','index','fund','swap'): return True
    return False

result = []
seen = set()

for fname in sorted(os.listdir(TS)):
    if not fname.endswith('.json') or fname == 'index.json':
        continue
    path = os.path.join(TS, fname)
    try:
        with open(path) as f:
            ts = json.load(f)
    except:
        continue

    market = ts.get("market","").strip()
    if not market or is_junk(market):
        continue

    data = ts.get("data", [])
    if len(data) < 2:
        continue

    # Finn siste rad med dato + forrige
    latest = prev = None
    for row in reversed(data):
        if row.get("date") and row.get("spec_net") is not None:
            if latest is None: latest = row
            elif prev is None: prev = row; break
    if not latest:
        continue

    net  = latest.get("spec_net", 0) or 0
    net_p= (prev.get("spec_net", 0) or 0) if prev else 0
    chg  = net - net_p
    oi   = latest.get("oi", 0) or 0
    kat  = ts.get("kategori") or get_kat(market)
    rep  = ts.get("report", fname.split("_")[-1].replace(".json",""))

    # Unngå duplikater (samme marked, ulik rapport – velg en)
    mk = market.lower()
    uid = mk + "_" + kat
    if uid in seen:
        continue
    seen.add(uid)

    result.append({
        "symbol":          ts.get("symbol",""),
        "market":          market,
        "navn_no":         get_navn(market),
        "kategori":        kat,
        "report":          rep,
        "forklaring":      "",
        "date":            latest.get("date",""),
        "spekulanter":     {"net": net, "long": latest.get("spec_long",0) or 0, "short": latest.get("spec_short",0) or 0},
        "open_interest":   oi,
        "change_spec_net": chg,
    })

result.sort(key=lambda x: abs(x["spekulanter"]["net"]), reverse=True)

with open(OUT, "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"OK: {len(result)} markeder → {OUT}")
# Vis topp 10
for d in result[:10]:
    print(f"  {d['navn_no']:25s}  net={d['spekulanter']['net']:>10,}  {d['kategori']:10s}  {d['date']}")
