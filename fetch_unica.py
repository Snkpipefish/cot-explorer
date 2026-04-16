#!/usr/bin/env python3
"""
fetch_unica.py — UNICA halvmånedlige crush-rapport (Brasil Centro-Sul)

Henter "Acompanhamento quinzenal da safra" fra unicadata.com.br, parser
mix-prosent og crush-volum via pdftotext.

Data-flow:
  1. GET https://unicadata.com.br/listagem.php?idMn=63  (index)
  2. Regex ut første .pdf-lenke (embedded i Google-Docs-viewer URL)
  3. Download PDF direkte (ikke via Google Docs)
  4. pdftotext -layout → regex nøkkeltall

Output:
  data/unica/latest.json   — siste rapport
  data/unica/history.json  — rullerende historikk (24 entries ≈ 1 år)

Brukes av: push_agri_signals.py (sugar-mix-driver)

Kjøring:
  python3 fetch_unica.py            — full kjøring
  python3 fetch_unica.py --dry-run  — print, ikke skriv
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

BASE     = Path(__file__).parent
OUT_DIR  = BASE / "data" / "unica"
OUT      = OUT_DIR / "latest.json"
HIST     = OUT_DIR / "history.json"
HIST_MAX = 24

DRY_RUN  = "--dry-run" in sys.argv

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

INDEX_URL = "https://unicadata.com.br/listagem.php?idMn=63"


def _http_get(url, timeout=30):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code} på {url}")
    except Exception as e:
        print(f"    FEIL ({url}): {e}")
    return None


def _pdftotext(pdf_bytes) -> str | None:
    if not pdf_bytes:
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fp:
        fp.write(pdf_bytes)
        tmp_path = fp.name
    try:
        r = subprocess.run(
            ["pdftotext", "-layout", tmp_path, "-"],
            capture_output=True, timeout=60
        )
        if r.returncode != 0:
            print(f"    pdftotext feilet: {r.stderr.decode(errors='replace')[:200]}")
            return None
        return r.stdout.decode("utf-8", errors="replace")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _find_latest_pdf_url() -> str | None:
    """Finn URL til siste quinzenal-rapport.
    UNICA embedder PDF i Google Docs viewer: docs.google.com/gview?url=<direkte>
    — vi ekstraherer den direkte URLen fra viewer-lenken."""
    html = _http_get(INDEX_URL)
    if not html:
        return None
    text = html.decode("utf-8", errors="replace")
    # Mønster: gview?url=https://unicadata.com.br/arquivos/pdfs/YYYY/MM/{hash}.pdf
    m = re.search(
        r'gview\?url=(https?://unicadata\.com\.br/arquivos/pdfs/\d{4}/\d{1,2}/[a-f0-9]+\.pdf)',
        text
    )
    if m:
        return m.group(1)
    # Fallback: direkte .pdf-lenker til arquivos
    direct = re.findall(
        r'(https?://unicadata\.com\.br/arquivos/pdfs/\d{4}/\d{1,2}/[a-f0-9]+\.pdf)',
        text
    )
    return direct[0] if direct else None


# ── Parsing ──────────────────────────────────────────────────────────────────

def _br_num(s: str) -> float | None:
    """'603.667' → 603667.0. '-2,21%' → -2.21."""
    if s is None:
        return None
    s = s.strip().replace("%", "").strip()
    if not s:
        return None
    neg = s.startswith("-")
    if neg:
        s = s[1:].strip()
    s = s.replace(".", "").replace(",", ".")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def parse_unica(text: str) -> dict:
    """Trekk ut mix-prosent, crush-akkumulert, og periode fra UNICA PDF."""
    data = {}

    # Periode: "Posição até DD/MM/YYYY" eller "referente à Xª quinzena de MMM de YYYY"
    m = re.search(r"Posição\s+até\s+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if m:
        data["position_date"] = m.group(1)

    m = re.search(
        r"(1ª|2ª)\s+quinzena\s+de\s+([a-zç]+)\s+de\s+(\d{4})",
        text, re.IGNORECASE
    )
    if m:
        data["period"] = f"{m.group(1)} quinzena de {m.group(2).lower()} de {m.group(3)}"

    # Safra-år: "SAFRA 2025/2026"
    m = re.search(r"SAFRA\s+(\d{4}/\d{4})", text, re.IGNORECASE)
    if m:
        data["crop_year"] = m.group(1)

    # Mix-rad i Tabela 1 (Centro-Sul akkumulert):
    #   açúcar    48,08%    50,61%    <blank/no change>    54,23%    ...
    #   etanol    51,92%    49,39%    <blank>              45,77%    ...
    # Vi tar de TO første %-tallene etter "açúcar"/"etanol" (CS prev + curr)
    m = re.search(
        r"açúcar\s+([\d,]+)%\s+([\d,]+)%",
        text, re.IGNORECASE
    )
    if m:
        data["mix_sugar_pct_prev_year"] = _br_num(m.group(1))
        data["mix_sugar_pct"] = _br_num(m.group(2))
    m = re.search(
        r"etanol\s+([\d,]+)%\s+([\d,]+)%",
        text, re.IGNORECASE
    )
    if m:
        data["mix_ethanol_pct_prev_year"] = _br_num(m.group(1))
        data["mix_ethanol_pct"] = _br_num(m.group(2))

    # Cana-de-açúcar-rad (Centro-Sul akkumulert crush i tusen tonn):
    #   Cana-de-açúcar ¹   617.317   603.667   -2,21%  ...
    m = re.search(
        r"Cana-de-açúcar[^\n]*?\s+([\d.]+)\s+([\d.]+)\s+(-?[\d,]+)%",
        text, re.IGNORECASE
    )
    if m:
        data["crush_accumulated_kt_prev"]   = _br_num(m.group(1))
        data["crush_accumulated_kt"]        = _br_num(m.group(2))
        data["crush_accumulated_yoy_pct"]   = _br_num(m.group(3))

    # Açúcar-produksjon-rad (Centro-Sul akkumulert):
    m = re.search(
        r"^\s*Açúcar[^\n]*?\s+([\d.]+)\s+([\d.]+)\s+(-?[\d,]+)%",
        text, re.IGNORECASE | re.MULTILINE
    )
    if m:
        data["sugar_production_kt_prev"]  = _br_num(m.group(1))
        data["sugar_production_kt"]       = _br_num(m.group(2))
        data["sugar_production_yoy_pct"]  = _br_num(m.group(3))

    # Etanol total akkumulert:
    m = re.search(
        r"Etanol total[^\n]*?\s+([\d.]+)\s+([\d.]+)\s+(-?[\d,]+)%",
        text, re.IGNORECASE
    )
    if m:
        data["ethanol_total_ml_prev"]  = _br_num(m.group(1))
        data["ethanol_total_ml"]       = _br_num(m.group(2))
        data["ethanol_total_yoy_pct"]  = _br_num(m.group(3))

    return data


def _load_history() -> list:
    if not HIST.exists():
        return []
    try:
        with open(HIST, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _apply_qoq(latest: dict, history: list):
    """Beregn quinzenal-over-quinzenal endring i mix_sugar_pct.
    Bruker forrige history-entry hvis periode ≠ nåværende."""
    if not history:
        return
    prev = history[-1]
    if prev.get("period") == latest.get("period"):
        return  # samme rapport
    cur_mix = latest.get("mix_sugar_pct")
    prv_mix = prev.get("mix_sugar_pct")
    if cur_mix is not None and prv_mix is not None:
        latest["mix_sugar_change_pct_qoq"] = round(cur_mix - prv_mix, 2)
        latest["prev_period"] = prev.get("period")


def main():
    print("[UNICA]")
    url = _find_latest_pdf_url()
    if not url:
        print("  Kunne ikke finne PDF-URL på index — avbryter")
        sys.exit(1)
    print(f"  PDF: {url}")
    pdf = _http_get(url)
    if not pdf:
        sys.exit(1)
    print(f"  Lastet ned {len(pdf)//1024} KB")
    text = _pdftotext(pdf)
    if not text:
        sys.exit(1)

    data = parse_unica(text)
    if not data.get("mix_sugar_pct"):
        print("  Mix-data ikke funnet — regex kan ha brutt")
        sys.exit(1)

    # Logg nøkkeltall
    print(f"  Periode: {data.get('period')}  safra: {data.get('crop_year')}")
    print(f"  Mix sukker: {data.get('mix_sugar_pct')}%  "
          f"(forrige år: {data.get('mix_sugar_pct_prev_year')}%)")
    print(f"  Crush akk.: {data.get('crush_accumulated_kt')} kt  "
          f"({data.get('crush_accumulated_yoy_pct')}% YoY)")
    print(f"  Sukker prod.: {data.get('sugar_production_kt')} kt")

    latest = {
        "generated":  datetime.now(timezone.utc).isoformat(),
        "source_url": url,
        **data,
    }

    history = _load_history()
    _apply_qoq(latest, history)
    if latest.get("mix_sugar_change_pct_qoq") is not None:
        print(f"  Mix QoQ-change: {latest['mix_sugar_change_pct_qoq']:+.2f} pp")

    if DRY_RUN:
        print("\n--dry-run: INGEN filer skrevet.")
        print(json.dumps(latest, ensure_ascii=False, indent=2))
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, OUT)
    print(f"Skrev {OUT}")

    # Append til history kun hvis ny periode
    last_period = history[-1].get("period") if history else None
    if latest.get("period") and latest["period"] != last_period:
        history.append(latest)
        history = history[-HIST_MAX:]
        HIST.write_text(json.dumps(history, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print(f"Oppdaterte {HIST} ({len(history)} entries)")
    else:
        print(f"history: samme periode som forrige kjøring — beholdes")


if __name__ == "__main__":
    main()
