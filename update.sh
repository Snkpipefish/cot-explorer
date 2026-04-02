#!/usr/bin/env bash
# Automatisk oppdatering av COT Explorer
# Kjøres 6× daglig (hverdager): 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 CET

set -e
cd "$(dirname "$0")"

# Last inn miljøvariabler (FRED_API_KEY, TWELVEDATA_API_KEY, FINNHUB_API_KEY, osv.)
# systemd laster ikke ~/.bashrc automatisk, så vi gjør det eksplisitt her
if [ -f "$HOME/.cot-env" ]; then
    set -a
    source "$HOME/.cot-env"
    set +a
elif [ -f "$HOME/.bashrc" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$HOME/.bashrc" 2>/dev/null || true
    set +a
fi

# Synk med origin før vi begynner
git fetch origin main 2>/dev/null && git rebase origin/main 2>/dev/null || true


LOG_DIR="$HOME/cot-explorer/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/update.log"

echo "=== $(date '+%Y-%m-%d %H:%M %Z') ===" >> "$LOG"

python3 fetch_calendar.py >> "$LOG" 2>&1 && echo "  kalender OK" >> "$LOG"
python3 fetch_cot.py      >> "$LOG" 2>&1 && echo "  COT OK"      >> "$LOG"
python3 build_combined.py >> "$LOG" 2>&1 && echo "  combined OK" >> "$LOG"
python3 fetch_ice_cot.py      >> "$LOG" 2>&1 \
    && echo "  ICE COT OK"      >> "$LOG" \
    || echo "  ICE COT FEIL (faller tilbake på CFTC)" >> "$LOG"
python3 fetch_euronext_cot.py >> "$LOG" 2>&1 \
    && echo "  Euronext COT OK" >> "$LOG" \
    || echo "  Euronext COT FEIL (faller tilbake på CFTC)" >> "$LOG"

# Fundamentals: kjøres kun én gang per 12 timer (FRED-data oppdateres månedlig/ukentlig)
FUND_FILE="$HOME/cot-explorer/data/fundamentals/latest.json"
if [ ! -f "$FUND_FILE" ] || [ "$(find "$FUND_FILE" -mmin +720 2>/dev/null | wc -l)" -gt 0 ]; then
    python3 fetch_fundamentals.py >> "$LOG" 2>&1 \
        && echo "  fundamentals OK" >> "$LOG" \
        || echo "  fundamentals FEIL (sjekk FRED_API_KEY / nettverkstilgang)" >> "$LOG"
else
    echo "  fundamentals: nylig oppdatert, hopper over" >> "$LOG"
fi

python3 fetch_all.py      >> "$LOG" 2>&1 && echo "  analyse OK"  >> "$LOG"

# Metals Intel: COMEX lagerdata, jordskjelv, intel-feed
python3 fetch_comex.py   >> "$LOG" 2>&1 && echo "  COMEX OK"    >> "$LOG" || echo "  COMEX FEIL"   >> "$LOG"
python3 fetch_seismic.py >> "$LOG" 2>&1 && echo "  seismikk OK" >> "$LOG" || echo "  seismikk FEIL" >> "$LOG"
python3 fetch_intel.py   >> "$LOG" 2>&1 && echo "  intel OK"    >> "$LOG" || echo "  intel FEIL"    >> "$LOG"
python3 fetch_agri.py     >> "$LOG" 2>&1 && echo "  agri OK"     >> "$LOG" || echo "  agri FEIL"     >> "$LOG"
python3 fetch_shipping.py >> "$LOG" 2>&1 && echo "  shipping OK" >> "$LOG" || echo "  shipping FEIL" >> "$LOG"
python3 fetch_oilgas.py   >> "$LOG" 2>&1 && echo "  oilgas OK"   >> "$LOG" || echo "  oilgas FEIL"   >> "$LOG"
python3 fetch_crypto.py   >> "$LOG" 2>&1 && echo "  krypto OK"   >> "$LOG" || echo "  krypto FEIL"   >> "$LOG"

# Push signaler — kjøres alltid (skriver signals.json og signal_log.json)
python3 push_signals.py >> "$LOG" 2>&1 && echo "  signals OK" >> "$LOG" || echo "  signals FEIL" >> "$LOG"

# Push data-filer til GitHub (oppdaterer GitHub Pages)
git add data/macro/latest.json data/signals.json data/signal_log.json data/calendar/ data/combined/ data/fundamentals/ data/comex/ data/geointel/ data/agri/ data/shipping/ data/oilgas/ data/crypto/ 2>/dev/null || true
if git diff --cached --quiet; then
    echo "  git: ingen nye data å pushe" >> "$LOG"
else
    git commit -m "data: oppdatering $(date '+%Y-%m-%d %H:%M')" >> "$LOG" 2>&1
    git fetch origin main >> "$LOG" 2>&1 && git rebase origin/main >> "$LOG" 2>&1 || true
    git push origin main >> "$LOG" 2>&1 && echo "  git push OK" >> "$LOG" || echo "  git push FEIL" >> "$LOG"
fi

echo "  FERDIG" >> "$LOG"
