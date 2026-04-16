#!/usr/bin/env python3
"""
fetch_conab.py — Conab avlings-estimater (Brasil)

Henter to månedlige rapporter fra gov.br:
  - Boletim da Safra de Grãos (Soja, Milho, Trigo, Algodão)
  - Boletim da Safra de Café   (Arábica + Conilon)

Bruker pdftotext (poppler-utils) via subprocess — ingen Python PDF-lib kreves.

URL-pattern er predikert per safra-måned; faller tilbake til index-scraping
hvis predikert URL gir 404 (f.eks. ny levantamento-nummer eller filnavn-endring).

Output:
  data/conab/latest.json   — siste kjøring
  data/conab/history.json  — rullerende liste (beholder 24 eldste for m/m-sammenligning)

Brukes av: push_agri_signals.py (shock-flag ved m/m-revisjon >threshold)

Kjøring:
  python3 fetch_conab.py            — full kjøring, skriver til data/
  python3 fetch_conab.py --dry-run  — print ekstrahert data uten å skrive
"""

import io
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
OUT_DIR  = BASE / "data" / "conab"
OUT      = OUT_DIR / "latest.json"
HIST     = OUT_DIR / "history.json"
HIST_MAX = 24                    # Behold opptil 24 runder (≈ 2 år)

DRY_RUN  = "--dry-run" in sys.argv

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ── URL-kilder ───────────────────────────────────────────────────────────────
# Grains-indeks (inneholder linker til siste levantamento PDF)
GRAINS_INDEX = ("https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/"
                "safras/safra-de-graos/boletim-da-safra-de-graos")
CAFE_INDEX   = ("https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/"
                "safras/safra-de-cafe")


def _http_get(url, timeout=30):
    """GET med User-Agent og redirects. Returnerer bytes eller None ved feil."""
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
    """Kjør pdftotext -layout på bytes. Returnerer tekst eller None."""
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
            print(f"    pdftotext feilet (rc={r.returncode}): {r.stderr.decode(errors='replace')[:200]}")
            return None
        return r.stdout.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        print("    pdftotext timeout (>60s)")
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _find_pdf_on_index(index_url: str, keyword_substr: str) -> str | None:
    """Scrape index-side, returner første PDF-lenke som inneholder keyword."""
    html = _http_get(index_url)
    if not html:
        return None
    text = html.decode("utf-8", errors="replace")
    # Matcher href="..."  eller href='...' med PDF-utvidelse
    matches = re.findall(r'href=["\']([^"\']+\.pdf)["\']', text)
    for m in matches:
        if keyword_substr.lower() in m.lower():
            # Absoluttér relative URLer
            if m.startswith("/"):
                return "https://www.gov.br" + m
            if m.startswith("http"):
                return m
    return None


def _find_cafe_pdf() -> str | None:
    """Coffee har 2-nivå indeks: (index) → levantamento-side → PDF.
    Vi henter index, finner øverste /Xo-levantamento-de-cafe-safra-YYYY/-lenke,
    besøker den, returnerer første PDF der."""
    html = _http_get(CAFE_INDEX)
    if not html:
        return None
    text = html.decode("utf-8", errors="replace")
    # Finn levantamento-sider. Største nummer = nyeste; vi tar første treff
    # i dokument-rekkefølge som er den nyeste safra.
    levantamento_urls = re.findall(
        r'href=["\'](https://www\.gov\.br/conab/[^"\']*?/'
        r'\d+o-levantamento-de-cafe-safra-\d+/'
        r'\d+o-levantamento-de-cafe-safra-\d+)["\']',
        text
    )
    seen: set[str] = set()
    for lev_url in levantamento_urls:
        if lev_url in seen:
            continue
        seen.add(lev_url)
        print(f"  Prøver levantamento-side: {lev_url}")
        lev_html = _http_get(lev_url)
        if not lev_html:
            continue
        lev_text = lev_html.decode("utf-8", errors="replace")
        pdfs = re.findall(r'href=["\']([^"\']+\.pdf)["\']', lev_text)
        for pdf in pdfs:
            if "cafe" in pdf.lower() or "boletim-de-safras" in pdf.lower():
                if pdf.startswith("/"):
                    return "https://www.gov.br" + pdf
                return pdf
    return None


# ── Brasiliansk tallformat → float ───────────────────────────────────────────
def _br_num(s: str) -> float | None:
    """Konverter '179.151,6' eller '(2,1)' eller '12,4' til float.
    Parentes indikerer negativt tall i Conab-tabellene."""
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    # Fjern tusen-skiller (punktum) og bytt desimal-komma til punktum
    s = s.replace(".", "").replace(",", ".")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


# ── Grains: TABELA 1 — COMPARATIVO DE ÁREA, PRODUTIVIDADE E PRODUÇÃO ─────────
# Linje-format (ett mellomrom kan bli mange i pdftotext -layout):
#   SOJA  47.346,1  48.472,7  2,4  3.622  3.696  2,0  171.480,5  179.151,6  4,5
#   ALGODÃO - PLUMA  2.085,6  2.041,5  (2,1)  ...
#
# Numerisk gruppe: 9 tall (3× (prev, curr, change)) — area, yield, production.
_NUM  = r"\(?[\d.,]+\)?"
_GROW = r"\(?\-?[\d.,]+\)?"
_GRAIN_ROW_RE = re.compile(
    r"^\s*(?P<crop>[A-ZÇÃÁÉÍÓÚÂÊÔÜ\-\s]{3,40}?)\s{2,}"
    rf"(?P<a_prev>{_NUM})\s+(?P<a_curr>{_NUM})\s+(?P<a_chg>{_GROW})\s+"
    rf"(?P<y_prev>{_NUM})\s+(?P<y_curr>{_NUM})\s+(?P<y_chg>{_GROW})\s+"
    rf"(?P<p_prev>{_NUM})\s+(?P<p_curr>{_NUM})\s+(?P<p_chg>{_GROW})\s*$",
    re.MULTILINE
)

# Crops vi vil trekke ut. Nøkkel er output-key i JSON; verdi er liste med
# navne-substringer vi matcher mot Conab-tabellradens crop-felt (case-insens).
GRAINS_OF_INTEREST = {
    "soja":     ["SOJA"],
    "milho":    ["MILHO TOTAL"],
    "trigo":    ["TRIGO"],
    "algodao":  ["ALGODÃO - PLUMA", "ALGODAO - PLUMA"],  # traded = lint
}


def parse_grains(text: str) -> dict:
    """Ekstrahér soja/milho/trigo/algodão fra tabell-tekst."""
    result = {}
    for m in _GRAIN_ROW_RE.finditer(text):
        crop_raw = re.sub(r"\s+", " ", m.group("crop").strip().upper())
        for key, aliases in GRAINS_OF_INTEREST.items():
            if key in result:
                continue  # allerede funnet
            for alias in aliases:
                if alias.upper() == crop_raw or alias.upper() in crop_raw:
                    prod = _br_num(m.group("p_curr"))
                    area = _br_num(m.group("a_curr"))
                    yld  = _br_num(m.group("y_curr"))
                    p_chg = _br_num(m.group("p_chg"))
                    if prod is None:
                        continue
                    result[key] = {
                        "production_kt":  prod,    # tusen tonn
                        "area_kha":       area,
                        "yield_kgha":     yld,
                        "yoy_change_pct": p_chg,   # vs forrige safra (IKKE m/m)
                    }
                    break
    return result


def _extract_levantamento(text: str) -> tuple[str | None, str | None]:
    """Finn 'X LEVANTAMENTO' og 'SAFRA YYYY/YY' i PDF-tekst.
    Grains-format: "7º LEVANTAMENTO". Coffee-format: "nº1 – primeiro levantamento"."""
    lev = re.search(r"(\d+)[ºo°]?\s*LEVANTAMENTO", text, re.IGNORECASE)
    if not lev:
        # Coffee-variant: "n.1 - Primeiro levantamento" eller "nº1 – primeiro levantamento"
        lev = re.search(r"n[º.°]\s*(\d+)\s*[–\-]\s*\w+\s+levantamento",
                        text, re.IGNORECASE)
    safra = re.search(r"SAFRA\s+(\d{4}/\d{2,4})|SAFRA\s+(\d{4})",
                      text, re.IGNORECASE)
    safra_str = None
    if safra:
        safra_str = safra.group(1) or safra.group(2)
    return (
        f"{lev.group(1)}o" if lev else None,
        safra_str,
    )


# ── Café: TABELA 1 (total), 2 (arábica), 3 (conilon) ─────────────────────────
# Radmønster samme som grains, men label = "BRASIL" og vi må vite hvilken
# tabell vi er i. Vi scanner tekst linje-for-linje og tracker "TABELA N …".
# NB: ingen \n-lookahead — regex brukes på enkeltlinjer.
_CAFE_TABLE_RE = re.compile(r"TABELA\s+(\d+)\s*[–\-]\s*(.*)", re.IGNORECASE)
_CAFE_BRASIL_RE = re.compile(
    r"^\s*BRASIL\s+"
    rf"(?P<a_prev>{_NUM})\s+(?P<a_curr>{_NUM})\s+(?P<a_chg>{_GROW})\s+"
    rf"(?P<y_prev>{_NUM})\s+(?P<y_curr>{_NUM})\s+(?P<y_chg>{_GROW})\s+"
    rf"(?P<p_prev>{_NUM})\s+(?P<p_curr>{_NUM})\s+(?P<p_chg>{_GROW})\s*$",
    re.MULTILINE
)


def parse_cafe(text: str) -> dict:
    """Trekk ut BRASIL-totaler fra Tabela 1 (total), 2 (arábica), 3 (conilon)."""
    result = {}
    # Finn alle tabell-headers med linjenummer
    lines = text.splitlines()
    table_positions: list[tuple[int, int, str]] = []   # (line_idx, table_num, title)
    for i, line in enumerate(lines):
        mt = _CAFE_TABLE_RE.search(line)
        if mt:
            try:
                table_positions.append((i, int(mt.group(1)), mt.group(2).strip()))
            except ValueError:
                pass

    # For hver tabell, finn første BRASIL-rad etter headeren
    table_num_to_key = {1: "cafe_total", 2: "cafe_arabica", 3: "cafe_conilon"}
    for idx, (line_idx, tnum, title) in enumerate(table_positions):
        if tnum not in table_num_to_key:
            continue
        key = table_num_to_key[tnum]
        end_idx = table_positions[idx + 1][0] if idx + 1 < len(table_positions) else len(lines)
        segment = "\n".join(lines[line_idx:end_idx])
        m = _CAFE_BRASIL_RE.search(segment)
        if not m:
            continue
        prod = _br_num(m.group("p_curr"))
        if prod is None:
            continue
        result[key] = {
            "production_mbags":  round(prod / 1000.0 if prod > 1000 else prod, 2),
            "production_ksacas": prod,
            "area_kha":          _br_num(m.group("a_curr")),
            "yield_sacasha":     _br_num(m.group("y_curr")),
            "yoy_change_pct":    _br_num(m.group("p_chg")),
        }
    return result


# ── Måneds-over-måned: sammenlign med forrige history-entry ─────────────────
def _load_history() -> list:
    if not HIST.exists():
        return []
    try:
        with open(HIST, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _apply_mom(latest: dict, history: list):
    """Beregn mom_change_pct per crop ved å sammenligne med forrige entry."""
    if not history:
        return
    prev = history[-1]
    prev_crops = prev.get("crops", {})
    for crop_key, data in latest.get("crops", {}).items():
        prev_data = prev_crops.get(crop_key)
        if not prev_data:
            continue
        # Bruk riktig produksjonsfelt per kilde
        if "production_kt" in data:
            cur_prod = data.get("production_kt")
            prv_prod = prev_data.get("production_kt")
        elif "production_mbags" in data:
            cur_prod = data.get("production_mbags")
            prv_prod = prev_data.get("production_mbags")
        else:
            continue
        if cur_prod and prv_prod and prv_prod > 0:
            data["mom_change_pct"] = round((cur_prod - prv_prod) / prv_prod * 100, 2)
            data["prev_production"] = prv_prod
            data["prev_levantamento"] = prev.get("grains_levantamento") or prev.get("cafe_levantamento")


# ── Main flyt ────────────────────────────────────────────────────────────────
def fetch_grains() -> dict:
    print("[Conab grains]")
    url = _find_pdf_on_index(GRAINS_INDEX, "e-book_boletim-de-safras")
    if not url:
        print("  Kunne ikke finne PDF på index — avbryter grains")
        return {}
    print(f"  PDF: {url}")
    pdf = _http_get(url)
    if not pdf:
        return {}
    print(f"  Lastet ned {len(pdf)//1024} KB")
    text = _pdftotext(pdf)
    if not text:
        return {}
    lev, safra = _extract_levantamento(text)
    crops = parse_grains(text)
    if not crops:
        print("  Ingen crops funnet — regex kan ha brutt")
        return {}
    print(f"  Funnet: {list(crops.keys())} (lev={lev} safra={safra})")
    return {"grains_levantamento": lev, "grains_safra": safra,
            "grains_source_url": url, "crops": crops}


def fetch_cafe() -> dict:
    print("[Conab café]")
    url = _find_cafe_pdf()
    if not url:
        print("  Kunne ikke finne PDF på index — avbryter café")
        return {}
    print(f"  PDF: {url}")
    pdf = _http_get(url)
    if not pdf:
        return {}
    print(f"  Lastet ned {len(pdf)//1024} KB")
    text = _pdftotext(pdf)
    if not text:
        return {}
    lev, safra = _extract_levantamento(text)
    crops = parse_cafe(text)
    if not crops:
        print("  Ingen coffee-data funnet — regex kan ha brutt")
        return {}
    print(f"  Funnet: {list(crops.keys())} (lev={lev} safra={safra})")
    return {"cafe_levantamento": lev, "cafe_safra": safra,
            "cafe_source_url": url, "crops": crops}


def main():
    grains = fetch_grains()
    cafe   = fetch_cafe()

    if not grains and not cafe:
        print("INGEN DATA HENTET — avbryter uten å overskrive latest.json")
        sys.exit(1)

    # Merge — "crops" slås sammen, metadata beholdes atskilt
    combined_crops = {}
    combined_crops.update(grains.get("crops", {}))
    combined_crops.update(cafe.get("crops", {}))

    latest = {
        "generated":            datetime.now(timezone.utc).isoformat(),
        "grains_levantamento":  grains.get("grains_levantamento"),
        "grains_safra":         grains.get("grains_safra"),
        "grains_source_url":    grains.get("grains_source_url"),
        "cafe_levantamento":    cafe.get("cafe_levantamento"),
        "cafe_safra":           cafe.get("cafe_safra"),
        "cafe_source_url":      cafe.get("cafe_source_url"),
        "crops":                combined_crops,
    }

    # m/m-beregning fra history
    history = _load_history()
    _apply_mom(latest, history)

    # Rapportér
    for key, d in combined_crops.items():
        mom = d.get("mom_change_pct")
        mom_s = f" m/m {mom:+.2f}%" if mom is not None else ""
        prod = d.get("production_kt") or d.get("production_mbags")
        unit = "kt" if "production_kt" in d else "Mb"
        print(f"  {key}: {prod} {unit} yoy {d.get('yoy_change_pct','?')}%{mom_s}")

    if DRY_RUN:
        print("\n--dry-run: INGEN filer skrevet.")
        print(json.dumps(latest, ensure_ascii=False, indent=2))
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Atomisk skriv av latest.json
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, OUT)
    print(f"Skrev {OUT}")

    # Oppdater history kun hvis levantamento faktisk er ny (unngå duplikater
    # når update.sh kjøres flere ganger per måned).
    new_key = (latest.get("grains_levantamento"), latest.get("cafe_levantamento"))
    last_keys = [(h.get("grains_levantamento"), h.get("cafe_levantamento"))
                 for h in history]
    if new_key and (not last_keys or new_key != last_keys[-1]):
        history.append(latest)
        history = history[-HIST_MAX:]
        HIST.write_text(json.dumps(history, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print(f"Oppdaterte {HIST} ({len(history)} entries)")
    else:
        print(f"history: samme levantamento som forrige kjøring ({new_key}) — beholdes")


if __name__ == "__main__":
    main()
