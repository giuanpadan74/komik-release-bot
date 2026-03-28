# Komik Release Bot 📚

Bot autonomo che raccoglie le uscite settimanali di fumetti e manga dalle principali case editrici italiane e le invia su Telegram.

**Completamente indipendente** — gira su GitHub Actions, non richiede KiloClaw né server.

## Fonti

| Fonte | Metodo | Affidabilità |
|-------|--------|-------------|
| MangaForever | RSS | ⭐⭐⭐ |
| Fumettologica | RSS | ⭐⭐⭐ |
| Star Comics | Web scraping (curl_cffi) | ⭐⭐ |
| J-Pop | Web scraping (curl_cffi) | ⭐⭐ |
| Panini Comics | Web scraping (curl_cffi) | ⭐⭐ |
| RW Edizioni | Web scraping (curl_cffi) | ⭐⭐ |
| DuckDuckGo | Search | ⭐⭐ |
| Calendario editoriale | JSON locale | ⭐⭐⭐ |

## Setup GitHub Actions

### 1. Crea il repo

```bash
gh repo create komik-release-bot --private
cd komik-release-bot
cp -r /root/.openclaw/workspace/komik-release-bot/* .
cp -r /root/.openclaw/workspace/komik-release-bot/.github .
git add . && git commit -m "init" && git push
```

### 2. Configura i Secrets

Su GitHub → Settings → Secrets → Actions:

| Secret | Valore |
|--------|--------|
| `BOT_TOKEN` | `8621330078:AAElhR3cNfrTd0Er1jTaboaNZAc8qEgYRsA` |
| `CHAT_ID` | `-1002240549288` |
| `TOPIC_ID` | `424` |

### 3. Test manuale

GitHub → Actions → "Komik Release Bot" → "Run workflow"

### 4. Schedule automatico

Già configurato: ogni lunedì alle 10:00 UTC.

## Calendario editoriale

Per uscite precise, aggiorna `calendario.json`:

```json
[
  {
    "casa": "Star Comics",
    "nome": "One Piece Vol. 108",
    "data": "31/03/2026",
    "sinossi": "Luffy e la ciurma proseguono..."
  }
]
```

Le date devono essere nella settimana corrente (lunedì-domenica).

## Esecuzione locale

```bash
pip install -r requirements.txt
export BOT_TOKEN="xxx"
export CHAT_ID="-1002240549288"
export TOPIC_ID="424"
python scraper.py
```

## Struttura

```
komik-release-bot/
├── scraper.py                    # Script principale
├── config.json                   # Config locale (non usata da GitHub Actions)
├── calendario.json               # Uscite manuali
├── requirements.txt              # Dipendenze
├── .github/workflows/
│   └── release-bot.yml           # GitHub Actions workflow
├── last_run.log                  # Ultimo output
└── debug_*.html                  # HTML per debug scraping
```
