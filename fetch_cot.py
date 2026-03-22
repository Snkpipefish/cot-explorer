import urllib.request
import zipfile
import csv
import json
import os
from datetime import datetime

URL = "https://www.cftc.gov/files/dea/history/fut_fin_txt_2026.zip"

print("Laster ned COT-data fra CFTC...")
opener = urllib.request.build_opener()
opener.addheaders = [("User-Agent", "Mozilla/5.0")]
urllib.request.install_opener(opener)
urllib.request.urlretrieve(URL, "/tmp/cot.zip")

print("Pakker ut...")
with zipfile.ZipFile("/tmp/cot.zip", "r") as z:
    z.extractall("/tmp/cot")

csv_file = None
for f in os.listdir("/tmp/cot"):
    if f.endswith(".txt") or f.endswith(".csv"):
        csv_file = f"/tmp/cot/{f}"
        break

print(f"Leser {csv_file}...")

def safe_int(val):
    try:
        return int(str(val).strip().replace(",", ""))
    except:
        return 0

results = {}
with open(csv_file, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        name = row.get("Market_and_Exchange_Names", "").strip()
        date = row.get("Report_Date_as_YYYY-MM-DD", "").strip()
        market_short = name.split("-")[0].strip().title()

        lev_long  = safe_int(row.get("Lev_Money_Positions_Long_All", 0))
        lev_short = safe_int(row.get("Lev_Money_Positions_Short_All", 0))
        am_long   = safe_int(row.get("Asset_Mgr_Positions_Long_All", 0))
        am_short  = safe_int(row.get("Asset_Mgr_Positions_Short_All", 0))
        dealer_long  = safe_int(row.get("Dealer_Positions_Long_All", 0))
        dealer_short = safe_int(row.get("Dealer_Positions_Short_All", 0))
        nr_long   = safe_int(row.get("NonRept_Positions_Long_All", 0))
        nr_short  = safe_int(row.get("NonRept_Positions_Short_All", 0))
        oi        = safe_int(row.get("Open_Interest_All", 0))
        chg_oi    = safe_int(row.get("Change_in_Open_Interest_All", 0))
        chg_lev   = safe_int(row.get("Change_in_Lev_Money_Long_All", 0)) - safe_int(row.get("Change_in_Lev_Money_Short_All", 0))

        entry = {
            "date": date,
            "market": market_short,
            "symbol": row.get("CFTC_Contract_Market_Code", "").strip(),
            "open_interest": oi,
            "leveraged_funds": {
                "long": lev_long,
                "short": lev_short,
                "net": lev_long - lev_short
            },
            "asset_managers": {
                "long": am_long,
                "short": am_short,
                "net": am_long - am_short
            },
            "dealers": {
                "long": dealer_long,
                "short": dealer_short,
                "net": dealer_long - dealer_short
            },
            "non_reportable": {
                "long": nr_long,
                "short": nr_short,
                "net": nr_long - nr_short
            },
            "change_oi": chg_oi,
            "change_lev_net": chg_lev
        }

        # Behold siste dato per marked
        if market_short not in results or date > results[market_short]["date"]:
            results[market_short] = entry

output = list(results.values())
output.sort(key=lambda x: x["market"])
date_str = datetime.now().strftime("%Y-%m-%d")

os.makedirs("data", exist_ok=True)
with open(f"data/{date_str}.json", "w") as f:
    json.dump(output, f, indent=2)
with open("data/latest.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"✅ Lagret {len(output)} markeder til data/{date_str}.json og data/latest.json")
