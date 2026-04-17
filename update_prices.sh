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

# Patch agri-priser fra bot_history + macro (lettvekts — ingen API-kall)
python3 -c "
import json, os
AGRI = os.path.expanduser('~/cot-explorer/data/agri/latest.json')
MACRO = os.path.expanduser('~/cot-explorer/data/macro/latest.json')
BOT_H = os.path.expanduser('~/cot-explorer/data/prices/bot_history.json')
CROP_MAP = {'corn':'Corn','wheat':'Wheat','soybeans':'Soybean','coffee':'Coffee','cotton':'Cotton','sugar':'Sugar','cocoa':'Cocoa'}
try:
    agri = json.load(open(AGRI))
    macro_prices = json.load(open(MACRO)).get('prices', {})
    bot_prices = {}
    if os.path.exists(BOT_H):
        bh = json.load(open(BOT_H))
        for k, v in bh.items():
            if isinstance(v, dict) and 'price' in v:
                bot_prices[k] = v
            elif isinstance(v, list) and v and 'price' in v[-1]:
                bot_prices[k] = v[-1]
    patched = 0
    for c in agri.get('crop_summary', []):
        pk = CROP_MAP.get(c.get('crop_key',''))
        if not pk: continue
        # Bot-priser prioriteres (ferske fra cTrader)
        bp = bot_prices.get(pk)
        mp = macro_prices.get(pk, {})
        if bp:
            c['price'] = {'value': bp['price'], 'chg1d': mp.get('chg1d',0), 'chg5d': mp.get('chg5d',0), 'chg20d': mp.get('chg20d',0), 'source': 'bot'}
            patched += 1
        elif mp.get('price'):
            c['price'] = {'value': mp['price'], 'chg1d': mp.get('chg1d',0), 'chg5d': mp.get('chg5d',0), 'chg20d': mp.get('chg20d',0), 'source': mp.get('source','macro')}
            patched += 1
    from datetime import datetime, timezone
    agri['generated'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    json.dump(agri, open(AGRI,'w'), ensure_ascii=False, indent=2)
    print(f'  agri-priser patched ({patched} avlinger)')
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

# Re-evaluér scores med oppdaterte priser (0 API-kall)
echo "  Rescore..." >> "$LOG"
python3 rescore.py >> "$LOG" 2>&1 \
    && echo "  rescore OK" >> "$LOG" \
    || echo "  rescore FEIL" >> "$LOG"

# SCALP-signaler (og alle andre signaler) pushes kun i update.sh hver 4. time.
# Grunn: hourly push tømte signals.json når ingen nye SCALP-kandidater fantes,
# noe som slettet eksisterende SWING/MAKRO-signaler mellom 4-timers runs.

# K5: Sync trade-log fra scalp_edge-boten (bot skriver lokalt, vi committer)
SCALP_LOG="$HOME/scalp_edge/signal_log.json"
COT_LOG="$HOME/cot-explorer/data/signal_log.json"
TRADE_LOG_CHANGED=0
if [ -f "$SCALP_LOG" ]; then
    if [ ! -f "$COT_LOG" ] || ! cmp -s "$SCALP_LOG" "$COT_LOG"; then
        cp "$SCALP_LOG" "$COT_LOG" \
            && echo "  trade-log synket fra scalp_edge" >> "$LOG" \
            && TRADE_LOG_CHANGED=1
    fi
fi

# Push oppdatert data til GitHub Pages (kun priser — signaler oppdateres i update.sh)
# git add -u data/ fanger alle modifiserte filer under data/ (inkl. bot_history.json)
# → hindrer at unstaged endringer gjør git rebase umulig.
git add -u data/ 2>/dev/null || true
if [ "$TRADE_LOG_CHANGED" -eq 1 ]; then
    git add data/signal_log.json 2>/dev/null || true
fi
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
