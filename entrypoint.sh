#!/bin/bash
set -e

# Stampa variabili per debug (senza mostrare il token)
echo "=== Komik Release Bot ==="
echo "CHAT_ID: ${CHAT_ID:-NON CONFIGURATO}"
echo "TOPIC_ID: ${TOPIC_ID:-NON CONFIGURATO}"
echo "BOT_TOKEN: ${BOT_TOKEN:+CONFIGURATO}"
echo ""

# Esegui subito il primo run
echo "--- Primo run ---"
python /app/scraper.py || echo "Primo run completato (con eventuali errori)"

# Avvia cron in foreground
echo "--- Avvio cron ---"
cron -f
