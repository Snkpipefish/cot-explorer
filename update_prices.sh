#!/usr/bin/env bash
# update_prices.sh — Oppdaterer kun priser fra bot (live_prices.json → macro/latest.json)
# Kjøres hvert 58. minutt i timen av cron/systemd
# Raskere enn full update.sh — ingen COT, ingen nyheter, ingen git push

set -e
cd "$(dirname "$0")"

# Last inn miljøvariabler
if [ -f "$HOME/.cot-env" ]; then
    set -a; source "$HOME/.cot-env"; set +a
elif [ -f "$HOME/.bashrc" ]; then
    set -a; source "$HOME/.bashrc" 2>/dev/null || true; set +a
fi

LOG_DIR="$HOME/cot-explorer/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/prices.log"

echo "=== $(date '+%Y-%m-%d %H:%M %Z') ===" >> "$LOG"

# Bygg macro/latest.json fra bot-priser (+ Yahoo for det som mangler)
python3 fetch_prices.py >> "$LOG" 2>&1 \
    && echo "  priser OK" >> "$LOG" \
    || echo "  priser FEIL" >> "$LOG"

# Oppdater olje & gass med bot-priser
python3 fetch_oilgas.py >> "$LOG" 2>&1 \
    && echo "  oilgas OK" >> "$LOG" \
    || echo "  oilgas FEIL" >> "$LOG"

# Push oppdatert data til GitHub Pages
git add data/macro/latest.json data/signals.json data/signal_log.json \
        data/oilgas/latest.json 2>/dev/null || true
if git diff --cached --quiet; then
    echo "  git: ingen prisendring å pushe" >> "$LOG"
else
    git commit -m "priser: $(date '+%H:%M')" >> "$LOG" 2>&1
    git fetch origin main >> "$LOG" 2>&1 && git rebase origin/main >> "$LOG" 2>&1 || true
    git push origin main >> "$LOG" 2>&1 \
        && echo "  git push OK" >> "$LOG" \
        || echo "  git push FEIL" >> "$LOG"
fi

echo "  FERDIG" >> "$LOG"
