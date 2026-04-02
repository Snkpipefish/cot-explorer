#!/usr/bin/env python3
"""
fetch_euronext_cot.py — Henter Euronext COT-data for landbruksråvarer (MiFID II)

Euronext publiserer hver onsdag ettermiddag, posisjoner per foregående fredag.
Dekker: Milling Wheat (EBM), Rapeseed (ECO), Corn/Maize (EMA)

URL-mønster (HTML per produkt):
  https://live.euronext.com/sites/default/files/commodities_reporting/YYYY/MM/DD/en/cdwpr_{SYMBOL}_{YYYYMMDD}.html

MiFID II-kategorier:
  - Investment Funds          → spekulanter (tilsvarer CFTC Managed Money)
  - Investment Firms/Banks    → mellommenn
  - Commercial Undertakings   → hedgere
  - Other Financial           → other reportables

Output: data/euronext_cot/latest.json
        data/euronext_cot/history.json
"""

import json
import re
from datetime import datetime, timezone, timedelta, date as _date
from html.parser import HTMLParser
from pathlib import Path

import requests

BASE    = Path(__file__).parent
OUT_DIR = BASE / "data" / "euronext_cot"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT  = OUT_DIR / "latest.json"
HIST = OUT_DIR / "history.json"

# Euronext-symboler vi henter
SYMBOLS = {
    "EBM": "wheat",
    "ECO": "canola",
    "EMA": "corn",
}

SPEC_KEYWORDS = ["investment fund", "fonds d'investissement", "managed", "fond"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://live.euronext.com/",
}

EURONEXT_BASE = "https://live.euronext.com/sites/default/files/commodities_reporting"


# ── URL-generering ────────────────────────────────────────────────────────────

def recent_wednesdays(n=6):
    """Returner de n siste onsdagsdatoer."""
    today = _date.today()
    days_since_wed = (today.weekday() - 2) % 7
    last_wed = today - timedelta(days=days_since_wed)
    return [last_wed - timedelta(weeks=i) for i in range(n)]


def report_url(symbol, d):
    ds = d.strftime("%Y%m%d")
    return f"{EURONEXT_BASE}/{d.year}/{d.month:02d}/{d.day:02d}/en/cdwpr_{symbol}_{ds}.html"


# ── Nedlasting ────────────────────────────────────────────────────────────────

def fetch_html_playwright(symbol, dates):
    """Bruk Playwright (headless Chrome) for å hente HTML-rapporter."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            # Sett cookies ved å besøke hoveddomen først
            page.goto("https://live.euronext.com/en/products/commodities/commitments_of_traders",
                      wait_until="domcontentloaded", timeout=20000)
            api = ctx.request
            for d in dates:
                url = report_url(symbol, d)
                try:
                    resp = api.get(url, headers=HEADERS, timeout=15000)
                    if resp.ok:
                        html = resp.text()
                        if len(html) > 200 and "<table" in html.lower():
                            print(f"    Playwright OK: {url[-40:]}")
                            browser.close()
                            return html, d
                    else:
                        print(f"    HTTP {resp.status}: {url[-40:]}")
                except Exception as e:
                    print(f"    FEIL: {e}")
        except Exception as e:
            print(f"  Playwright FEIL: {e}")
        finally:
            browser.close()
    return None


def fetch_html_requests(symbol, dates):
    """Prøv requests med session-cookies."""
    sess = requests.Session()
    try:
        sess.get("https://live.euronext.com/", headers=HEADERS, timeout=10)
    except Exception:
        pass
    for d in dates:
        url = report_url(symbol, d)
        try:
            r = sess.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if r.status_code == 200 and "<table" in r.text.lower():
                print(f"    requests OK: {url[-40:]}")
                return r.text, d
            print(f"    HTTP {r.status_code}: {url[-40:]}")
        except Exception as e:
            print(f"    FEIL: {e}")
    return None


def fetch_report(symbol):
    """Hent HTML-rapport for ett symbol. Returnerer (html_tekst, dato) eller None."""
    dates = recent_wednesdays(6)
    print(f"  {symbol}: prøver {len(dates)} onsdager...")

    result = fetch_html_playwright(symbol, dates)
    if result:
        return result

    print(f"  {symbol}: Playwright feilet — prøver requests...")
    return fetch_html_requests(symbol, dates)


# ── HTML-parsing ──────────────────────────────────────────────────────────────

class TableParser(HTMLParser):
    """Enkel parser som trekker ut alle tabeller som lister av rader."""
    def __init__(self):
        super().__init__()
        self.tables = []
        self._cur_table = None
        self._cur_row = None
        self._cur_cell = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._cur_table = []
            self._depth += 1
        elif tag == "tr" and self._cur_table is not None:
            self._cur_row = []
        elif tag in ("td", "th") and self._cur_row is not None:
            self._cur_cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self._depth -= 1
            if self._depth == 0 and self._cur_table is not None:
                self.tables.append(self._cur_table)
                self._cur_table = None
        elif tag == "tr" and self._cur_row is not None:
            if self._cur_table is not None:
                self._cur_table.append(self._cur_row)
            self._cur_row = None
        elif tag in ("td", "th") and self._cur_cell is not None:
            text = " ".join(self._cur_cell).strip()
            if self._cur_row is not None:
                self._cur_row.append(text)
            self._cur_cell = None

    def handle_data(self, data):
        if self._cur_cell is not None:
            self._cur_cell.append(data.strip())


def safe_int(s):
    if not s:
        return 0
    try:
        return int(float(re.sub(r"[^\d.\-]", "", str(s))))
    except Exception:
        return 0


def is_spec_row(text):
    t = text.lower()
    return any(k in t for k in SPEC_KEYWORDS)


def parse_html_report(html):
    """
    Parser HTML-rapporten og returnerer dict med long/short/net/oi.
    Tabellen har rader per MiFID II-kategori med long/short-kolonner.
    """
    parser = TableParser()
    parser.feed(html)

    for table in parser.tables:
        if len(table) < 3:
            continue

        # Finn header-rad med "long" og "short"
        header_idx = None
        for i, row in enumerate(table[:10]):
            r = " ".join(row).lower()
            if "long" in r and "short" in r:
                header_idx = i
                break

        if header_idx is None:
            continue

        header = [c.lower() for c in table[header_idx]]

        # Finn kolonner
        def col(keywords):
            for i, h in enumerate(header):
                if all(k in h for k in keywords):
                    return i
            for i, h in enumerate(header):
                if any(k in h for k in keywords):
                    return i
            return None

        long_col  = col(["long"])
        short_col = col(["short"])
        oi_col    = col(["open interest", "oi", "open_interest"])
        chg_col   = col(["change", "variation", "chg"])

        if long_col is None:
            continue

        mm_long = mm_short = oi = chg = 0

        for row in table[header_idx + 1:]:
            if not row:
                continue
            label = row[0] if row else ""
            if not is_spec_row(label):
                continue

            if long_col < len(row):
                mm_long += safe_int(row[long_col])
            if short_col and short_col < len(row):
                mm_short += safe_int(row[short_col])
            if oi_col and oi_col < len(row):
                v = safe_int(row[oi_col])
                if v > oi:
                    oi = v
            if chg_col and chg_col < len(row):
                chg += safe_int(row[chg_col])

        if mm_long == 0 and mm_short == 0:
            continue

        return {
            "mm_long":  mm_long,
            "mm_short": mm_short,
            "mm_net":   mm_long - mm_short,
            "oi":       oi if oi > 0 else max(abs(mm_long - mm_short) * 6, 1),
            "chg":      chg,
        }

    return None


# ── Historikk ─────────────────────────────────────────────────────────────────

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
    "wheat":  "Milling Wheat (Euronext EBM)",
    "canola": "Rapeseed (Euronext ECO)",
    "corn":   "Corn/Maize (Euronext EMA)",
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
            "open_interest":    oi,
            "change_spec_net":  change,
            "spec_net_history": hist,
            "date":   date,
            "report": "euronext",
            "source": "Euronext",
        }

    return results


# ── Hoved ─────────────────────────────────────────────────────────────────────

def main():
    print("Henter Euronext agri COT-data (MiFID II)...")

    parsed = {}
    for symbol, crop in SYMBOLS.items():
        result = fetch_report(symbol)
        if result is None:
            print(f"  {symbol}: ikke tilgjengelig")
            continue
        html, report_date = result
        data = parse_html_report(html)
        if data is None:
            print(f"  {symbol}: kunne ikke parse HTML")
            continue
        data["date"] = report_date.strftime("%Y-%m-%d")
        parsed[crop] = data
        net = data["mm_net"]
        oi  = data["oi"]
        print(f"  {symbol} ({crop}): net={net:+,}  ({net/oi*100:+.1f}% OI)  {data['date']}")

    if not parsed:
        print("  FEIL: Ingen Euronext-markeder hentet")
        # Debug: hent og vis første tabell fra EBM
        result = fetch_report("EBM")
        if result:
            html, _ = result
            p = TableParser()
            p.feed(html)
            print(f"  DEBUG: {len(p.tables)} tabeller funnet")
            for ti, t in enumerate(p.tables[:3]):
                print(f"  Tabell {ti}: {len(t)} rader")
                for row in t[:8]:
                    print(f"    {row}")
        return False

    history = load_history()
    history = update_history(history, parsed)
    HIST.write_text(json.dumps(history, ensure_ascii=False, indent=2))

    output_data = build_output(parsed, history)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = {
        "generated": now_str,
        "source":    "Euronext Derivatives — MiFID II COT",
        "markets":   output_data,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"  OK → {len(output_data)} avlinger lagret til {OUT}")
    return True


if __name__ == "__main__":
    ok = main()
    raise SystemExit(0 if ok else 1)
