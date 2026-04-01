#!/usr/bin/env python3
"""
fetch_euronext_cot.py — Henter Euronext COT-data for landbruksråvarer (MiFID II)

Euronext publiserer hver onsdag ettermiddag, posisjoner per foregående fredag.
Dekker: Milling Wheat (EBM), Rapeseed (EBR), Corn/Maize (EMA)

Rapporten (Excel, "agri-commodities") viser per kategori:
  antall personer, long/short, endring, % av open interest

MiFID II-kategorier (brukt av Euronext):
  - Investment Funds          → tilsvarer CFTC Managed Money (spekulanter)
  - Investment Firms/Banks    → Swap Dealers / mellommenn
  - Commercial Undertakings   → Producers/Commercials (hedgere)
  - Other Financial           → Other Reportables

Output: data/euronext_cot/latest.json  — samme struktur som fetch_agri.py forventer
        data/euronext_cot/history.json — rullende 26-ukers historikk
"""

import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
import openpyxl

BASE    = Path(__file__).parent
OUT_DIR = BASE / "data" / "euronext_cot"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT  = OUT_DIR / "latest.json"
HIST = OUT_DIR / "history.json"

# Euronext-markeder → intern crop-nøkkel
# Søker case-insensitivt i markedsnavn/produktnavn
EURONEXT_MARKETS = {
    # Milling Wheat
    "milling wheat":   "wheat",
    "wheat milling":   "wheat",
    "ebm":             "wheat",
    "farine":          "wheat",
    "blé":             "wheat",
    "ble":             "wheat",
    # Rapeseed / Colza
    "rapeseed":        "canola",
    "colza":           "canola",
    "ebr":             "canola",
    "canola":          "canola",
    # Corn / Maize
    "corn":            "corn",
    "maize":           "corn",
    "ema":             "corn",
    "mais":            "corn",
    # Sunflower (bonus — vises hvis det finnes)
    "sunflower":       "sunflower",
    "tournesol":       "sunflower",
}

# MiFID II-kategorier → type (viktigst: investment_funds = spekulanter)
SPEC_KEYWORDS    = ["investment fund", "fonds d'investissement", "managed", "fund"]
COMMERCIAL_KEYWORDS = ["commercial undertaking", "entreprise commerciale", "commercial"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://live.euronext.com/",
}
HEADERS_XLSX = {**HEADERS,
    "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
              "application/vnd.ms-excel,*/*",
}

from datetime import date as _date
import itertools

def _candidate_urls():
    """Generer kandidat-URLer basert på dato (siste 8 uker)."""
    today = _date.today()
    urls = []
    # live.euronext.com — prøv siste 8 uker med dato-prefix
    for weeks_ago in range(0, 8):
        from datetime import timedelta
        d = today - timedelta(weeks=weeks_ago)
        month_str = d.strftime("%Y-%m")
        urls.append(
            f"https://live.euronext.com/sites/default/files/{month_str}/agri-commodities-cot.xlsx"
        )
    # Fallback uten dato-prefix
    urls += [
        "https://live.euronext.com/sites/default/files/agri-commodities-cot.xlsx",
        "https://live.euronext.com/sites/default/files/agri-cot.xlsx",
    ]
    return urls

# Euronext COT rapport-sider (skrapes for Excel-lenke)
EURONEXT_PAGES = [
    "https://live.euronext.com/en/products/commodities/commitments_of_traders",
    "https://www.euronext.com/en/markets/derivatives/commitment-of-traders",
]


# ── Nedlasting ───────────────────────────────────────────────────────────────

def find_excel_url():
    """Skrap Euronext COT-side for Excel-lenke med 'agri' i filnavnet."""
    for page_url in EURONEXT_PAGES:
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=20)
            urls = re.findall(r'href=["\']([^"\']*agri[^"\']*\.xlsx?)["\']', r.text, re.I)
            if not urls:
                urls = re.findall(r'href=["\']([^"\']*\.xlsx?)["\']', r.text, re.I)
            for u in urls:
                if not u.startswith("http"):
                    base = "https://live.euronext.com" if "live.euronext" in page_url else "https://www.euronext.com"
                    u = base + u
                return u
        except Exception as e:
            print(f"  Kunne ikke hente side {page_url}: {e}")
    return None


def download_excel():
    """Last ned Euronext agri COT Excel. Returnerer bytes eller None."""
    scraped = find_excel_url()
    candidates = ([scraped] if scraped else []) + _candidate_urls()

    for url in candidates:
        if not url:
            continue
        try:
            print(f"  Prøver: {url}")
            r = requests.get(url, headers=HEADERS_XLSX, timeout=30, allow_redirects=True)
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "")
            if len(r.content) < 500:
                continue
            if "html" in ctype.lower() and b"<!DOCTYPE" in r.content[:200]:
                continue
            print(f"    OK — {len(r.content)//1024} KB")
            return r.content
        except Exception as e:
            print(f"    FEIL: {e}")
    return None


# ── Excel-parsing ────────────────────────────────────────────────────────────

def normalize(s):
    if s is None:
        return ""
    return str(s).strip().lower()


def safe_int(v):
    if v is None:
        return 0
    try:
        return int(float(str(v).replace(",", "").replace(" ", "").strip()))
    except Exception:
        return 0


def match_market(cell_val):
    """Returner crop_key hvis celleverdien matcher et kjent Euronext-marked."""
    s = normalize(cell_val)
    for keyword, crop in EURONEXT_MARKETS.items():
        if keyword in s:
            return crop
    return None


def is_speculator_row(cell_val):
    s = normalize(cell_val)
    return any(k in s for k in SPEC_KEYWORDS)


def parse_euronext_excel(data):
    """
    Parser Euronext agri COT Excel.

    Euronext-formater vi støtter:
    Format A — Bred tabell: én rad per marked, kolonner per kategori×long/short
    Format B — Lang tabell: én rad per marked×kategori
    """
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    results = {}

    for sheet_name in wb.sheetnames:
        ws    = wb[sheet_name]
        rows  = list(ws.iter_rows(values_only=True))
        if len(rows) < 3:
            continue

        # Søk etter header-rad som inneholder "long" og "short"
        header_idx  = None
        header_row  = None
        for i, row in enumerate(rows[:30]):
            s = " ".join(normalize(c) for c in row if c is not None)
            if "long" in s and "short" in s:
                header_row = [normalize(c) for c in row]
                header_idx = i
                break

        if header_row:
            r = _parse_format_a(rows, header_row, header_idx)
            if r:
                results.update(r)
                continue

        # Fallback: Format B (lang tabell)
        r = _parse_format_b(rows)
        if r:
            results.update(r)

    return results


def _parse_format_a(rows, header, header_idx):
    """
    Bred tabell: én rad per marked.
    Kolonner inneholder markedsnavn, dato, og verdier per kategori.
    Vi leter spesielt etter "investment fund" long/short-kolonner.
    """
    results = {}
    h = header

    def find_col(keywords):
        """Finn kolonne-indeks som inneholder alle keywords i overskriften (evt. kombinert med naborade)."""
        for i, c in enumerate(h):
            if all(kw in c for kw in keywords):
                return i
        return None

    def find_col_any(keywords):
        for i, c in enumerate(h):
            if any(kw in c for kw in keywords):
                return i
        return None

    market_col  = find_col_any(["product", "market", "contract", "commodity", "instrument"])
    date_col    = find_col_any(["date", "reference", "reporting"])
    oi_col      = find_col_any(["open interest", "open_interest", "total oi"])

    # Investment Funds (spekulanter) — lang/short
    spec_long_col  = None
    spec_short_col = None
    for i, c in enumerate(h):
        if any(k in c for k in SPEC_KEYWORDS):
            if "long" in c and spec_long_col is None:
                spec_long_col = i
            elif "short" in c and spec_short_col is None:
                spec_short_col = i

    # Fallback: "non-commercial" (eldre format)
    if spec_long_col is None:
        for i, c in enumerate(h):
            if ("non-commercial" in c or "noncommercial" in c):
                if "long" in c and spec_long_col is None:
                    spec_long_col = i
                elif "short" in c and spec_short_col is None:
                    spec_short_col = i

    if market_col is None or spec_long_col is None:
        return {}

    # Parse datarader
    for row in rows[header_idx + 1:]:
        if not row or row[market_col] is None:
            continue
        crop = match_market(row[market_col])
        if crop is None:
            continue

        mm_long  = safe_int(row[spec_long_col]  if spec_long_col  < len(row) else None)
        mm_short = safe_int(row[spec_short_col] if spec_short_col and spec_short_col < len(row) else None)
        mm_net   = mm_long - mm_short
        oi       = safe_int(row[oi_col] if oi_col and oi_col < len(row) else None)
        if oi == 0:
            oi = max(abs(mm_net) * 6, 1)

        raw_date = row[date_col] if date_col and date_col < len(row) else None
        date_str = _parse_date(raw_date)

        if mm_long == 0 and mm_short == 0:
            continue

        # Ikke overskriv med dårligere data
        if crop in results and results[crop]["mm_long"] > mm_long and mm_long == 0:
            continue

        results[crop] = {
            "mm_long":  mm_long,
            "mm_short": mm_short,
            "mm_net":   mm_net,
            "oi":       oi,
            "date":     date_str,
        }

    return results


def _parse_format_b(rows):
    """
    Lang tabell: én rad per marked × kategori.
    Typiske kolonner: Product | Category | Date | Long | Short | Change Long | Change Short | % OI
    """
    # Finn header
    header_idx = None
    header_row = None
    for i, row in enumerate(rows[:30]):
        s = " ".join(normalize(c) for c in row if c is not None)
        if ("category" in s or "participant" in s or "type" in s) and "long" in s:
            header_row = [normalize(c) for c in row]
            header_idx = i
            break

    if header_row is None:
        return {}

    h = header_row
    def find_col_any(kws):
        for i, c in enumerate(h):
            if any(kw in c for kw in kws):
                return i
        return None

    market_col   = find_col_any(["product", "market", "contract", "commodity"])
    category_col = find_col_any(["category", "participant", "type", "trader"])
    date_col     = find_col_any(["date", "reference"])
    long_col     = find_col_any(["long"])
    short_col    = find_col_any(["short"])
    oi_col       = find_col_any(["open interest", "oi"])

    if market_col is None or long_col is None:
        return {}

    by_crop = {}
    for row in rows[header_idx + 1:]:
        if not row:
            continue
        crop = match_market(row[market_col] if market_col < len(row) else None)
        if crop is None:
            continue

        cat_val = row[category_col] if category_col and category_col < len(row) else ""
        if not is_speculator_row(cat_val):
            continue

        mm_long  = safe_int(row[long_col]  if long_col  < len(row) else None)
        mm_short = safe_int(row[short_col] if short_col and short_col < len(row) else None)
        oi       = safe_int(row[oi_col] if oi_col and oi_col < len(row) else None)
        raw_date = row[date_col] if date_col and date_col < len(row) else None
        date_str = _parse_date(raw_date)

        if mm_long == 0 and mm_short == 0:
            continue

        entry = by_crop.setdefault(crop, {"mm_long": 0, "mm_short": 0, "mm_net": 0,
                                           "oi": 0, "date": date_str})
        entry["mm_long"]  += mm_long
        entry["mm_short"] += mm_short
        entry["mm_net"]    = entry["mm_long"] - entry["mm_short"]
        if oi > entry["oi"]:
            entry["oi"] = oi

    return by_crop


def _parse_date(raw):
    if raw is None:
        return ""
    if isinstance(raw, datetime):
        return raw.strftime("%Y-%m-%d")
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                "%d.%m.%Y", "%B %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return s[:10] if len(s) >= 10 else s


# ── Historikk ────────────────────────────────────────────────────────────────

def load_history():
    if HIST.exists():
        try:
            return json.loads(HIST.read_text())
        except Exception:
            pass
    return {}


def update_history(history, parsed):
    for crop, data in parsed.items():
        entries = history.setdefault(crop, [])
        date = data.get("date", "")
        if entries and entries[-1].get("date") == date:
            continue
        entries.append({"date": date, "net": data["mm_net"],
                        "long": data["mm_long"], "short": data["mm_short"]})
        history[crop] = entries[-26:]
    return history


def calc_change(history, crop, current_net):
    entries = history.get(crop, [])
    if len(entries) >= 2:
        return current_net - entries[-2]["net"]
    return 0


# ── Bygg output ───────────────────────────────────────────────────────────────

CROP_DISPLAY = {
    "wheat":     "Milling Wheat (Euronext EBM)",
    "canola":    "Rapeseed (Euronext EBR)",
    "corn":      "Corn/Maize (Euronext EMA)",
    "sunflower": "Sunflower Seed (Euronext)",
}


def build_output(parsed, history):
    results = {}
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for crop, data in parsed.items():
        net    = data["mm_net"]
        oi     = data.get("oi") or max(abs(net) * 7, 1)
        date   = data.get("date") or today
        change = calc_change(history, crop, net)
        hist   = [e["net"] for e in history.get(crop, [])]

        results[crop] = {
            "crop":        crop,
            "display":     CROP_DISPLAY.get(crop, f"Euronext {crop.title()}"),
            "spekulanter": {
                "long":  data["mm_long"],
                "short": data["mm_short"],
                "net":   net,
                "label": "Investment Funds (MiFID II)",
            },
            "open_interest":   oi,
            "change_spec_net": change,
            "spec_net_history": hist,
            "date":   date,
            "report": "euronext",
            "source": "Euronext",
        }

    return results


# ── Hoved ────────────────────────────────────────────────────────────────────

def main():
    print("Henter Euronext agri COT-data (MiFID II)...")

    raw = download_excel()
    if raw is None:
        print("  FEIL: Kunne ikke laste ned Euronext COT Excel")
        return False

    try:
        parsed = parse_euronext_excel(raw)
    except Exception as e:
        print(f"  FEIL ved parsing: {e}")
        return False

    if not parsed:
        print("  FEIL: Ingen Euronext-markeder funnet i Excel-filen")
        return False

    history = load_history()
    history = update_history(history, parsed)
    HIST.write_text(json.dumps(history, ensure_ascii=False, indent=2))

    output_data = build_output(parsed, history)
    now_str     = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = {
        "generated": now_str,
        "source":    "Euronext Derivatives — MiFID II COT",
        "markets":   output_data,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    print(f"  OK → {len(output_data)} avlinger lagret")
    for crop, d in output_data.items():
        net = d["spekulanter"]["net"]
        oi  = d["open_interest"]
        pct = net / oi * 100 if oi else 0
        print(f"    {d['display']:40} net={net:+,}  ({pct:+.1f}% OI)  {d['date']}")

    return True


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)
