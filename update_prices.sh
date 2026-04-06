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

# Patch agri-priser fra macro (lettvekts — ingen API-kall)
python3 -c "
import json, os
AGRI = os.path.expanduser('~/cot-explorer/data/agri/latest.json')
MACRO = os.path.expanduser('~/cot-explorer/data/macro/latest.json')
CROP_MAP = {'corn':'Corn','wheat':'Wheat','soybeans':'Soybean','coffee':'Coffee','cotton':'Cotton','sugar':'Sugar','cocoa':'Cocoa'}
try:
    agri = json.load(open(AGRI))
    prices = json.load(open(MACRO)).get('prices', {})
    for c in agri.get('crop_summary', []):
        pk = CROP_MAP.get(c.get('crop_key',''))
        if pk and pk in prices:
            p = prices[pk]
            c['price'] = {'value': p.get('price'), 'chg1d': p.get('chg1d',0), 'chg5d': p.get('chg5d',0), 'chg20d': p.get('chg20d',0), 'source': p.get('source','bot')}
    from datetime import datetime, timezone
    agri['generated'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    json.dump(agri, open(AGRI,'w'), ensure_ascii=False, indent=2)
    print('  agri-priser patched')
except Exception as e:
    print(f'  agri-priser FEIL: {e}')
" >> "$LOG" 2>&1

# Patch crypto-priser fra macro (lettvekts — ingen API-kall)
python3 -c "
import json, os
CRYPTO = os.path.expanduser('~/cot-explorer/data/crypto/latest.json')
MACRO = os.path.expanduser('~/cot-explorer/data/macro/latest.json')
try:
    crypto = json.load(open(CRYPTO))
    prices = json.load(open(MACRO)).get('prices', {})
    for k in list(crypto.get('prices', {}).keys()):
        if k in prices:
            mp = prices[k]
            crypto['prices'][k]['price'] = mp.get('price', crypto['prices'][k]['price'])
            if mp.get('chg1d') is not None: crypto['prices'][k]['chg1d'] = mp['chg1d']
            crypto['prices'][k]['source'] = mp.get('source', 'bot')
    from datetime import datetime, timezone
    crypto['updated'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    json.dump(crypto, open(CRYPTO,'w'), ensure_ascii=False, indent=2)
    print('  crypto-priser patched')
except Exception as e:
    print(f'  crypto-priser FEIL: {e}')
" >> "$LOG" 2>&1

# Push oppdatert data til GitHub Pages
git add data/macro/latest.json data/signals.json data/signal_log.json \
        data/oilgas/latest.json data/agri/latest.json data/crypto/latest.json 2>/dev/null || true
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
