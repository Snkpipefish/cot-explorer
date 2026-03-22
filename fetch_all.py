#!/usr/bin/env python3
"""
Markedspuls – Henter all markedsdata
Kjør daglig (eller via Cowork automatisk)
"""
import urllib.request, zipfile, csv, json, os, sys, shutil
from datetime import datetime, timezone

opener = urllib.request.build_opener()
opener.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")]
urllib.request.install_opener(opener)

def fetch_json(url, timeout=10):
    try:
        res = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(res.read())
    except Exception as e:
        print(f"  Feil {url[:60]}: {e}")
        return None

def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

today = datetime.now().strftime("%Y-%m-%d")
now_utc = datetime.now(timezone.utc).isoformat()

print("=" * 50)
print("Markedspuls – Datanedlasting")
print(f"Tid: {now_utc[:19]}")
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

# ── 2. TRADING LEVELS ──
print("\n[TRADING LEVELS]")
TRADING_INSTRUMENTS = {
    "EUR/USD": {"symbol":"EURUSD=X", "class":"A","cot_key":"Euro Fx",               "pip":0.0001,"label":"Euro/Dollar"},
    "GBP/USD": {"symbol":"GBPUSD=X", "class":"A","cot_key":"British Pound",         "pip":0.0001,"label":"Pund/Dollar"},
    "USD/JPY": {"symbol":"USDJPY=X", "class":"A","cot_key":"Japanese Yen",          "pip":0.01,  "label":"Dollar/Yen"},
    "USD/CHF": {"symbol":"USDCHF=X", "class":"A","cot_key":"Swiss Franc",           "pip":0.0001,"label":"Dollar/Franc"},
    "AUD/USD": {"symbol":"AUDUSD=X", "class":"A","cot_key":"Australian Dollar",     "pip":0.0001,"label":"Aussie/Dollar"},
    "XAU/USD": {"symbol":"GC=F",     "class":"B","cot_key":"Gold",                  "pip":0.1,   "label":"Gull (XAU)"},
    "NAS100":  {"symbol":"^NDX",     "class":"C","cot_key":"Nasdaq",                "pip":1.0,   "label":"Nasdaq 100"},
    "SPX500":  {"symbol":"^GSPC",    "class":"C","cot_key":"S&P 500 Consolidated",  "pip":0.25,  "label":"S&P 500"},
    "WTI":     {"symbol":"CL=F",     "class":"B","cot_key":"Crude Oil, Light Sweet","pip":0.01,  "label":"Råolje (WTI)"},
}

levels = {}
for name, cfg in TRADING_INSTRUMENTS.items():
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

        # Key levels
        pdh  = round(H[-2], 6)
        pdl  = round(L[-2], 6)
        pdc  = round(C[-2], 6)
        pwh  = round(max(H[-6:-1]), 6)
        pwl  = round(min(L[-6:-1]), 6)
        curr = round(C[-1], 6)

        # SMA200
        sma200 = round(sum(C[-200:])/min(len(C),200), 6)
        above_sma200 = curr > sma200

        # ATR14
        trs = []
        for i in range(max(-15,-len(C)), -1):
            tr = max(H[i]-L[i], abs(H[i]-C[i-1]), abs(L[i]-C[i-1]))
            trs.append(tr)
        atr14 = round(sum(trs)/len(trs), 6) if trs else 0

        # 5d og 20d trend
        chg5d  = round((curr/C[-6]-1)*100, 2) if len(C)>=6  else 0
        chg20d = round((curr/C[-21]-1)*100, 2) if len(C)>=21 else 0

        # Closest levels
        all_levels = [
            {"level":pwh, "name":"PWH", "type":"resistance"},
            {"level":pdh, "name":"PDH", "type":"resistance"},
            {"level":pdc, "name":"PDC", "type":"pivot"},
            {"level":sma200,"name":"SMA200","type":"trend"},
            {"level":pdl, "name":"PDL", "type":"support"},
            {"level":pwl, "name":"PWL", "type":"support"},
        ]

        resistances = sorted([l for l in all_levels if l["level"] > curr], key=lambda x: x["level"])
        supports    = sorted([l for l in all_levels if l["level"] < curr], key=lambda x: x["level"], reverse=True)

        # Mark levels within 1x ATR
        for lv in all_levels:
            lv["dist"] = round(abs(lv["level"] - curr), 6)
            lv["dist_atr"] = round(lv["dist"] / atr14, 2) if atr14 > 0 else 99
            lv["active"] = lv["dist_atr"] <= 1.0

        levels[name] = {
            "name": name,
            "label": cfg["label"],
            "class": cfg["class"],
            "cot_key": cfg["cot_key"],
            "pip": cfg["pip"],
            "current": curr,
            "pdh": pdh, "pdl": pdl, "pdc": pdc,
            "pwh": pwh, "pwl": pwl,
            "sma200": sma200,
            "above_sma200": above_sma200,
            "atr14": atr14,
            "chg5d": chg5d,
            "chg20d": chg20d,
            "resistances": resistances[:3],
            "supports": supports[:3],
            "all_levels": all_levels,
        }
        print(f"  {name}: {curr} | PDH={pdh} PDL={pdl} ATR={atr14}")
    except Exception as e:
        print(f"  {name}: feil – {e}")

# ── 3. DOLLAR-SMIL ──
print("\n[DOLLAR-SMIL]")
vix = prices.get("VIX",{}).get("price",0)
hyg_5d = prices.get("HYG",{}).get("chg5d",0)
brent = prices.get("Brent",{}).get("price",0)
tip_5d = prices.get("TIP",{}).get("chg5d",0)
dxy_5d = prices.get("DXY",{}).get("chg5d",0)
hy_stress = hyg_5d < -1.0

if vix > 25 or hy_stress:
    smile_pos="venstre"; smile_label="Krise / Risk-off"
    smile_desc="USD styrkes. Kjøp USD, CHF, JPY. Unngå NOK, AUD, NZD."
    usd_bias="KJØP"; usd_color="bull"
elif brent > 85 or tip_5d > 0.5:
    smile_pos="høyre"; smile_label="Vekst / Inflasjon"
    smile_desc="USD styrkes. Fed on-hold. Inflasjonspremium i markedet."
    usd_bias="KJØP"; usd_color="bull"
else:
    smile_pos="midten"; smile_label="Goldilocks / Soft landing"
    smile_desc="USD svekkes. Fed kutter. Risikoappetitt normal."
    usd_bias="SELG"; usd_color="bear"

vix_regime = "normal" if vix<20 else "stress" if vix<30 else "krise"
vix_size   = "Full størrelse" if vix<20 else "Halv størrelse" if vix<30 else "Kvart størrelse"
vix_color  = "bull" if vix<20 else "warn" if vix<30 else "bear"

print(f"  Dollar-smil: {smile_pos.upper()} – {smile_label}")
print(f"  VIX: {vix} → {vix_regime} ({vix_size})")

# ── 4. KALENDER ──
print("\n[KALENDER]")
calendar = []
try:
    data = fetch_json("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
    if data:
        for e in data:
            if e.get("impact") in ["High","Medium"]:
                calendar.append({"date":e.get("date",""),"title":e.get("title",""),
                    "country":e.get("country",""),"impact":e.get("impact",""),
                    "forecast":e.get("forecast",""),"previous":e.get("previous","")})
        print(f"  {len(calendar)} hendelser")
except Exception as e:
    print(f"  Kalender feil: {e}")

# ── 5. COT-DATA ──
YEAR = datetime.now().year
BASE = "https://www.cftc.gov/files/dea/history"
REPORTS = [
    {"id":"tff",           "url":f"{BASE}/fut_fin_txt_{YEAR}.zip"},
    {"id":"legacy",        "url":f"{BASE}/com_disagg_txt_{YEAR}.zip"},
    {"id":"disaggregated", "url":f"{BASE}/fut_disagg_txt_{YEAR}.zip"},
    {"id":"supplemental",  "url":f"{BASE}/dea_cit_txt_{YEAR}.zip"},
]
CATEGORIES = {
    "aksjer":["s&p","nasdaq","russell","nikkei","msci","vix","topix","dow"],
    "valuta":["euro fx","japanese yen","british pound","swiss franc","canadian dollar","australian dollar","nz dollar","mexican peso","so african rand","usd index","brazilian real"],
    "renter":["ust","sofr","eurodollar","treasury","t-note","t-bond","swap","eris","federal fund"],
    "råvarer":["crude oil","natural gas","gasoline","heating oil","gold","silver","copper","platinum","palladium","lumber","wti","brent","rbob"],
    "krypto":["bitcoin","ether","solana","xrp","cardano","polkadot","litecoin","nano","zcash","sui","doge"],
    "landbruk":["corn","wheat","soybean","coffee","sugar","cocoa","cotton","cattle","hogs","lean","live","feeder","oats","rice","milk","butter","orange juice","canola"],
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
    "Nz Dollar":{"no":"NZD/USD","info":"Newzealandsk dollar mot USD."},
    "So African Rand":{"no":"USD/ZAR","info":"Dollar mot rand."},
    "Usd Index":{"no":"DXY – Dollarindeks","info":"Styrken til USD mot 6 valutaer."},
    "Ust 2Y Note":{"no":"US 2-årig rente","info":"Sensitiv for Fed-forventninger."},
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
    "Wheat-Srw":{"no":"Hvete","info":"Brød og pasta."},
    "Coffee C":{"no":"Kaffe","info":"Arabica-kaffe."},
    "Cotton No. 2":{"no":"Bomull","info":"Tekstilfiber."},
}

def safe_int(v):
    try: return int(str(v).strip().replace(",","").split(".")[0])
    except: return 0

def get_category(n):
    nl=n.lower()
    for cat,kws in CATEGORIES.items():
        for kw in kws:
            if kw in nl: return cat
    return "annet"

def download_extract(url, tmp):
    zp=os.path.join(tmp,"cot.zip")
    try:
        urllib.request.urlretrieve(url,zp)
        with zipfile.ZipFile(zp,"r") as z: z.extractall(tmp)
        for f in os.listdir(tmp):
            if f.endswith(".txt"): return os.path.join(tmp,f)
    except Exception as e: print(f"  Feil: {e}")
    return None

def parse_cot(csv_file, rid):
    results={}
    try:
        with open(csv_file,newline="",encoding="utf-8") as f:
            reader=csv.DictReader(f)
            for row in reader:
                name=row.get("Market_and_Exchange_Names","").strip()
                date=row.get("Report_Date_as_YYYY-MM-DD","").strip()
                sym=row.get("CFTC_Contract_Market_Code","").strip()
                mkt=name.split("-")[0].strip().title()
                oi=safe_int(row.get("Open_Interest_All",0))
                chg=safe_int(row.get("Change_in_Open_Interest_All",0))
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
                        "smahandlere":{"long":nl,"short":ns,"net":nl-ns,"label":"Småhandlere"}}
                elif rid=="legacy":
                    sl=safe_int(row.get("NonComm_Positions_Long_All",0)); ss=safe_int(row.get("NonComm_Positions_Short_All",0))
                    cl=safe_int(row.get("Comm_Positions_Long_All",0)); cs_=safe_int(row.get("Comm_Positions_Short_All",0))
                    nl=safe_int(row.get("NonRept_Positions_Long_All",0)); ns=safe_int(row.get("NonRept_Positions_Short_All",0))
                    cs=safe_int(row.get("Change_in_NonComm_Long_All",0))-safe_int(row.get("Change_in_NonComm_Short_All",0))
                    entry={"date":date,"market":mkt,"symbol":sym,"report":"legacy","open_interest":oi,"change_oi":chg,"change_spec_net":cs,
                        "spekulanter":{"long":sl,"short":ss,"net":sl-ss,"label":"Store Spekulanter"},
                        "kommersielle":{"long":cl,"short":cs_,"net":cl-cs_,"label":"Produsenter/Hedgers"},
                        "smahandlere":{"long":nl,"short":ns,"net":nl-ns,"label":"Småhandlere"}}
                elif rid=="disaggregated":
                    sl=safe_int(row.get("M_Money_Positions_Long_All",0)); ss=safe_int(row.get("M_Money_Positions_Short_All",0))
                    pl=safe_int(row.get("Prod_Merc_Positions_Long_All",0)); ps=safe_int(row.get("Prod_Merc_Positions_Short_All",0))
                    nl=safe_int(row.get("NonRept_Positions_Long_All",0)); ns=safe_int(row.get("NonRept_Positions_Short_All",0))
                    cs=safe_int(row.get("Change_in_M_Money_Long_All",0))-safe_int(row.get("Change_in_M_Money_Short_All",0))
                    entry={"date":date,"market":mkt,"symbol":sym,"report":"disaggregated","open_interest":oi,"change_oi":chg,"change_spec_net":cs,
                        "spekulanter":{"long":sl,"short":ss,"net":sl-ss,"label":"Managed Money"},
                        "produsenter":{"long":pl,"short":ps,"net":pl-ps,"label":"Produsenter"},
                        "smahandlere":{"long":nl,"short":ns,"net":nl-ns,"label":"Småhandlere"}}
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
                        "smahandlere":{"long":nl,"short":ns,"net":nl-ns,"label":"Småhandlere"}}
                else: continue
                entry["kategori"]=get_category(name)
                info=MARKET_NO.get(mkt,{})
                entry["navn_no"]=info.get("no",mkt)
                entry["forklaring"]=info.get("info","")
                if mkt not in results or date>results[mkt]["date"]: results[mkt]=entry
    except Exception as e: print(f"  Parse-feil: {e}")
    return list(results.values())

print("\n[COT-DATA]")
all_cot=[]
for report in REPORTS:
    rid=report["id"]; print(f"  Laster {rid}...")
    tmp=f"/tmp/cot_{rid}"; os.makedirs(tmp,exist_ok=True)
    csv_file=download_extract(report["url"],tmp)
    if csv_file:
        data=parse_cot(csv_file,rid)
        if data:
            save(f"data/{rid}/latest.json",data)
            save(f"data/{rid}/{today}.json",data)
            all_cot.extend(data); print(f"  {len(data)} markeder")
    shutil.rmtree(tmp,ignore_errors=True)

seen=set(); combined=[]
for d in all_cot:
    key=d["symbol"]+d["report"]
    if key not in seen: seen.add(key); combined.append(d)
combined.sort(key=lambda x:(x["kategori"],x["navn_no"]))
save("data/combined/latest.json",combined)
save(f"data/combined/{today}.json",combined)

# ── 6. KNYTT COT TIL TRADING LEVELS ──
print("\n[TRADING IDEER]")
cot_by_market = {}
for d in combined:
    cot_by_market[d["market"]] = d
    cot_by_market[d.get("navn_no","")] = d

for name, lv in levels.items():
    cot_key = lv["cot_key"]
    cot = None
    for key in [cot_key, cot_key.title(), name]:
        if key in cot_by_market:
            cot = cot_by_market[key]; break
    if not cot:
        for d in combined:
            if cot_key.lower() in d["market"].lower() or cot_key.lower() in d.get("navn_no","").lower():
                cot = d; break

    if cot:
        spec = cot.get("spekulanter",{})
        net = spec.get("net",0)
        oi  = cot.get("open_interest",1)
        chg = cot.get("change_spec_net",0)
        pct = net/oi if oi else 0

        if pct > 0.15:   cot_bias="STERKT BULLISH"; cot_color="bull"
        elif pct > 0.04: cot_bias="SVAKT BULLISH";  cot_color="bull"
        elif pct < -0.15:cot_bias="STERKT BEARISH"; cot_color="bear"
        elif pct < -0.04:cot_bias="SVAKT BEARISH";  cot_color="bear"
        else:            cot_bias="NØYTRAL";         cot_color="neutral"

        lv["cot"] = {
            "bias": cot_bias, "color": cot_color,
            "net": net, "chg": chg,
            "pct": round(pct*100,1),
            "date": cot.get("date",""),
            "report": cot.get("report","")
        }
    else:
        lv["cot"] = {"bias":"UKJENT","color":"neutral","net":0,"chg":0,"pct":0,"date":"","report":""}

    # Kombinert bias
    curr = lv["current"]
    sma = lv["sma200"]
    chg5 = lv["chg5d"]
    cot_c = lv["cot"]["color"]
    sma_ok = curr > sma  # price above SMA200

    # DXY konfluens
    is_usd_quote = name in ["EUR/USD","GBP/USD","AUD/USD","NZD/USD","XAU/USD"]
    dxy_up = dxy_5d > 0
    dxy_conf = "motvind" if (is_usd_quote and dxy_up) or (not is_usd_quote and not dxy_up) else "medvind"

    # VIX posisjonsstørrelse
    pos_size = vix_size

    scores = {"bull":1,"bear":-1,"neutral":0}
    score = scores.get(cot_c,0)
    if sma_ok: score += 0.5
    else: score -= 0.5

    if score > 0.5:   combined_bias="LONG"; bias_color="bull"
    elif score < -0.5:combined_bias="SHORT"; bias_color="bear"
    else:             combined_bias="NØYTRAL"; bias_color="neutral"

    lv["combined_bias"] = combined_bias
    lv["bias_color"] = bias_color
    lv["dxy_conf"] = dxy_conf
    lv["pos_size"] = pos_size
    lv["sma200_pos"] = "over" if sma_ok else "under"

    # Aktive nivåer (innen 1x ATR)
    active_levels = [l for l in lv["all_levels"] if l["dist_atr"] <= 1.0]
    lv["active_levels"] = active_levels

    print(f"  {name}: {combined_bias} | COT:{cot_bias} | SMA200:{lv['sma200_pos']} | DXY:{dxy_conf}")

# ── 7. LAGRE ALT ──
macro = {
    "timestamp": now_utc, "date": today,
    "dollar_smile": {
        "position":smile_pos,"label":smile_label,"desc":smile_desc,
        "usd_bias":usd_bias,"usd_color":usd_color,
        "inputs":{"vix":vix,"hy_stress":hy_stress,"brent":brent,"tip_trend_5d":tip_5d,"dxy_trend_5d":dxy_5d}
    },
    "vix_regime":{"value":vix,"regime":vix_regime,"label":vix_size,"color":vix_color},
    "prices": prices,
    "calendar": calendar,
    "cot_count": len(combined),
    "cot_date": combined[0]["date"] if combined else today,
    "trading_levels": levels,
}
save("data/macro/latest.json", macro)
save(f"data/macro/{today}.json", macro)

print(f"\n✅ FERDIG!")
print(f"   {len(combined)} COT-markeder")
print(f"   {len(levels)} trading-instrumenter med nivåer")
print(f"   {len(calendar)} kalender-hendelser")
print(f"   Dollar-smil: {smile_pos.upper()} | VIX: {vix} ({vix_regime})")
print("\nPush: git add data/ && git commit -m 'daglig oppdatering' && git push origin main")
