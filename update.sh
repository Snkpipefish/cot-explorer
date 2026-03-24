#!/usr/bin/env bash
# Automatisk oppdatering av COT Explorer
# Kjøres 4× daglig: 07:45, 12:30, 14:15, 17:15 CET/CEST

set -e
cd "$(dirname "$0")"

LOG_DIR="$HOME/cot-explorer/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/update.log"

echo "=== $(date '+%Y-%m-%d %H:%M %Z') ===" >> "$LOG"

python3 fetch_calendar.py >> "$LOG" 2>&1 && echo "  kalender OK" >> "$LOG"
python3 fetch_cot.py      >> "$LOG" 2>&1 && echo "  COT OK"      >> "$LOG"
python3 build_combined.py >> "$LOG" 2>&1 && echo "  combined OK" >> "$LOG"
python3 fetch_all.py      >> "$LOG" 2>&1 && echo "  analyse OK"  >> "$LOG"

# Push signaler til Telegram/Discord (kun hvis minst én er konfigurert)
if [ -n "$TELEGRAM_TOKEN" ] || [ -n "$DISCORD_WEBHOOK" ] || [ -n "$SCALP_API_KEY" ]; then
    python3 push_signals.py >> "$LOG" 2>&1 && echo "  push OK" >> "$LOG"
else
    echo "  push: ingen bot konfigurert (sett TELEGRAM_TOKEN/DISCORD_WEBHOOK)" >> "$LOG"
fi

# Push data-filer til GitHub (oppdaterer GitHub Pages)
git add data/macro/latest.json data/calendar/ data/combined/ 2>/dev/null || true
if git diff --cached --quiet; then
    echo "  git: ingen nye data å pushe" >> "$LOG"
else
    git commit -m "data: oppdatering $(date '+%Y-%m-%d %H:%M')" >> "$LOG" 2>&1
    git push origin main >> "$LOG" 2>&1 && echo "  git push OK" >> "$LOG" || echo "  git push FEIL" >> "$LOG"
fi

echo "  FERDIG" >> "$LOG"
