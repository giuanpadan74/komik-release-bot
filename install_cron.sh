#!/bin/bash
# Komik Release Bot - Installazione cronjob
# Esegui: bash install_cron.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Komik Release Bot - Installazione ==="

# 1. Test bot
echo "[1/3] Test connessione bot..."
python3 -c "
import json, requests
with open('$SCRIPT_DIR/config.json') as f:
    cfg = json.load(f)
r = requests.get(f'https://api.telegram.org/bot{cfg[\"bot_token\"]}/getMe', timeout=10)
d = r.json()
if d.get('ok'):
    print(f'✅ Bot OK: @{d[\"result\"][\"username\"]}')
else:
    print(f'❌ Bot error: {d}')
    exit(1)
"

# 2. Test run
echo "[2/3] Test esecuzione scraper..."
python3 "$SCRIPT_DIR/scraper.py" || echo "⚠️  Scraper ha avuto errori (normale se il bot non è nel gruppo)"

# 3. Installa cronjob
echo "[3/3] Installazione cronjob..."
# Ogni lunedì alle 10:00 (uscite del martedì)
CRON_LINE="0 10 * * 1 cd $SCRIPT_DIR && /usr/bin/python3 $SCRIPT_DIR/scraper.py >> $SCRIPT_DIR/cron.log 2>&1"
(crontab -l 2>/dev/null | grep -v "komik-release-bot"; echo "$CRON_LINE") | crontab -

echo ""
echo "✅ Installazione completata!"
echo ""
echo "📋 Config:"
echo "   Script: $SCRIPT_DIR/scraper.py"
echo "   Config: $SCRIPT_DIR/config.json"
echo "   Calendario: $SCRIPT_DIR/calendario.json"
echo "   Log: $SCRIPT_DIR/cron.log"
echo "   Cron: ogni lunedì alle 10:00"
echo ""
echo "🔧 Comandi utili:"
echo "   Test:  python3 $SCRIPT_DIR/scraper.py"
echo "   Cron:  crontab -l"
echo "   Log:   tail -f $SCRIPT_DIR/cron.log"
echo ""
echo "⚠️  Aggiungi il bot al gruppo @komgaitaliafumetticlub!"
