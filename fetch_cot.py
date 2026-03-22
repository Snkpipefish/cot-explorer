#!/usr/bin/env python3
import urllib.request, zipfile, csv, json, os, sys, shutil
from datetime import datetime

opener = urllib.request.build_opener()
opener.addheaders = [("User-Agent", "Mozilla/5.0")]
urllib.request.install_opener(opener)

YEAR = datetime.now().year
BASE = "https://www.cftc.gov/files/dea/history"

REPORTS = [
    {"id":"tff",           "url":f"{BASE}/fut_fin_txt_{YEAR}.zip",   "hist_from":2009, "hist_pat":f"{BASE}/fut_fin_txt_YYYY.zip"},
    {"id":"legacy",        "url":f"{BASE}/com_disagg_txt_{YEAR}.zip",        "hist_from":2010, "hist_pat":f"{BASE}/com_disagg_txt_YYYY.zip"},
    {"id":"disaggregated", "url":f"{BASE}/fut_disagg_txt_{YEAR}.zip", "hist_from":2009, "hist_pat":f"{BASE}/fut_disagg_txt_YYYY.zip"},
    {"id":"supplemental",  "url":f"{BASE}/dea_cit_txt_{YEAR}.zip",   "hist_from":2006, "hist_pat":f"{BASE}/dea_cit_txt_YYYY.zip"},
]

CATEGORIES = {
    "aksjer":     ["s&p","nasdaq","russell","nikkei","msci","vix","topix","dow"],
    "valuta":     ["euro fx","japanese yen","british pound","swiss franc","canadian dollar","australian dollar","nz dollar","mexican peso","so african rand","usd index","brazilian real"],
    "renter":     ["ust","sofr","eurodollar","treasury","t-note","t-bond","swap","eris","federal fund"],
    "råvarer":    ["crude oil","natural gas","gasoline","heating oil","gold","silver","copper","platinum","palladium","lumber","wti","brent","rbob"],
    "krypto":     ["bitcoin","ether","solana","xrp","cardano","polkadot","litecoin","nano","zcash","sui","doge"],
    "landbruk":   ["corn","wheat","soybean","coffee","sugar","cocoa","cotton","cattle","hogs","lean","live","feeder","oats","rice","milk","butter","orange juice","canola"],
    "volatilitet":["vix"],
}

MARKET_NO = {
    "S&P 500 Consolidated":         {"no":"S&P 500",              "info":"De 500 største selskapene i USA."},
    "Nasdaq":                        {"no":"Nasdaq 100",           "info":"Teknologiindeks. Apple, Microsoft, Nvidia m.fl."},
    "Nasdaq Mini":                   {"no":"Nasdaq Mini",          "info":"Mindre Nasdaq-kontrakt."},
    "Russell E":                     {"no":"Russell 2000",         "info":"2000 mindre amerikanske selskaper."},
    "Msci Eafe":                     {"no":"MSCI Europa/Asia",     "info":"Aksjer utenfor USA: Europa, Japan, Australia."},
    "Msci Em Index":                 {"no":"MSCI Fremvoksende",    "info":"Kina, India, Brasil og andre vekstmarkeder."},
    "Nikkei Stock Average":          {"no":"Nikkei (Japan)",       "info":"225 største selskaper på Tokyo-børsen."},
    "Vix Futures":                   {"no":"VIX – Fryktindeks",    "info":"Høy verdi = mye usikkerhet i markedet."},
    "Euro Fx":                       {"no":"Euro (EUR/USD)",       "info":"Verdens mest handlede valutapar."},
    "Japanese Yen":                  {"no":"Japansk Yen",          "info":"Trygg-havn-valuta i urolige tider."},
    "British Pound":                 {"no":"Britisk Pund",         "info":"Påvirkes av Bank of England."},
    "Swiss Franc":                   {"no":"Sveitsisk Franc",      "info":"En av de sikreste valutaene i verden."},
    "Canadian Dollar":               {"no":"Kanadisk Dollar",      "info":"Tett knyttet til oljeprisen."},
    "Australian Dollar":             {"no":"Australsk Dollar",     "info":"Råvarevaluta – følger kobber og jernmalm."},
    "Nz Dollar":                     {"no":"New Zealand Dollar",   "info":"Barometer for global risikoappetitt."},
    "So African Rand":               {"no":"Sørafrikansk Rand",    "info":"Volatil valuta fra fremvoksende marked."},
    "Usd Index":                     {"no":"Dollarindeks (DXY)",   "info":"Styrken til USD mot 6 valutaer."},
    "Ust 2Y Note":                   {"no":"USA 2-årig rente",     "info":"Sensitiv for hva sentralbanken (Fed) gjør."},
    "Ust 5Y Note":                   {"no":"USA 5-årig rente",     "info":"Mellomlang amerikansk statsrente."},
    "Ust 10Y Note":                  {"no":"USA 10-årig rente",    "info":"Viktigste globale rente. Påvirker boliglån verden over."},
    "Ust Bond":                      {"no":"USA 30-årig rente",    "info":"Langsiktig rente for pensjonsfond."},
    "Sofr":                          {"no":"SOFR (dagslånsrente)", "info":"Hva banker betaler for korte dollarlån."},
    "Bitcoin":                       {"no":"Bitcoin (BTC)",        "info":"Verdens største kryptovaluta."},
    "Nano Bitcoin":                  {"no":"Bitcoin Mini",         "info":"Mindre Bitcoin-kontrakt (1/100 BTC)."},
    "Nano Bitcoin Perp Style":       {"no":"Bitcoin Mini Perp",    "info":"Bitcoin uten utløpsdato."},
    "Nano Ether":                    {"no":"Ethereum Mini",        "info":"Ethereum – plattform for smarte kontrakter."},
    "Nano Ether Perp Style":         {"no":"Ethereum Mini Perp",   "info":"Ethereum uten utløpsdato."},
    "Nano Solana":                   {"no":"Solana Mini",          "info":"Solana – rask og billig blokkjede."},
    "Nano Solana Perp Style":        {"no":"Solana Mini Perp",     "info":"Solana uten utløpsdato."},
    "Nano Xrp":                      {"no":"XRP Mini",             "info":"XRP – brukes til internasjonal betaling."},
    "Sol":                           {"no":"Solana (SOL)",         "info":"Solana kryptovaluta."},
    "Xrp":                           {"no":"XRP",                  "info":"XRP kryptovaluta."},
    "Crude Oil, Light Sweet":        {"no":"Råolje (WTI)",         "info":"Amerikansk råolje. Global prisreferanse."},
    "Natural Gas":                   {"no":"Naturgass",            "info":"Energiråvare for strøm og oppvarming."},
    "Gold":                          {"no":"Gull",                 "info":"Trygg havn. Handles globalt som verdilager."},
    "Silver":                        {"no":"Sølv",                 "info":"Brukes som investering og i industri."},
    "Copper-Grade #1":               {"no":"Kobber",               "info":"Industrimetall. Høy etterspørsel = sterk økonomi."},
    "Corn":                          {"no":"Mais",                 "info":"Viktigste kornavling i USA."},
    "Soybeans":                      {"no":"Soyabønner",           "info":"Verdens nest viktigste kornavling."},
    "Wheat-Srw":                     {"no":"Hvete",                "info":"Brukes til brød og pasta."},
    "Coffee C":                      {"no":"Kaffe (Arabica)",      "info":"Arabica-kaffe handles på New York-børsen."},
    "Sugar No. 11":                  {"no":"Sukker",               "info":"Råsukker. Viktig for mat og drivstoff."},
    "Cotton No. 2":                  {"no":"Bomull",               "info":"Viktigste naturlige tekstilfiber."},
    "Lean Hogs":                     {"no":"Svinekjøtt",           "info":"Futures på mager svinekjøtt."},
    "Live Cattle":                   {"no":"Storfe",               "info":"Futures på levende storfe klar for slakt."},
}

def safe_int(val):
    try: return int(str(val).strip().replace(",","").split(".")[0])
    except: return 0

def get_category(name):
    nl = name.lower()
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in nl:
                return cat
    return "annet"

def download_and_extract(url, tmp_dir):
    zip_path = os.path.join(tmp_dir, "cot.zip")
    try:
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp_dir)
        for f in os.listdir(tmp_dir):
            if f.endswith(".txt") and f != "cot.zip":
                return os.path.join(tmp_dir, f)
    except Exception as e:
        print(f"  Feil: {e}")
    return None

def parse_file(csv_file, report_id, keep_all=False):
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

                if report_id == "tff":
                    sl=safe_int(row.get("Lev_Money_Positions_Long_All",0))
                    ss=safe_int(row.get("Lev_Money_Positions_Short_All",0))
                    il=safe_int(row.get("Asset_Mgr_Positions_Long_All",0))
                    i_=safe_int(row.get("Asset_Mgr_Positions_Short_All",0))
                    dl=safe_int(row.get("Dealer_Positions_Long_All",0))
                    ds=safe_int(row.get("Dealer_Positions_Short_All",0))
                    nl=safe_int(row.get("NonRept_Positions_Long_All",0))
                    ns=safe_int(row.get("NonRept_Positions_Short_All",0))
                    cs=safe_int(row.get("Change_in_Lev_Money_Long_All",0))-safe_int(row.get("Change_in_Lev_Money_Short_All",0))
                    entry={"date":date,"market":mkt,"symbol":sym,"report":"tff","open_interest":oi,"change_oi":chg,"change_spec_net":cs,
                        "spekulanter":{"long":sl,"short":ss,"net":sl-ss,"label":"Hedge Funds"},
                        "institusjoner":{"long":il,"short":i_,"net":il-i_,"label":"Pensjonsfond"},
                        "meglere":{"long":dl,"short":ds,"net":dl-ds,"label":"Banker/Meglere"},
                        "smahandlere":{"long":nl,"short":ns,"net":nl-ns,"label":"Småhandlere"}}
                elif report_id == "legacy":
                    sl=safe_int(row.get("NonComm_Positions_Long_All",0))
                    ss=safe_int(row.get("NonComm_Positions_Short_All",0))
                    cl=safe_int(row.get("Comm_Positions_Long_All",0))
                    cs_=safe_int(row.get("Comm_Positions_Short_All",0))
                    nl=safe_int(row.get("NonRept_Positions_Long_All",0))
                    ns=safe_int(row.get("NonRept_Positions_Short_All",0))
                    cs=safe_int(row.get("Change_in_NonComm_Long_All",0))-safe_int(row.get("Change_in_NonComm_Short_All",0))
                    entry={"date":date,"market":mkt,"symbol":sym,"report":"legacy","open_interest":oi,"change_oi":chg,"change_spec_net":cs,
                        "spekulanter":{"long":sl,"short":ss,"net":sl-ss,"label":"Store Spekulanter"},
                        "kommersielle":{"long":cl,"short":cs_,"net":cl-cs_,"label":"Produsenter/Hedgers"},
                        "smahandlere":{"long":nl,"short":ns,"net":nl-ns,"label":"Småhandlere"}}
                elif report_id == "disaggregated":
                    sl=safe_int(row.get("M_Money_Positions_Long_All",0))
                    ss=safe_int(row.get("M_Money_Positions_Short_All",0))
                    pl=safe_int(row.get("Prod_Merc_Positions_Long_All",0))
                    ps=safe_int(row.get("Prod_Merc_Positions_Short_All",0))
                    nl=safe_int(row.get("NonRept_Positions_Long_All",0))
                    ns=safe_int(row.get("NonRept_Positions_Short_All",0))
                    cs=safe_int(row.get("Change_in_M_Money_Long_All",0))-safe_int(row.get("Change_in_M_Money_Short_All",0))
                    entry={"date":date,"market":mkt,"symbol":sym,"report":"disaggregated","open_interest":oi,"change_oi":chg,"change_spec_net":cs,
                        "spekulanter":{"long":sl,"short":ss,"net":sl-ss,"label":"Managed Money"},
                        "produsenter":{"long":pl,"short":ps,"net":pl-ps,"label":"Produsenter"},
                        "smahandlere":{"long":nl,"short":ns,"net":nl-ns,"label":"Småhandlere"}}
                elif report_id == "supplemental":
                    sl=safe_int(row.get("NonComm_Positions_Long_All",0))
                    ss=safe_int(row.get("NonComm_Positions_Short_All",0))
                    cl=safe_int(row.get("Comm_Positions_Long_All",0))
                    cs_=safe_int(row.get("Comm_Positions_Short_All",0))
                    il=safe_int(row.get("Index_Positions_Long_All",0))
                    i_=safe_int(row.get("Index_Positions_Short_All",0))
                    nl=safe_int(row.get("NonRept_Positions_Long_All",0))
                    ns=safe_int(row.get("NonRept_Positions_Short_All",0))
                    cs=safe_int(row.get("Change_in_NonComm_Long_All",0))-safe_int(row.get("Change_in_NonComm_Short_All",0))
                    entry={"date":date,"market":mkt,"symbol":sym,"report":"supplemental","open_interest":oi,"change_oi":chg,"change_spec_net":cs,
                        "spekulanter":{"long":sl,"short":ss,"net":sl-ss,"label":"Store Spekulanter"},
                        "kommersielle":{"long":cl,"short":cs_,"net":cl-cs_,"label":"Produsenter/Hedgers"},
                        "indeksfond":{"long":il,"short":i_,"net":il-i_,"label":"Indeksfond"},
                        "smahandlere":{"long":nl,"short":ns,"net":nl-ns,"label":"Småhandlere"}}
                else:
                    continue

                entry["kategori"] = get_category(name)
                info = MARKET_NO.get(mkt, {})
                entry["navn_no"] = info.get("no", mkt)
                entry["forklaring"] = info.get("info", "")
                if keep_all:
                    if sym not in results:
                        results[sym] = []
                    results[sym].append(entry)
                else:
                    if mkt not in results or date > results[mkt]["date"]:
                        results[mkt] = entry
    except Exception as e:
        print(f"  Parse-feil: {e}")
    if keep_all:
        out = []
        for entries in results.values():
            out.extend(entries)
        return out
    return list(results.values())

def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def process_report(report, year=None, keep_all=False):
    url = report["url"] if year is None else report["hist_pat"].replace("YYYY", str(year))
    rid = report["id"]
    yr  = year or YEAR
    print(f"  Laster {rid} {yr}...")
    tmp = f"/tmp/cot_{rid}_{yr}"
    os.makedirs(tmp, exist_ok=True)
    csv_file = download_and_extract(url, tmp)
    if not csv_file:
        return []
    data = parse_file(csv_file, rid, keep_all=keep_all)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"  {len(data)} markeder")
    return data

do_history = "--history" in sys.argv
today = datetime.now().strftime("%Y-%m-%d")
print("COT Explorer – Datanedlasting")
print("=" * 40)

all_current = []
for report in REPORTS:
    print(f"\n[{report['id'].upper()}]")
    data = process_report(report)
    if data:
        save(f"data/{report['id']}/latest.json", data)
        save(f"data/{report['id']}/{today}.json", data)
        all_current.extend(data)

seen = set()
combined = []
for d in all_current:
    key = d["symbol"] + d["report"]
    if key not in seen:
        seen.add(key)
        combined.append(d)
combined.sort(key=lambda x: (x["kategori"], x["navn_no"]))
save("data/combined/latest.json", combined)
save(f"data/combined/{today}.json", combined)
print(f"\nKombinert: {len(combined)} markeder -> data/combined/latest.json")

if do_history:
    print("\n[HISTORISKE DATA]")
    for report in REPORTS:
        for yr in range(report["hist_from"], YEAR):
            data = process_report(report, yr, keep_all=True)
            if data:
                save(f"data/history/{report['id']}/{yr}.json", data)
    print("Historiske data lagret i data/history/")

print("\nFerdig! Kjor:")
print("git add data/ && git commit -m 'oppdater COT-data' && git push origin main")
