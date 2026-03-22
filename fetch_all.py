#!/usr/bin/env python3
"""
Markedspuls – Henter all markedsdata + beregner trading-setups
"""
import urllib.request, zipfile, csv, json, os, sys, shutil
from datetime import datetime, timezone, timedelta

opener = urllib.request.build_opener()
opener.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")]
urllib.request.install_opener(opener)

def fetch_json(url, timeout=10):
    try:
        res = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(res.read())
    except Exception as e:
        print(f"  Feil: {e}")
        return None

def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

today = datetime.now().strftime("%Y-%m-%d")
now_utc = datetime.now(timezone.utc)
now_str = now_utc.isoformat()

print("=" * 50)
print("Markedspuls – Datanedlasting")
print(f"Tid: {now_str[:19]}")
print("=" * 50)

# ── 1. MARKEDSPRISER ──
print("\n[MARKEDSPRISER]")
PRICE_SYMBOLS = {
    "VIX":"^VIX","DXY":"DX-Y.NYB","Brent":"BZ=F","WTI":"CL=F",
    "Gold":"GC=F","Silver":"SI=F","SPX":"^GSPC","NAS100":"^NDX",
    "HYG":"HYG","TIP":"TIP","EURUSD":"EURUSD=X","USDJPY":"USDJPY=X",
    "GBPUSD":"GBPUSD=X","USDCHF":"USDCHF=X","AUDUSD":"AUDUSD=X",
    "NZDUSD":"NZDUSD=X","USDCAD":"USDCAD=X","USDSEK":"USDSEK=X","USDNOK":"USDNOK=X",
}

prices = {}
for name, sym in PRICE_SYMBOLS.items():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=22d"
    data = fetch_json(url)
    if data and data.get("chart",{}).get("result"):
        r = data["chart"]["result"][0]
        closes = [c for c in r["indicators"]["quote"][0]["close"] if c]
        if len(closes) >= 2:
            c,p = closes[-1],closes[-2]
            c5 = closes[-6] if len(closes)>=6 else closes[0]
            prices[name] = {"price":round(c,4),"chg1d":round((c/p-1)*100,2),"chg5d":round((c/c5-1)*100,2),"symbol":sym}
            print(f"  {name}: {prices[name]['price']} | 1d:{prices[name]['chg1d']}%")

# ── 2. TRADING LEVELS + SETUPS ──
print("\n[TRADING LEVELS & SETUPS]")

INSTRUMENTS = {
    "EUR/USD": {"symbol":"EURUSD=X","class":"A","cot_key":"Euro Fx",               "pip":0.0001,"spread":0.0001,"label":"Euro/Dollar",    "session_cet":[(8,12),(14,16)]},
    "GBP/USD": {"symbol":"GBPUSD=X","class":"A","cot_key":"British Pound",         "pip":0.0001,"spread":0.00013,"label":"Pund/Dollar",   "session_cet":[(8,12),(14,16)]},
    "USD/JPY": {"symbol":"USDJPY=X","class":"A","cot_key":"Japanese Yen",          "pip":0.01,  "spread":0.01,  "label":"Dollar/Yen",     "session_cet":[(8,12),(14,16)]},
    "USD/CHF": {"symbol":"USDCHF=X","class":"A","cot_key":"Swiss Franc",           "pip":0.0001,"spread":0.00012,"label":"Dollar/Franc",  "session_cet":[(8,12),(14,16)]},
    "AUD/USD": {"symbol":"AUDUSD=X","class":"A","cot_key":"Australian Dollar",     "pip":0.0001,"spread":0.00012,"label":"Aussie/Dollar", "session_cet":[(8,12),(14,16)]},
    "XAU/USD": {"symbol":"GC=F",    "class":"B","cot_key":"Gold",                  "pip":0.1,   "spread":0.3,   "label":"Gull (XAU)",     "session_cet":[(9,11),(14,16)]},
    "NAS100":  {"symbol":"^NDX",    "class":"C","cot_key":"Nasdaq",                "pip":1.0,   "spread":1.0,   "label":"Nasdaq 100",     "session_cet":[(14,17)]},
    "SPX500":  {"symbol":"^GSPC",   "class":"C","cot_key":"S&P 500 Consolidated",  "pip":0.25,  "spread":0.5,   "label":"S&P 500",        "session_cet":[(14,17)]},
    "WTI":     {"symbol":"CL=F",    "class":"B","cot_key":"Crude Oil, Light Sweet","pip":0.01,  "spread":0.03,  "label":"Råolje (WTI)",   "session_cet":[(9,11),(14,16)]},
}

levels = {}
for name, cfg in INSTRUMENTS.items():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{cfg['symbol']}?interval=1d&range=250d"
    data = fetch_json(url)
    if not data or not data.get("chart",{}).get("result"):
        continue
    try:
        r = data["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        H = [x for x in q["high"]  if x]
        L = [x for x in q["low"]   if x]
        C = [x for x in q["close"] if x]
        if len(C) < 10: continue

        curr = round(C[-1], 6)
        pdh  = round(H[-2], 6)
        pdl  = round(L[-2], 6)
        pdc  = round(C[-2], 6)
        pwh  = round(max(H[-6:-1]), 6)
        pwl  = round(min(L[-6:-1]), 6)
        sma200 = round(sum(C[-200:])/min(len(C),200), 6)

        trs = []
        for i in range(max(-15,-len(C)+1), 0):
            tr = max(H[i]-L[i], abs(H[i]-C[i-1]), abs(L[i]-C[i-1]))
            trs.append(tr)
        atr14 = round(sum(trs)/len(trs), 6) if trs else cfg["pip"]*10

        chg5d  = round((curr/C[-6]-1)*100, 2) if len(C)>=6 else 0
        chg20d = round((curr/C[-21]-1)*100, 2) if len(C)>=21 else 0

        all_levels = [
            {"level":pwh,   "name":"PWH",   "type":"resistance", "weight":3},
            {"level":pdh,   "name":"PDH",   "type":"resistance", "weight":2},
            {"level":sma200,"name":"SMA200","type":"trend",       "weight":2},
            {"level":pdc,   "name":"PDC",   "type":"pivot",       "weight":1},
            {"level":pdl,   "name":"PDL",   "type":"support",     "weight":2},
            {"level":pwl,   "name":"PWL",   "type":"support",     "weight":3},
        ]
        for lv in all_levels:
            lv["dist"]     = round(abs(lv["level"] - curr), 6)
            lv["dist_atr"] = round(lv["dist"] / atr14, 2) if atr14 > 0 else 99
            lv["active"]   = lv["dist_atr"] <= 1.0

        resistances = sorted([lv for lv in all_levels if lv["level"] > curr], key=lambda x: x["level"])
        supports    = sorted([lv for lv in all_levels if lv["level"] < curr], key=lambda x: x["level"], reverse=True)

        levels[name] = {
            "name": name, "label": cfg["label"], "class": cfg["class"],
            "cot_key": cfg["cot_key"], "pip": cfg["pip"], "spread": cfg["spread"],
            "session_cet": cfg["session_cet"],
            "current": curr, "pdh": pdh, "pdl": pdl, "pdc": pdc,
            "pwh": pwh, "pwl": pwl, "sma200": sma200,
            "above_sma200": curr > sma200,
            "atr14": atr14, "chg5d": chg5d, "chg20d": chg20d,
            "resistances": resistances[:4],
            "supports": supports[:4],
            "all_levels": all_levels,
        }
        print(f"  {name}: {curr} | ATR={atr14:.5f} | PDH={pdh} | PDL={pdl}")
    except Exception as e:
        print(f"  {name}: feil – {e}")

# ── 3. MAKRO OG DOLLAR-SMIL ──
vix    = prices.get("VIX",{}).get("price",0)
hyg5d  = prices.get("HYG",{}).get("chg5d",0)
brent  = prices.get("Brent",{}).get("price",0)
tip5d  = prices.get("TIP",{}).get("chg5d",0)
dxy5d  = prices.get("DXY",{}).get("chg5d",0)
hy_stress = hyg5d < -1.0

if vix > 25 or hy_stress:
    smile_pos="venstre"; smile_label="Krise/Risk-off"
    smile_desc="USD styrkes. Kjøp USD, CHF, JPY. Unngå NOK, AUD, NZD."
    usd_bias="KJØP"; usd_color="bull"
elif brent > 85 or tip5d > 0.5:
    smile_pos="hoyre"; smile_label="Vekst/Inflasjon"
    smile_desc="USD styrkes. Fed on-hold. Inflasjonspremium."
    usd_bias="KJØP"; usd_color="bull"
else:
    smile_pos="midten"; smile_label="Goldilocks"
    smile_desc="USD svekkes. Fed kutter. Risikoappetitt normal."
    usd_bias="SELG"; usd_color="bear"

vix_regime = "normal" if vix<20 else "stress" if vix<30 else "krise"
vix_label  = "Full størrelse" if vix<20 else "Halv størrelse" if vix<30 else "Kvart størrelse"
vix_color  = "bull" if vix<20 else "warn" if vix<30 else "bear"

# VIX spread-faktor
vix_spread_factor = 1.5 if vix < 20 else 2.0 if vix < 30 else 3.0

# ── 4. KALENDER ──
print("\n[KALENDER]")
calendar = []
try:
    data = fetch_json("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
    if data:
        for e in data:
            if e.get("impact") in ["High","Medium"]:
                calendar.append({
                    "date":e.get("date",""),"title":e.get("title",""),
                    "country":e.get("country",""),"impact":e.get("impact",""),
                    "forecast":e.get("forecast",""),"previous":e.get("previous",""),
                })
        print(f"  {len(calendar)} hendelser")
except Exception as e:
    print(f"  Kalender feil: {e}")

# Finn binær risiko per instrument de neste 4 timene
def get_binary_risk(instrument_class, calendar_events, now):
    window_start = now
    window_end   = now + timedelta(hours=4)
    CLASS_COUNTRIES = {
        "A": ["USD","EUR","GBP","JPY","CHF","AUD","NZD","CAD"],
        "B": ["USD","EUR"],
        "C": ["USD"],
    }
    countries = CLASS_COUNTRIES.get(instrument_class, ["USD"])
    risks = []
    for e in calendar_events:
        if e.get("impact") != "High":
            continue
        try:
            et = datetime.fromisoformat(e["date"].replace("Z","+00:00"))
            if et.tzinfo is None:
                et = et.replace(tzinfo=timezone.utc)
            if window_start <= et <= window_end and e.get("country") in countries:
                risks.append({"title": e["title"], "time": e["date"], "country": e["country"]})
        except:
            pass
    return risks

# ── 5. SESSION-VALIDERING ──
def get_session_status(session_cet, now_utc):
    # Konverter til CET (UTC+1 vinter, UTC+2 sommer – bruk UTC+1 som fast)
    now_cet = now_utc + timedelta(hours=1)
    hour = now_cet.hour
    minute = now_cet.minute
    now_decimal = hour + minute/60.0

    for start, end in session_cet:
        if start <= now_decimal <= end:
            return {"active": True, "next": None, "label": f"Aktiv ({start:02d}:00-{end:02d}:00 CET)"}

    # Finn neste sesjon
    next_sessions = [(s,e) for s,e in session_cet if s > now_decimal]
    if next_sessions:
        ns, ne = next_sessions[0]
        mins = int((ns - now_decimal) * 60)
        return {"active": False, "next": f"{ns:02d}:00", "label": f"Starter om {mins}min ({ns:02d}:00 CET)"}
    return {"active": False, "next": None, "label": "Utenfor sesjon i dag"}

# ── 6. COT DATA ──
YEAR = datetime.now().year
BASE = "https://www.cftc.gov/files/dea/history"
REPORTS = [
    {"id":"tff",           "url":f"{BASE}/fut_fin_txt_{YEAR}.zip"},
    {"id":"legacy",        "url":f"{BASE}/com_disagg_txt_{YEAR}.zip"},
    {"id":"disaggregated", "url":f"{BASE}/fut_disagg_txt_{YEAR}.zip"},
    {"id":"supplemental",  "url":f"{BASE}/dea_cit_txt_{YEAR}.zip"},
]
CATEGORIES = {
    "aksjer":["s&p","nasdaq","russell","nikkei","msci","vix"],
    "valuta":["euro fx","japanese yen","british pound","swiss franc","canadian dollar","australian dollar","nz dollar","mexican peso","so african rand","usd index"],
    "renter":["ust","sofr","eurodollar","treasury","t-note","t-bond","swap","eris"],
    "ravarer":["crude oil","natural gas","gold","silver","copper","platinum","palladium","lumber","rbob","gasoline","heating oil"],
    "krypto":["bitcoin","ether","solana","xrp","nano","zcash","sui"],
    "landbruk":["corn","wheat","soybean","coffee","sugar","cocoa","cotton","cattle","hogs","lean","live","feeder"],
    "volatilitet":["vix"],
}
MARKET_NO = {
    "S&P 500 Consolidated":{"no":"S&P 500","info":"De 500 største selskapene i USA."},
    "Nasdaq":{"no":"Nasdaq 100","info":"Teknologiindeks. Apple, Microsoft, Nvidia m.fl."},
    "Nasdaq Mini":{"no":"Nasdaq Mini","info":"Mindre Nasdaq-kontrakt."},
    "Russell E":{"no":"Russell 2000","info":"2000 mindre amerikanske selskaper."},
    "Msci Eafe":{"no":"MSCI Europa/Asia","info":"Aksjer utenfor USA."},
    "Msci Em Index":{"no":"MSCI Fremvoksende","info":"Kina, India, Brasil m.fl."},
    "Nikkei Stock Average":{"no":"Nikkei (Japan)","info":"Tokyo-børsens 225 største."},
    "Vix Futures":{"no":"VIX – Fryktindeks","info":"Høy = mye usikkerhet."},
    "Euro Fx":{"no":"EUR/USD","info":"Euro mot dollar."},
    "Japanese Yen":{"no":"USD/JPY","info":"Dollar mot yen."},
    "British Pound":{"no":"GBP/USD","info":"Pund mot dollar."},
    "Swiss Franc":{"no":"USD/CHF","info":"Dollar mot franc."},
    "Canadian Dollar":{"no":"USD/CAD","info":"Dollar mot kanadisk dollar."},
    "Australian Dollar":{"no":"AUD/USD","info":"Australsk dollar mot USD."},
    "Nz Dollar":{"no":"NZD/USD","info":"NZD mot USD."},
    "So African Rand":{"no":"USD/ZAR","info":"Dollar mot rand."},
    "Usd Index":{"no":"DXY","info":"Styrken til USD mot 6 valutaer."},
    "Ust 2Y Note":{"no":"US 2-årig rente","info":"Sensitiv for Fed."},
    "Ust 5Y Note":{"no":"US 5-årig rente","info":"Mellomlang statsrente."},
    "Ust 10Y Note":{"no":"US 10-årig rente","info":"Viktigste globale rente."},
    "Ust Bond":{"no":"US 30-årig rente","info":"Langsiktig rente."},
    "Sofr":{"no":"SOFR","info":"Kortsiktig dollarlånsrente."},
    "Bitcoin":{"no":"Bitcoin (BTC)","info":"Verdens største krypto."},
    "Nano Bitcoin":{"no":"Bitcoin Mini","info":"1/100 BTC kontrakt."},
    "Crude Oil, Light Sweet":{"no":"Råolje (WTI)","info":"Amerikansk råolje."},
    "Natural Gas":{"no":"Naturgass","info":"Energiråvare."},
    "Gold":{"no":"Gull (XAU)","info":"Trygg havn i urolige tider."},
    "Silver":{"no":"Sølv (XAG)","info":"Industri og investering."},
    "Corn":{"no":"Mais","info":"Viktigste kornavling i USA."},
    "Soybeans":{"no":"Soyabønner","info":"Nest viktigste kornavling."},
}

def safe_int(v):
    try: return int(str(v).strip().replace(",","").split(".")[0])
    except: return 0

def get_category(n):
    nl = n.lower()
    for cat, kws in CATEGORIES.items():
        for kw in kws:
            if kw in nl: return cat
    return "annet"

def download_extract(url, tmp):
    zp = os.path.join(tmp,"cot.zip")
    try:
        urllib.request.urlretrieve(url, zp)
        with zipfile.ZipFile(zp,"r") as z: z.extractall(tmp)
        for f in os.listdir(tmp):
            if f.endswith(".txt"): return os.path.join(tmp, f)
    except Exception as e: print(f"  Feil: {e}")
    return None

def parse_cot(csv_file, rid):
    results = {}
    try:
        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("Market_and_Exchange_Names","").strip()
                date = row.get("Report_Date_as_YYYY-MM-DD","").strip()
                sym  = row.get("CFTC_Contract_Market_Code","").strip()
                mkt  = name.split("-")[0].strip().title()
                oi   = safe_int(row.get("Open_Interest_All",0))
                chg  = safe_int(row.get("Change_in_Open_Interest_All",0))
                if rid=="tff":
                    sl=safe_int(row.get("Lev_Money_Positions_Long_All",0)); ss=safe_int(row.get("Lev_Money_Positions_Short_All",0))
                    il=safe_int(row.get("Asset_Mgr_Positions_Long_All",0)); i_=safe_int(row.get("Asset_Mgr_Positions_Short_All",0))
                    dl=safe_int(row.get("Dealer_Positions_Long_All",0)); ds=safe_int(row.get("Dealer_Positions_Short_All",0))
                    nl=safe_int(row.get("NonRept_Positions_Long_All",0)); ns=safe_int(row.get("NonRept_Positions_Short_All",0))
                    cs=safe_int(row.get("Change_in_Lev_Money_Long_All",0))-safe_int(row.get("Change_in_Lev_Money_Short_All",0))
                    entry={"date":date,"market":mkt,"symbol":sym,"report":"tff","open_interest":oi,"change_oi":chg,"change_spec_net":cs,
                        "spekulanter":{"long":sl,"short":ss,"net":sl-ss,"label":"Hedge Funds"},
                        "institusjoner":{"long":il,"short":i_,"net":il-i_,"label":"Pensjonsfond"},
                        "meglere":{"long":dl,"short":ds,"net":dl-ds,"label":"Banker/Meglere"},
                        "smahandlere":{"long":nl,"short":ns,"net":nl-ns,"label":"Smahandlere"}}
                elif rid=="legacy":
                    sl=safe_int(row.get("NonComm_Positions_Long_All",0)); ss=safe_int(row.get("NonComm_Positions_Short_All",0))
                    cl=safe_int(row.get("Comm_Positions_Long_All",0)); cs_=safe_int(row.get("Comm_Positions_Short_All",0))
                    nl=safe_int(row.get("NonRept_Positions_Long_All",0)); ns=safe_int(row.get("NonRept_Positions_Short_All",0))
                    cs=safe_int(row.get("Change_in_NonComm_Long_All",0))-safe_int(row.get("Change_in_NonComm_Short_All",0))
                    entry={"date":date,"market":mkt,"symbol":sym,"report":"legacy","open_interest":oi,"change_oi":chg,"change_spec_net":cs,
                        "spekulanter":{"long":sl,"short":ss,"net":sl-ss,"label":"Store Spekulanter"},
                        "kommersielle":{"long":cl,"short":cs_,"net":cl-cs_,"label":"Produsenter/Hedgers"},
                        "smahandlere":{"long":nl,"short":ns,"net":nl-ns,"label":"Smahandlere"}}
                elif rid=="disaggregated":
                    sl=safe_int(row.get("M_Money_Positions_Long_All",0)); ss=safe_int(row.get("M_Money_Positions_Short_All",0))
                    pl=safe_int(row.get("Prod_Merc_Positions_Long_All",0)); ps=safe_int(row.get("Prod_Merc_Positions_Short_All",0))
                    nl=safe_int(row.get("NonRept_Positions_Long_All",0)); ns=safe_int(row.get("NonRept_Positions_Short_All",0))
                    cs=safe_int(row.get("Change_in_M_Money_Long_All",0))-safe_int(row.get("Change_in_M_Money_Short_All",0))
                    entry={"date":date,"market":mkt,"symbol":sym,"report":"disaggregated","open_interest":oi,"change_oi":chg,"change_spec_net":cs,
                        "spekulanter":{"long":sl,"short":ss,"net":sl-ss,"label":"Managed Money"},
                        "produsenter":{"long":pl,"short":ps,"net":pl-ps,"label":"Produsenter"},
                        "smahandlere":{"long":nl,"short":ns,"net":nl-ns,"label":"Smahandlere"}}
                elif rid=="supplemental":
                    sl=safe_int(row.get("NonComm_Positions_Long_All",0)); ss=safe_int(row.get("NonComm_Positions_Short_All",0))
                    cl=safe_int(row.get("Comm_Positions_Long_All",0)); cs_=safe_int(row.get("Comm_Positions_Short_All",0))
                    il=safe_int(row.get("Index_Positions_Long_All",0)); i_=safe_int(row.get("Index_Positions_Short_All",0))
                    nl=safe_int(row.get("NonRept_Positions_Long_All",0)); ns=safe_int(row.get("NonRept_Positions_Short_All",0))
                    cs=safe_int(row.get("Change_in_NonComm_Long_All",0))-safe_int(row.get("Change_in_NonComm_Short_All",0))
                    entry={"date":date,"market":mkt,"symbol":sym,"report":"supplemental","open_interest":oi,"change_oi":chg,"change_spec_net":cs,
                        "spekulanter":{"long":sl,"short":ss,"net":sl-ss,"label":"Store Spekulanter"},
                        "kommersielle":{"long":cl,"short":cs_,"net":cl-cs_,"label":"Produsenter/Hedgers"},
                        "indeksfond":{"long":il,"short":i_,"net":il-i_,"label":"Indeksfond"},
                        "smahandlere":{"long":nl,"short":ns,"net":nl-ns,"label":"Smahandlere"}}
                else: continue
                entry["kategori"] = get_category(name)
                info = MARKET_NO.get(mkt,{})
                entry["navn_no"] = info.get("no",mkt)
                entry["forklaring"] = info.get("info","")
                if mkt not in results or date > results[mkt]["date"]: results[mkt] = entry
    except Exception as e: print(f"  Parse-feil: {e}")
    return list(results.values())

print("\n[COT-DATA]")
all_cot = []
for report in REPORTS:
    rid = report["id"]; print(f"  Laster {rid}...")
    tmp = f"/tmp/cot_{rid}"; os.makedirs(tmp, exist_ok=True)
    csv_file = download_extract(report["url"], tmp)
    if csv_file:
        data = parse_cot(csv_file, rid)
        if data:
            save(f"data/{rid}/latest.json", data)
            save(f"data/{rid}/{today}.json", data)
            all_cot.extend(data); print(f"  {len(data)} markeder")
    shutil.rmtree(tmp, ignore_errors=True)

seen = set(); combined = []
for d in all_cot:
    key = d["symbol"] + d["report"]
    if key not in seen: seen.add(key); combined.append(d)
combined.sort(key=lambda x:(x["kategori"],x["navn_no"]))
save("data/combined/latest.json", combined)
save(f"data/combined/{today}.json", combined)

# ── 7. KNYTT COT + BEREGN SETUP ──
print("\n[BEREGNER SETUPS]")
cot_lookup = {}
for d in combined:
    cot_lookup[d["market"].lower()] = d
    cot_lookup[d.get("navn_no","").lower()] = d

for name, lv in levels.items():
    # Finn COT
    cot = None
    for key in [lv["cot_key"].lower(), lv["cot_key"].title().lower(), name.lower()]:
        if key in cot_lookup:
            cot = cot_lookup[key]; break
    if not cot:
        for d in combined:
            if lv["cot_key"].lower() in d["market"].lower():
                cot = d; break

    spec_net = 0
    cot_bias = "UKJENT"
    cot_color = "neutral"
    cot_chg = 0
    cot_pct = 0
    cot_date = ""
    cot_report = ""

    if cot:
        spec = cot.get("spekulanter",{})
        spec_net = spec.get("net",0)
        oi = cot.get("open_interest",1)
        cot_chg = cot.get("change_spec_net",0)
        cot_pct = round(spec_net/oi*100,1) if oi else 0
        cot_date = cot.get("date","")
        cot_report = cot.get("report","")
        p = spec_net/oi if oi else 0
        if p > 0.15:    cot_bias="STERKT BULLISH"; cot_color="bull"
        elif p > 0.04:  cot_bias="SVAKT BULLISH";  cot_color="bull"
        elif p < -0.15: cot_bias="STERKT BEARISH"; cot_color="bear"
        elif p < -0.04: cot_bias="SVAKT BEARISH";  cot_color="bear"
        else:           cot_bias="NOYTRAL";         cot_color="neutral"

    lv["cot"] = {"bias":cot_bias,"color":cot_color,"net":spec_net,"chg":cot_chg,"pct":cot_pct,"date":cot_date,"report":cot_report}

    # DXY konfluens
    is_usd_quote = name in ["EUR/USD","GBP/USD","AUD/USD","NZD/USD","XAU/USD"]
    dxy_up = dxy5d > 0
    dxy_conf = "motvind" if (is_usd_quote and dxy_up) or (not is_usd_quote and not dxy_up) else "medvind"

    # Session
    session = get_session_status(lv["session_cet"], now_utc)

    # Binær risiko
    binary_risk = get_binary_risk(lv["class"], calendar, now_utc)

    # ── KONFLUENS-SCORE ──
    score = 0.0
    score_details = []

    # 1. SMA200
    if (lv["above_sma200"] and cot_color == "bull") or (not lv["above_sma200"] and cot_color == "bear"):
        score += 1.0
        score_details.append({"kryss":"SMA200 + COT retning stemmer","verdi":True})
    else:
        score_details.append({"kryss":"SMA200 + COT retning stemmer","verdi":False})

    # 2. 5d trend
    if (lv["chg5d"] > 0 and cot_color == "bull") or (lv["chg5d"] < 0 and cot_color == "bear"):
        score += 1.0
        score_details.append({"kryss":"5d trend støtter","verdi":True})
    else:
        score_details.append({"kryss":"5d trend støtter","verdi":False})

    # 3. COT bias (vektet)
    if cot_color in ["bull","bear"]:
        score += 1.5
        score_details.append({"kryss":"COT bias klar","verdi":True})
    else:
        score_details.append({"kryss":"COT bias klar","verdi":False})

    # 4. DXY konfluens
    if dxy_conf == "medvind":
        score += 1.0
        score_details.append({"kryss":"DXY medvind","verdi":True})
    else:
        score_details.append({"kryss":"DXY medvind","verdi":False})

    # 5. Pris innen 1x ATR av nivå
    active_levels = [l for l in lv["all_levels"] if l["dist_atr"] <= 1.0]
    if active_levels:
        score += 1.5
        score_details.append({"kryss":"Pris ved aktivt nivå (1x ATR)","verdi":True})
    else:
        score_details.append({"kryss":"Pris ved aktivt nivå (1x ATR)","verdi":False})

    # 6. VIX-regime
    if vix_regime != "krise":
        score += 0.5
        score_details.append({"kryss":"VIX-regime OK (ikke krise)","verdi":True})
    else:
        score_details.append({"kryss":"VIX-regime OK (ikke krise)","verdi":False})

    # 7. Ingen binær risiko
    if not binary_risk:
        score += 0.5
        score_details.append({"kryss":"Ingen binær risiko neste 4t","verdi":True})
    else:
        score_details.append({"kryss":"Ingen binær risiko neste 4t","verdi":False})

    max_score = 7.0
    score_pct = round(score / max_score * 100)

    if score >= 6.0:   grade = "A+"; grade_color = "bull"
    elif score >= 4.0: grade = "B";  grade_color = "warn"
    else:              grade = "C";  grade_color = "bear"

    # ── RETNING ──
    long_score  = (1 if lv["above_sma200"] else 0) + (1 if lv["chg5d"]>0 else 0) + (1.5 if cot_color=="bull" else 0)
    short_score = (1 if not lv["above_sma200"] else 0) + (1 if lv["chg5d"]<0 else 0) + (1.5 if cot_color=="bear" else 0)

    if long_score > short_score:   direction="LONG";  dir_color="bull"
    elif short_score > long_score: direction="SHORT"; dir_color="bear"
    else:                          direction="NOYTRAL"; dir_color="neutral"

    # ── ENTRY + SL + T1 + T2 ──
    curr = lv["current"]
    atr  = lv["atr14"]
    spread = lv["spread"]
    sf = vix_spread_factor

    setup_long  = None
    setup_short = None

    # LONG setup – kjøp fra nærmeste støtte
    if supports and direction in ["LONG","NOYTRAL"]:
        entry_lv = supports[0]
        entry = entry_lv["level"]
        sl = round(entry - atr * 0.5 - spread * sf, 6)
        sl_dist = round(entry - sl, 6)
        t1 = round(resistances[0]["level"] if resistances else entry + atr * 1.5, 6)
        t2 = round(resistances[1]["level"] if len(resistances)>1 else entry + atr * 3.0, 6)
        rr_t1 = round((t1 - entry) / sl_dist, 2) if sl_dist > 0 else 0
        rr_t2 = round((t2 - entry) / sl_dist, 2) if sl_dist > 0 else 0
        min_rr = 1.5 if vix_regime == "normal" else 2.0
        valid = rr_t1 >= min_rr

        setup_long = {
            "type":"LONG","entry":entry,"entry_name":entry_lv["name"],
            "sl":sl,"sl_dist":sl_dist,"t1":t1,"t2":t2,
            "rr_t1":rr_t1,"rr_t2":rr_t2,"min_rr":min_rr,"valid":valid,
            "entry_dist_atr": entry_lv["dist_atr"],
            "note": f"Kjøp fra {entry_lv['name']} – SL {round(sl_dist/atr,1)}xATR under inngang"
        }

    # SHORT setup – selg fra nærmeste motstand
    if resistances and direction in ["SHORT","NOYTRAL"]:
        entry_lv = resistances[0]
        entry = entry_lv["level"]
        sl = round(entry + atr * 0.5 + spread * sf, 6)
        sl_dist = round(sl - entry, 6)
        t1 = round(supports[0]["level"] if supports else entry - atr * 1.5, 6)
        t2 = round(supports[1]["level"] if len(supports)>1 else entry - atr * 3.0, 6)
        rr_t1 = round((entry - t1) / sl_dist, 2) if sl_dist > 0 else 0
        rr_t2 = round((entry - t2) / sl_dist, 2) if sl_dist > 0 else 0
        min_rr = 1.5 if vix_regime == "normal" else 2.0
        valid = rr_t1 >= min_rr

        setup_short = {
            "type":"SHORT","entry":entry,"entry_name":entry_lv["name"],
            "sl":sl,"sl_dist":sl_dist,"t1":t1,"t2":t2,
            "rr_t1":rr_t1,"rr_t2":rr_t2,"min_rr":min_rr,"valid":valid,
            "entry_dist_atr": entry_lv["dist_atr"],
            "note": f"Selg fra {entry_lv['name']} – SL {round(sl_dist/atr,1)}xATR over inngang"
        }

    lv.update({
        "direction": direction,
        "dir_color": dir_color,
        "dxy_conf": dxy_conf,
        "pos_size": vix_label,
        "vix_spread_factor": sf,
        "session": session,
        "binary_risk": binary_risk,
        "score": round(score,1),
        "score_pct": score_pct,
        "grade": grade,
        "grade_color": grade_color,
        "score_details": score_details,
        "active_levels": active_levels,
        "setup_long": setup_long,
        "setup_short": setup_short,
    })

    status = "AKTIV" if session["active"] and not binary_risk and grade != "C" else "WATCHLIST"
    print(f"  {name}: {direction} | {grade} ({score}/{max_score}) | {status} | BinRisk:{len(binary_risk)}")

# ── 8. LAGRE ALT ──
macro = {
    "timestamp": now_str, "date": today,
    "dollar_smile": {
        "position":smile_pos,"label":smile_label,"desc":smile_desc,
        "usd_bias":usd_bias,"usd_color":usd_color,
        "inputs":{"vix":vix,"hy_stress":hy_stress,"brent":brent,"tip_trend_5d":tip5d,"dxy_trend_5d":dxy5d}
    },
    "vix_regime": {"value":vix,"regime":vix_regime,"label":vix_label,"color":vix_color},
    "prices": prices,
    "calendar": calendar,
    "cot_count": len(combined),
    "cot_date": combined[0]["date"] if combined else today,
    "trading_levels": levels,
}
save("data/macro/latest.json", macro)
save(f"data/macro/{today}.json", macro)

print(f"\n{'='*50}")
print(f"FERDIG!")
print(f"  {len(combined)} COT-markeder")
print(f"  {len(levels)} trading-instrumenter")
print(f"  {len(calendar)} kalender-hendelser")
print(f"  Dollar-smil: {smile_pos.upper()} | VIX: {vix} ({vix_regime})")
print(f"\nPush: git add data/ && git commit -m 'oppdatering' && git push origin main")
