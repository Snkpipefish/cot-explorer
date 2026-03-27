#!/usr/bin/env bash
# Automatisk oppdatering av COT Explorer
# Kjøres 6× daglig (hverdager): 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 CET

set -e
cd "$(dirname "$0")"

LOG_DIR="$HOME/cot-explorer/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/update.log"

echo "=== $(date '+%Y-%m-%d %H:%M %Z') ===" >> "$LOG"

python3 fetch_calendar.py >> "$LOG" 2>&1 && echo "  kalender OK" >> "$LOG"
python3 fetch_cot.py      >> "$LOG" 2>&1 && echo "  COT OK"      >> "$LOG"
python3 build_combined.py >> "$LOG" 2>&1 && echo "  combined OK" >> "$LOG"

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

# Push signaler til Telegram/Discord (kun hvis minst én er konfigurert)
if [ -n "$TELEGRAM_TOKEN" ] || [ -n "$DISCORD_WEBHOOK" ] || [ -n "$SCALP_API_KEY" ]; then
    python3 push_signals.py >> "$LOG" 2>&1 && echo "  push OK" >> "$LOG"
else
    echo "  push: ingen bot konfigurert (sett TELEGRAM_TOKEN/DISCORD_WEBHOOK)" >> "$LOG"
fi

# Push data-filer til GitHub (oppdaterer GitHub Pages)
git add data/macro/latest.json data/calendar/ data/combined/ data/fundamentals/ data/comex/ data/geointel/ 2>/dev/null || true
if git diff --cached --quiet; then
    echo "  git: ingen nye data å pushe" >> "$LOG"
else
    git commit -m "data: oppdatering $(date '+%Y-%m-%d %H:%M')" >> "$LOG" 2>&1
    git push origin main >> "$LOG" 2>&1 && echo "  git push OK" >> "$LOG" || echo "  git push FEIL" >> "$LOG"
fi

echo "  FERDIG" >> "$LOG"
